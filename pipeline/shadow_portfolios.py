"""Build the public shadow-portfolio report from immutable, dated selections.

The old ``public/data/screens/shadow-portfolios.json`` file was a static placeholder.
This module makes the screen an output of the refresh pipeline:

* one selection per strategy and market date is appended, never overwritten;
* the next dated price tape values the prior selection, so current information can never
  leak into an earlier result;
* every reported return is net of the declared spread and slippage assumptions; and
* strategies whose upstream screen is still unavailable remain explicitly accumulating.

``--bootstrap-git`` is a one-time migration for the already-published production ranking,
SPY, and eligible-universe snapshots retained in Git since the shadow contract was
declared. Git commit ids are stored in the snapshot metadata. Challenger screens are not
reconstructed: their collection begins only when their live screen actually publishes.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path

from validation_framework import append_immutable_snapshot, performance_metrics


def sessions_between(start_session, end_session):
    """Trading sessions elapsed between two session dates, or ``None`` if unknowable.

    Runs do not capture every session -- no run ever read 2026-08-05 -- so consecutive
    snapshots can straddle a two-session gap. Counting each stored period as one session
    would understate elapsed time and inflate every annualized statistic derived from it.
    """
    if not start_session or not end_session:
        return None
    try:
        from validation.trading_calendar import default_calendar
        sessions = default_calendar().sessions
    except Exception:  # noqa: BLE001 - an absent price history must not break reporting
        return None
    index = {day.isoformat(): position for position, day in enumerate(sessions)}
    if start_session not in index or end_session not in index:
        return None
    return index[end_session] - index[start_session]


PIPELINE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PIPELINE_DIR.parent
PUBLIC_DATA = REPO_ROOT / "public" / "data"
DEFAULT_STORE = PIPELINE_DIR / "shadow_store"
DEFAULT_OUTPUT = PUBLIC_DATA / "screens" / "shadow-portfolios.json"
ACTIVATION_DATE = "2026-08-02"
PERIODS_PER_YEAR = 252
MINIMUM_ANNUALIZED_OBSERVATIONS = 20
# Portfolio weight that may be carried at a stale price for one session before the period
# is treated as unpriced rather than merely incomplete.
MAXIMUM_CARRIED_WEIGHT = 0.10

STRATEGIES = OrderedDict([
    ("production", "Existing production model"),
    ("structural_tactical", "Structural + tactical model"),
    ("momentum", "Momentum sleeve"),
    ("quality_value", "Quality-value sleeve"),
    ("combined", "Combined model"),
    ("SPY", "SPY benchmark"),
    ("eligible_universe_equal_weight", "Equal-weight eligible universe"),
    ("external", "User-imported external rankings"),
])


def _read_json(path, fallback=None):
    try:
        with open(path) as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return fallback


def _finite(value):
    return value is not None and not isinstance(value, bool) and math.isfinite(float(value))


def _priced_universe(advisor):
    unique = {}
    for row in [*(advisor.get("research") or []), *(advisor.get("screen_universe") or []),
                *(advisor.get("portfolio_coverage") or [])]:
        ticker = str(row.get("ticker") or "").upper()
        if ticker and _finite(row.get("price")) and float(row["price"]) > 0:
            unique.setdefault(ticker, row)
    return unique


def _equal_weight_rows(rows, price_by_ticker, signal_field=None, limit=20):
    selected = []
    seen = set()
    for candidate in rows:
        ticker = str(candidate.get("ticker") or "").upper()
        price_row = price_by_ticker.get(ticker)
        if ticker in seen or not price_row:
            continue
        seen.add(ticker)
        selected.append({
            "ticker": ticker,
            "rank": len(selected) + 1,
            "signal": candidate.get(signal_field) if signal_field else candidate.get("score"),
            "price": round(float(price_row["price"]), 8),
        })
        if limit and len(selected) >= limit:
            break
    if not selected:
        return []
    weight = 1 / len(selected)
    return [{**row, "weight": weight} for row in selected]


def selections_from_payload(advisor, benchmark, screens=None):
    """Project current public outputs into predeclared signal-only portfolios."""
    screens = screens or {}
    price_by_ticker = _priced_universe(advisor)
    production = sorted(
        (row for row in advisor.get("research") or [] if _finite(row.get("score"))),
        key=lambda row: float(row["score"]), reverse=True,
    )
    eligible = [{"ticker": ticker, "score": None} for ticker in sorted(price_by_ticker)]

    def screen_rows(name, signal_field):
        payload = screens.get(name) or {}
        if payload.get("status") != "success":
            return []
        rows = [row for row in payload.get("results") or [] if row.get("eligibility", True)]
        return _equal_weight_rows(rows, price_by_ticker, signal_field=signal_field)

    output = {
        "production": _equal_weight_rows(production, price_by_ticker, signal_field="score"),
        "structural_tactical": screen_rows("structural-tactical", "tactical_score"),
        "momentum": screen_rows("momentum", "percentile"),
        "quality_value": screen_rows("quality-value", "quality_value_score"),
        "eligible_universe_equal_weight": _equal_weight_rows(
            eligible, price_by_ticker, limit=None,
        ),
    }

    # The combined model is published only after all three constituent sleeves are live.
    # Guessing an allocation while a sleeve is unavailable would silently change the test.
    sleeve_keys = ("structural_tactical", "momentum", "quality_value")
    if all(output.get(key) for key in sleeve_keys):
        ranks = {}
        for sleeve in sleeve_keys:
            for row in output[sleeve]:
                ranks.setdefault(row["ticker"], []).append(row["rank"])
        combined = sorted(
            ({"ticker": ticker, "score": -sum(values) / len(values)}
             for ticker, values in ranks.items() if len(values) == len(sleeve_keys)),
            key=lambda row: row["score"], reverse=True,
        )
        output["combined"] = _equal_weight_rows(combined, price_by_ticker, signal_field="score")
    else:
        output["combined"] = []

    session = price_session(benchmark)
    output["SPY"] = ([{"ticker": "SPY", "rank": 1, "signal": None,
                       "price": round(float(session[1]), 8), "weight": 1.0}]
                     if session else [])
    output["external"] = []
    return output


def price_session(benchmark):
    """The market session every price in this run reflects, as ``(date, SPY close)``.

    Every leg of a run is fetched from the same upstream tape, so one session date governs
    all of them. Reading it from the tape rather than from the wall clock is the point: a
    run at 08:24 UTC on a Monday carries *Friday's* closes, and a run on a Saturday carries
    the same Friday closes as the Friday run did. Dating those by ``generated_at`` invents
    market sessions that never happened, and prices them as if the portfolio had earned a
    return over a weekend it slept through.
    """
    spy = (benchmark.get("histories") or {}).get("SPY") or {}
    dated = [(str(day)[:10], close)
             for day, close in zip(spy.get("dates") or [], spy.get("closes") or [])
             if day and _finite(close)]
    return max(dated, key=lambda item: item[0]) if dated else None


def append_payload(advisor, benchmark, screens, store_root=DEFAULT_STORE, source=None):
    as_of = str(advisor.get("generated_at") or datetime.now(timezone.utc).isoformat())[:10]
    if as_of < ACTIVATION_DATE:
        return {"as_of": as_of, "appended": [], "preserved": [], "stale_tape": []}
    if not (benchmark.get("histories") or {}).get("SPY") and advisor.get("benchmark_history"):
        benchmark = {**benchmark, "histories": {**(benchmark.get("histories") or {}),
                                                "SPY": advisor["benchmark_history"]}}
    session = price_session(benchmark)
    selections = selections_from_payload(advisor, benchmark, screens)
    appended, preserved, stale = [], [], []
    defaults = _read_json(PIPELINE_DIR / "config" / "shadow_strategies.json", {}) \
        .get("construction_defaults", {})
    metadata = {
        "comparison_mode": "signal_only",
        "weighting_method": "equal_weight",
        "execution_lag_sessions": defaults.get("execution_lag_sessions", 1),
        "spread_bps": defaults.get("spread_bps", 10),
        "slippage_bps": defaults.get("slippage_bps", 10),
        "price_session": session[0] if session else None,
        "source": source or "scheduled_public_refresh",
    }
    for strategy, rows in selections.items():
        if not rows:
            continue
        # A run whose tape has not moved past the last stored snapshot is a re-read of a
        # session already recorded, not a new observation. Storing it would manufacture a
        # zero-return period that still gets charged rebalance cost.
        if session and _stored_price_session(store_root, strategy) == session[0]:
            stale.append(strategy)
            continue
        try:
            append_immutable_snapshot(str(store_root), strategy, as_of, rows, metadata)
            appended.append(strategy)
        except FileExistsError:
            # The first observation of a market date is the immutable one. Later intraday
            # refreshes and rescoring runs may report different values but cannot rewrite it.
            preserved.append(strategy)
    return {"as_of": as_of, "appended": appended, "preserved": preserved, "stale_tape": stale}


def _stored_price_session(store_root, strategy):
    """The market session of the newest stored snapshot, or ``None`` for legacy rows."""
    snapshots = _load_snapshots(store_root, strategy)
    return snapshot_session(snapshots[-1]) if snapshots else None


def snapshot_session(snapshot):
    """The market session a stored snapshot priced, when it recorded one.

    Snapshots written before sessions were stamped return ``None``; callers fall back to
    comparing the tapes themselves rather than assuming each stored date is its own session.
    """
    return ((snapshot.get("methodology") or {}).get("price_session")) or None


def _load_snapshots(store_root, strategy):
    directory = Path(store_root) / strategy
    if not directory.exists():
        return []
    snapshots = []
    for path in sorted(directory.glob("*.json")):
        payload = _read_json(path)
        if payload and payload.get("rows"):
            snapshots.append(payload)
    return sorted(snapshots, key=lambda row: row["as_of"])


def weighted_turnover(previous_rows, current_rows):
    previous = {row["ticker"]: float(row.get("weight") or 0) for row in previous_rows}
    current = {row["ticker"]: float(row.get("weight") or 0) for row in current_rows}
    return 0.5 * sum(abs(current.get(ticker, 0) - previous.get(ticker, 0))
                     for ticker in set(previous) | set(current))


def turnover_components(previous_rows, current_rows, investable=None):
    """Split weight change into ``(traded, composition)``.

    A name the previous tape could not price was not available to hold, so its arrival is
    the data coverage widening, not a decision to buy. Charging it as turnover bills the
    strategy for a trade nobody could have made -- and it is not a rounding error here: the
    eligible universe went from 414 priced names to 872 in a single run, which reads as a
    52% rebalance of a benchmark that by construction never rebalances.

    ``composition`` is the weight landing in those newly priced names. Turnover is then
    measured on what remains, renormalized back to a full book, which is what isolates the
    rotation from the dilution: every incoming name mechanically trims every existing
    holding, and counting that trim as a sale would charge the same coverage change twice,
    once on each side of the trade.
    """
    previous = {row["ticker"]: float(row.get("weight") or 0) for row in previous_rows}
    current = {row["ticker"]: float(row.get("weight") or 0) for row in current_rows}
    newly_covered = {ticker for ticker in current
                     if investable is not None and ticker not in previous and ticker not in investable}
    composition = sum(current[ticker] for ticker in newly_covered)
    tradable = {ticker: weight for ticker, weight in current.items() if ticker not in newly_covered}
    total = sum(tradable.values())
    if total:
        tradable = {ticker: weight / total for ticker, weight in tradable.items()}
    traded = 0.5 * sum(abs(tradable.get(ticker, 0) - previous.get(ticker, 0))
                       for ticker in set(previous) | set(tradable))
    return traded, composition


def tape_advanced(start, end):
    """True when ``end`` prices a later market session than ``start``.

    Stamped snapshots answer this exactly. For snapshots written before sessions were
    recorded, an unchanged price on every commonly held name is the same evidence: a tape
    that did not move at all did not close another session, it was re-read.
    """
    start_session, end_session = snapshot_session(start), snapshot_session(end)
    if start_session and end_session:
        return start_session != end_session
    before = {row["ticker"]: float(row["price"]) for row in start["rows"]}
    after = {row["ticker"]: float(row["price"]) for row in end["rows"]}
    shared = set(before) & set(after)
    return not shared or any(before[ticker] != after[ticker] for ticker in shared)


def matched_returns(snapshots, market_snapshots, maximum_carried_weight=MAXIMUM_CARRIED_WEIGHT):
    """Return forward portfolio returns using only the next immutable price tape.

    A holding absent from the next tape is carried at its own last price for one session --
    the declared ``unavailable_price_handling`` policy -- rather than voiding the period.
    A truncated upstream fetch drops a contiguous block of tickers, and discarding every
    period it touches throws away real observations to hide a data-collection fault. Beyond
    ``maximum_carried_weight`` of the portfolio the period genuinely is unpriced and is
    skipped, with the reason recorded either way.
    """
    market_by_date = {
        snapshot["as_of"]: {row["ticker"]: float(row["price"]) for row in snapshot["rows"]}
        for snapshot in market_snapshots
    }
    returns, turnovers, dates, skipped = [], [], [], []
    compositions = []
    for index, (start, end) in enumerate(zip(snapshots, snapshots[1:])):
        next_prices = market_by_date.get(end["as_of"], {})
        holdings = start["rows"]
        if not holdings:
            skipped.append({"start": start["as_of"], "end": end["as_of"], "reason": "EMPTY_PORTFOLIO"})
            continue
        if not tape_advanced(start, end):
            skipped.append({"start": start["as_of"], "end": end["as_of"],
                            "reason": "PRICE_SESSION_DID_NOT_ADVANCE"})
            continue
        carried = [row for row in holdings if row["ticker"] not in next_prices]
        carried_weight = sum(float(row["weight"]) for row in carried)
        if carried_weight > maximum_carried_weight:
            skipped.append({"start": start["as_of"], "end": end["as_of"],
                            "reason": "NEXT_TAPE_MISSING_PRICES",
                            "missing_weight": round(carried_weight, 6),
                            "missing_tickers": sorted(row["ticker"] for row in carried)})
            continue
        gross = sum(float(row["weight"])
                    * (next_prices.get(row["ticker"], float(row["price"])) / float(row["price"]) - 1)
                    for row in holdings)
        returns.append(gross)
        # The entry charge belongs to the first period actually observed. Keying it to the
        # first snapshot *pair* silently exempted any strategy whose opening period was
        # skipped from ever paying to establish its portfolio.
        if not dates:
            traded, composition = 1.0, 0.0
        else:
            previous = snapshots[index - 1]
            traded, composition = turnover_components(
                previous["rows"], holdings, investable=market_by_date.get(previous["as_of"]))
        turnovers.append(traded)
        compositions.append(composition)
        dates.append({"start": start["as_of"], "end": end["as_of"],
                      "session_start": snapshot_session(start), "session_end": snapshot_session(end),
                      "sessions_elapsed": sessions_between(snapshot_session(start), snapshot_session(end)),
                      "composition_change": round(composition, 6),
                      "carried_weight": round(carried_weight, 6)})
    return {"returns": returns, "turnover": turnovers, "periods": dates,
            "composition_change": compositions,
            "skipped": len(skipped), "skipped_detail": skipped}


def _effective_periods_per_year(periods):
    """Annualization factor implied by sessions actually elapsed, not periods stored.

    ``performance_metrics`` derives years as ``len(returns) / periods_per_year``. When a
    period spans two sessions because no run captured the one between, a flat 252 tells it
    less calendar time passed than really did, which inflates CAGR and Sharpe alike. Scaling
    the factor by the observed session count makes that division resolve to the true elapsed
    sessions over 252. Falls back to the flat rate when no period could be dated.
    """
    elapsed = [period.get("sessions_elapsed") for period in periods]
    total = sum(value for value in elapsed if value)
    if not total or any(value is None for value in elapsed):
        return PERIODS_PER_YEAR, None
    return PERIODS_PER_YEAR * len(periods) / total, total


def _period_key(period):
    return (period.get("session_start"), period.get("session_end"))


def _metrics_block(returns, turnover, cost_bps, periods):
    periods_per_year, sessions = _effective_periods_per_year(periods)
    metrics = performance_metrics(returns, turnover=turnover, cost_bps=cost_bps,
                                  periods_per_year=periods_per_year)
    gated = metrics["observations"] >= MINIMUM_ANNUALIZED_OBSERVATIONS
    percent = lambda value: None if value is None else round(float(value) * 100, 4)
    return {
        "net_return": percent(metrics["net_return"]),
        "gross_return": percent(metrics["gross_return"]),
        "cagr": percent(metrics["cagr"]) if gated else None,
        "sharpe": round(metrics["sharpe"], 4) if gated and metrics["sharpe"] is not None else None,
        "sortino": round(metrics["sortino"], 4) if gated and metrics["sortino"] is not None else None,
        "max_drawdown": percent(metrics["maximum_drawdown"]),
        "turnover": percent(metrics["turnover"]),
        "transaction_costs": percent(metrics["transaction_costs"]),
        "observations": metrics["observations"],
        "sessions_elapsed": sessions,
    }


def _strategy_matched(strategy, store_root):
    snapshots = _load_snapshots(store_root, strategy)
    if not snapshots:
        return snapshots, None
    market = (_load_snapshots(store_root, "SPY") if strategy == "SPY"
              else _load_snapshots(store_root, "eligible_universe_equal_weight"))
    return snapshots, matched_returns(snapshots, market)


def _strategy_report(strategy, store_root, defaults, aligned_keys=None):
    snapshots, matched = _strategy_matched(strategy, store_root)
    if strategy == "external" and not snapshots:
        return {"strategy": STRATEGIES[strategy], "snapshots": 0, "observations": 0,
                "evidence_status": "No legal manual snapshots imported"}
    if not snapshots:
        return {"strategy": STRATEGIES[strategy], "snapshots": 0, "observations": 0,
                "evidence_status": "Collection wired · awaiting first eligible portfolio"}
    if not matched["returns"]:
        pending = next((row["reason"] for row in matched["skipped_detail"]), None)
        return {"strategy": STRATEGIES[strategy], "snapshots": len(snapshots), "observations": 0,
                "window_start": snapshots[0]["as_of"], "window_end": snapshots[-1]["as_of"],
                "pending_reason": pending,
                "evidence_status": f"{len(snapshots)} immutable snapshot{'s' if len(snapshots) != 1 else ''} · first matched return pending"}
    cost_bps = float(defaults.get("spread_bps", 10)) + float(defaults.get("slippage_bps", 10))
    block = _metrics_block(matched["returns"], matched["turnover"], cost_bps, matched["periods"])
    report = {
        "strategy": STRATEGIES[strategy],
        **block,
        "composition_change": round(sum(matched["composition_change"]) * 100, 4),
        "snapshots": len(snapshots),
        "skipped_periods": matched["skipped"],
        "skipped_detail": matched["skipped_detail"],
        "window_start": matched["periods"][0]["session_start"] or matched["periods"][0]["start"],
        "window_end": matched["periods"][-1]["session_end"] or matched["periods"][-1]["end"],
        "comparison_mode": "signal_only",
        "cost_bps": cost_bps,
        "promotion_eligible": False,
        "annualized_metrics_minimum_observations": MINIMUM_ANNUALIZED_OBSERVATIONS,
        "evidence_status": f"Accumulating · {block['observations']} immutable net-of-cost return{'s' if block['observations'] != 1 else ''}",
    }
    if aligned_keys:
        selected = [index for index, period in enumerate(matched["periods"])
                    if _period_key(period) in aligned_keys]
        if selected:
            aligned_periods = [matched["periods"][index] for index in selected]
            # The entry charge is re-based onto the first period of the aligned window: over
            # a shortened window the strategy is being measured from the moment it is bought,
            # exactly as it is over its own full window.
            aligned_turnover = [1.0 if position == 0 else matched["turnover"][index]
                                for position, index in enumerate(selected)]
            report["aligned"] = {
                **_metrics_block([matched["returns"][index] for index in selected],
                                 aligned_turnover, cost_bps, aligned_periods),
                "window_start": aligned_periods[0]["session_start"],
                "window_end": aligned_periods[-1]["session_end"],
            }
    return report


def aligned_period_keys(store_root, strategies=None):
    """Session periods every live strategy observed, so their returns are comparable.

    Strategies begin collecting on different days and skip different periods, so their
    headline returns cover different stretches of market. Reading those side by side is not
    a comparison -- SPY's number covered a rally that the momentum sleeve, which started two
    sessions later, was never in a position to earn. This is the intersection they all share.
    """
    shared = None
    for strategy in (strategies or STRATEGIES):
        _, matched = _strategy_matched(strategy, store_root)
        if not matched or not matched["returns"]:
            continue
        keys = {_period_key(period) for period in matched["periods"] if all(_period_key(period))}
        shared = keys if shared is None else shared & keys
    return shared or set()


def build_report(store_root=DEFAULT_STORE):
    config = _read_json(PIPELINE_DIR / "config" / "shadow_strategies.json", {})
    defaults = config.get("construction_defaults", {})
    aligned_keys = aligned_period_keys(store_root)
    strategies = [_strategy_report(strategy, store_root, defaults, aligned_keys)
                  for strategy in STRATEGIES]
    aligned = sorted(aligned_keys)
    return {
        "schema_version": "1.2.0",
        "model_version": "shadow-validation-v1.2.0",
        "config_version": config.get("config_version", "shadow-construction-v1.0.0"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "comparison_type": "prospective",
        "comparison_mode": "signal_only",
        "metric_unit": "percent",
        "promotion_gate": "No strategy is promotion-eligible until the configured 36 monthly observations are complete.",
        "aligned_window": {
            "observations": len(aligned),
            "window_start": aligned[0][0] if aligned else None,
            "window_end": aligned[-1][1] if aligned else None,
            "basis": "session periods observed by every reporting strategy",
        },
        "strategies": strategies,
    }


def write_report(report, output_path=DEFAULT_OUTPUT):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    with open(temporary, "w") as handle:
        json.dump(report, handle, indent=2, allow_nan=False)
        handle.write("\n")
    os.replace(temporary, output_path)


def _git_json(commit, path):
    try:
        raw = subprocess.check_output(
            ["git", "show", f"{commit}:{path}"], cwd=REPO_ROOT, stderr=subprocess.DEVNULL,
        )
        return json.loads(raw)
    except (subprocess.CalledProcessError, ValueError):
        return {}


def bootstrap_git(store_root=DEFAULT_STORE):
    """Import one last-published snapshot per UTC date since contract activation."""
    try:
        # Do not pass ``--since`` here. Git may prune an older-dated side of a merge before
        # reaching newer commits behind it. Reading the small metadata log and filtering
        # below reliably finds every retained publication date.
        log = subprocess.check_output([
            "git", "log", "--format=%H%x09%cI", "--", "public/data/advisor.json",
        ], cwd=REPO_ROOT, text=True)
    except subprocess.CalledProcessError:
        return []
    commits_by_day = OrderedDict()
    for line in log.splitlines():
        commit, committed_at = line.split("\t", 1)
        day = committed_at[:10]
        if day < ACTIVATION_DATE:
            continue
        commits_by_day.setdefault(day, commit)  # git log is newest first
    imported = []
    for day, commit in sorted(commits_by_day.items()):
        advisor = _git_json(commit, "public/data/advisor.json")
        benchmark = _git_json(commit, "public/data/benchmark-report.json")
        if not advisor:
            continue
        screens = {
            name: _git_json(commit, f"public/data/screens/{name}.json")
            for name in ("structural-tactical", "momentum", "quality-value")
        }
        result = append_payload(
            advisor, benchmark, screens, store_root,
            source={"kind": "git_archived_published_snapshot", "commit": commit, "commit_date": day},
        )
        if result["appended"]:
            imported.append(result)
    return imported


def _benchmark_commits():
    """``(committed_at, commit)`` for every retained benchmark-report revision, newest first."""
    try:
        log = subprocess.check_output([
            "git", "log", "--format=%H%x09%cI", "--", "public/data/benchmark-report.json",
        ], cwd=REPO_ROOT, text=True)
    except subprocess.CalledProcessError:
        return []
    rows = []
    for line in log.splitlines():
        commit, committed_at = line.split("\t", 1)
        rows.append((committed_at, commit))
    return sorted(rows, reverse=True)


def _session_at(commit):
    """The session an archived revision priced, from either published benchmark layout.

    ``benchmark-report.json`` post-dates the earliest retained snapshots; before it existed
    the same SPY history was published inline on ``advisor.json``, which ``append_payload``
    already falls back to when building a snapshot.
    """
    session = price_session(_git_json(commit, "public/data/benchmark-report.json"))
    if not session:
        advisor = _git_json(commit, "public/data/advisor.json")
        session = price_session({"histories": {"SPY": advisor.get("benchmark_history") or {}}})
    return session[0] if session else None


def _spy_closes(benchmark):
    """``[(session, close)]`` from the committed SPY history."""
    spy = (benchmark.get("histories") or {}).get("SPY") or {}
    return [(str(day)[:10], float(close))
            for day, close in zip(spy.get("dates") or [], spy.get("closes") or [])
            if day and _finite(close)]


def _session_of_close(price, closes, tolerance=1e-6):
    """The one session whose close is ``price``, or ``None`` when no single session is.

    Matched on a relative tolerance because the earliest snapshots stored the SPY close at
    the reduced precision the inline advisor history published, so 747.03 has to recognise
    itself in a history that now records 747.0300293. A price matching two sessions
    identifies neither and is rejected rather than guessed.
    """
    matches = {session for session, close in closes
               if abs(close - price) <= tolerance * max(abs(close), abs(price), 1.0)}
    return matches.pop() if len(matches) == 1 else None


def _stored_snapshots_by_date(store_root):
    grouped = OrderedDict()
    for strategy in STRATEGIES:
        directory = Path(store_root) / strategy
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.json")):
            snapshot = _read_json(path)
            if snapshot:
                grouped.setdefault(snapshot["as_of"], []).append((strategy, path, snapshot))
    return OrderedDict(sorted(grouped.items()))


def _resolve_session(entries, commits, sessions_by_commit, closes):
    """The session a stored run priced, by the most authoritative route available."""
    for _, _, snapshot in entries:
        stamped = snapshot_session(snapshot)
        if stamped:
            return stamped, "already_stamped"
    for _, _, snapshot in entries:
        source = (snapshot.get("methodology") or {}).get("source")
        commit = source.get("commit") if isinstance(source, dict) else None
        if not commit:
            recorded_at = str(snapshot.get("recorded_at") or "")
            commit = next((sha for when, sha in commits if when <= recorded_at), None)
        if not commit:
            continue
        if commit not in sessions_by_commit:
            sessions_by_commit[commit] = _session_at(commit)
        if sessions_by_commit[commit]:
            return sessions_by_commit[commit], f"archived_commit:{commit}"
    # Last resort, and only when it is unambiguous: the SPY leg of a run stores that run's
    # SPY close verbatim, so a close matching exactly one session in the committed history
    # names the session the whole run read. Bailing out here would be worse than it looks --
    # an unstamped snapshot silently falls back to tape comparison, which is precisely the
    # check that cannot see a torn tape.
    for strategy, _, snapshot in entries:
        if strategy != "SPY":
            continue
        for row in snapshot.get("rows") or []:
            session = _session_of_close(float(row["price"]), closes)
            if session:
                return session, "matched_spy_close"
    return None, None


def backfill_price_sessions(store_root=DEFAULT_STORE, benchmark=None):
    """Stamp the market session onto snapshots written before sessions were recorded.

    Without this, every already-collected snapshot falls back to comparing tapes, which
    cannot tell a genuinely flat session from a torn one -- a run that refreshed only part
    of the universe looks like real movement on the half that moved. The session each run
    actually read is recoverable: bootstrapped snapshots name the commit they were built
    from, scheduled ones match the newest benchmark revision published at or before they
    were recorded, and anything older than the retained history is identified by its own
    stored SPY close. Every leg of one run shares a tape, so the session resolved for a date
    is stamped across that date's strategies.

    Only ``methodology`` is written. ``rows`` and ``content_sha256`` -- the immutable
    selection and the prices it was made at -- are untouched, and each amended snapshot
    records how its session was recovered, so an annotation is never mistaken for something
    the original run observed.
    """
    commits = _benchmark_commits()
    closes = _spy_closes(
        benchmark if benchmark is not None else _read_json(PUBLIC_DATA / "benchmark-report.json", {}))
    sessions_by_commit, stamped = {}, []
    for as_of, entries in _stored_snapshots_by_date(store_root).items():
        session, method = _resolve_session(entries, commits, sessions_by_commit, closes)
        if not session or method == "already_stamped":
            continue
        for strategy, path, snapshot in entries:
            if snapshot_session(snapshot):
                continue
            methodology = {**(snapshot.get("methodology") or {}), "price_session": session,
                           "price_session_recovered_by": method}
            path.write_text(json.dumps({**snapshot, "methodology": methodology}, indent=2) + "\n")
            stamped.append({"strategy": strategy, "as_of": as_of, "price_session": session,
                            "recovered_by": method})
    return stamped


def current_payload():
    advisor = _read_json(PUBLIC_DATA / "advisor.json", {})
    benchmark = _read_json(PUBLIC_DATA / "benchmark-report.json", {})
    screens = {
        name: _read_json(PUBLIC_DATA / "screens" / f"{name}.json", {})
        for name in ("structural-tactical", "momentum", "quality-value")
    }
    return advisor, benchmark, screens


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--store", default=str(DEFAULT_STORE))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--bootstrap-git", action="store_true")
    parser.add_argument("--skip-session-backfill", action="store_true")
    args = parser.parse_args(argv)
    if args.bootstrap_git:
        bootstrap_git(args.store)
    if not args.skip_session_backfill:
        # Idempotent: already-stamped snapshots are skipped, so this runs harmlessly on
        # every refresh and needs no separate migration step.
        stamped = backfill_price_sessions(args.store)
        if stamped:
            print(f"Shadow portfolios: recovered price sessions for {len(stamped)} snapshots")
    advisor, benchmark, screens = current_payload()
    appended = append_payload(advisor, benchmark, screens, args.store)
    report = build_report(args.store)
    write_report(report, args.output)
    live = sum(row.get("observations", 0) > 0 for row in report["strategies"])
    aligned = report["aligned_window"]["observations"]
    if appended["stale_tape"]:
        print(f"Shadow portfolios: tape unchanged since last snapshot, skipped "
              f"{len(appended['stale_tape'])} strategies")
    print(f"Shadow portfolios: {live} strategies with matched observations "
          f"({aligned} aligned across all)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
