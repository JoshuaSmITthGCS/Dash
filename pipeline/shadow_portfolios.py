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


PIPELINE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PIPELINE_DIR.parent
PUBLIC_DATA = REPO_ROOT / "public" / "data"
DEFAULT_STORE = PIPELINE_DIR / "shadow_store"
DEFAULT_OUTPUT = PUBLIC_DATA / "screens" / "shadow-portfolios.json"
ACTIVATION_DATE = "2026-08-02"
PERIODS_PER_YEAR = 252
MINIMUM_ANNUALIZED_OBSERVATIONS = 20

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

    spy = (benchmark.get("histories") or {}).get("SPY") or {}
    dated = [(date, close) for date, close in zip(spy.get("dates") or [], spy.get("closes") or [])
             if _finite(close)]
    output["SPY"] = ([{"ticker": "SPY", "rank": 1, "signal": None,
                       "price": round(float(dated[-1][1]), 8), "weight": 1.0}]
                     if dated else [])
    output["external"] = []
    return output


def append_payload(advisor, benchmark, screens, store_root=DEFAULT_STORE, source=None):
    as_of = str(advisor.get("generated_at") or datetime.now(timezone.utc).isoformat())[:10]
    if as_of < ACTIVATION_DATE:
        return {"as_of": as_of, "appended": [], "preserved": []}
    if not (benchmark.get("histories") or {}).get("SPY") and advisor.get("benchmark_history"):
        benchmark = {**benchmark, "histories": {**(benchmark.get("histories") or {}),
                                                "SPY": advisor["benchmark_history"]}}
    selections = selections_from_payload(advisor, benchmark, screens)
    appended, preserved = [], []
    defaults = _read_json(PIPELINE_DIR / "config" / "shadow_strategies.json", {}) \
        .get("construction_defaults", {})
    metadata = {
        "comparison_mode": "signal_only",
        "weighting_method": "equal_weight",
        "execution_lag_sessions": defaults.get("execution_lag_sessions", 1),
        "spread_bps": defaults.get("spread_bps", 10),
        "slippage_bps": defaults.get("slippage_bps", 10),
        "source": source or "scheduled_public_refresh",
    }
    for strategy, rows in selections.items():
        if not rows:
            continue
        try:
            append_immutable_snapshot(str(store_root), strategy, as_of, rows, metadata)
            appended.append(strategy)
        except FileExistsError:
            # The first observation of a market date is the immutable one. Later intraday
            # refreshes and rescoring runs may report different values but cannot rewrite it.
            preserved.append(strategy)
    return {"as_of": as_of, "appended": appended, "preserved": preserved}


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


def matched_returns(snapshots, market_snapshots):
    """Return forward portfolio returns using only the next immutable price tape."""
    market_by_date = {
        snapshot["as_of"]: {row["ticker"]: float(row["price"]) for row in snapshot["rows"]}
        for snapshot in market_snapshots
    }
    returns, turnovers, dates, skipped = [], [], [], 0
    for index, (start, end) in enumerate(zip(snapshots, snapshots[1:])):
        next_prices = market_by_date.get(end["as_of"], {})
        holdings = start["rows"]
        if not holdings or any(row["ticker"] not in next_prices for row in holdings):
            skipped += 1
            continue
        gross = sum(float(row["weight"]) * (next_prices[row["ticker"]] / float(row["price"]) - 1)
                    for row in holdings)
        returns.append(gross)
        turnovers.append(1.0 if index == 0 else weighted_turnover(snapshots[index - 1]["rows"], holdings))
        dates.append({"start": start["as_of"], "end": end["as_of"]})
    return {"returns": returns, "turnover": turnovers, "periods": dates, "skipped": skipped}


def _strategy_report(strategy, store_root, defaults):
    snapshots = _load_snapshots(store_root, strategy)
    if strategy == "external" and not snapshots:
        return {"strategy": STRATEGIES[strategy], "snapshots": 0, "observations": 0,
                "evidence_status": "No legal manual snapshots imported"}
    if not snapshots:
        return {"strategy": STRATEGIES[strategy], "snapshots": 0, "observations": 0,
                "evidence_status": "Collection wired · awaiting first eligible portfolio"}
    market = (_load_snapshots(store_root, "SPY") if strategy == "SPY"
              else _load_snapshots(store_root, "eligible_universe_equal_weight"))
    matched = matched_returns(snapshots, market)
    if not matched["returns"]:
        return {"strategy": STRATEGIES[strategy], "snapshots": len(snapshots), "observations": 0,
                "window_start": snapshots[0]["as_of"], "window_end": snapshots[-1]["as_of"],
                "evidence_status": f"{len(snapshots)} immutable snapshot{'s' if len(snapshots) != 1 else ''} · first matched return pending"}
    cost_bps = float(defaults.get("spread_bps", 10)) + float(defaults.get("slippage_bps", 10))
    metrics = performance_metrics(
        matched["returns"], turnover=matched["turnover"], cost_bps=cost_bps,
        periods_per_year=PERIODS_PER_YEAR,
    )
    percent = lambda value: None if value is None else round(float(value) * 100, 4)
    return {
        "strategy": STRATEGIES[strategy],
        "net_return": percent(metrics["net_return"]),
        "cagr": (percent(metrics["cagr"])
                 if metrics["observations"] >= MINIMUM_ANNUALIZED_OBSERVATIONS else None),
        "sharpe": (round(metrics["sharpe"], 4)
                   if metrics["observations"] >= MINIMUM_ANNUALIZED_OBSERVATIONS
                   and metrics["sharpe"] is not None else None),
        "sortino": (round(metrics["sortino"], 4)
                    if metrics["observations"] >= MINIMUM_ANNUALIZED_OBSERVATIONS
                    and metrics["sortino"] is not None else None),
        "max_drawdown": percent(metrics["maximum_drawdown"]),
        "turnover": percent(metrics["turnover"]),
        "snapshots": len(snapshots),
        "observations": metrics["observations"],
        "window_start": matched["periods"][0]["start"],
        "window_end": matched["periods"][-1]["end"],
        "comparison_mode": "signal_only",
        "cost_bps": cost_bps,
        "promotion_eligible": False,
        "annualized_metrics_minimum_observations": MINIMUM_ANNUALIZED_OBSERVATIONS,
        "evidence_status": f"Accumulating · {metrics['observations']} immutable net-of-cost return{'s' if metrics['observations'] != 1 else ''}",
    }


def build_report(store_root=DEFAULT_STORE):
    config = _read_json(PIPELINE_DIR / "config" / "shadow_strategies.json", {})
    defaults = config.get("construction_defaults", {})
    return {
        "schema_version": "1.1.0",
        "model_version": "shadow-validation-v1.1.0",
        "config_version": config.get("config_version", "shadow-construction-v1.0.0"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "comparison_type": "prospective",
        "comparison_mode": "signal_only",
        "metric_unit": "percent",
        "promotion_gate": "No strategy is promotion-eligible until the configured 36 monthly observations are complete.",
        "strategies": [_strategy_report(strategy, store_root, defaults) for strategy in STRATEGIES],
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
    args = parser.parse_args(argv)
    if args.bootstrap_git:
        bootstrap_git(args.store)
    advisor, benchmark, screens = current_payload()
    append_payload(advisor, benchmark, screens, args.store)
    report = build_report(args.store)
    write_report(report, args.output)
    live = sum(row.get("observations", 0) > 0 for row in report["strategies"])
    print(f"Shadow portfolios: {live} strategies with matched observations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
