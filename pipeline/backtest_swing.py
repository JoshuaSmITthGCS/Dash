"""Historical walk-forward backtest for the swing-horizon composite (swing_signals.py).

The swing model (swing-v1.1.0) was registered in pipeline/validation/harness_freeze.json
without a backtest of any kind: "shipped as a screen without a backtest, a deflated Sharpe,
a PBO estimate or a cost model." A prospective clock starts 2026-09-01 and remains the sole
promotion authority for it - nothing here changes that, no new variant is introduced, and no
weight is tuned on the numbers this file produces. What this module adds is a supplementary
*historical* read, built the same way Round 5/6 built the as-filed research-score backtest:
by replaying only data that was genuinely knowable on each historical date, never by
reconstructing score history from what is known today.

**Leg coverage is partial, and that is disclosed rather than hidden.** Four of the five legs
are reconstructable point-in-time:

  pead_drift            edgar_sue.sue_for(ticker, as_of) reads the EDGAR PIT store directly -
                         already point-in-time by construction, same code path build_swing_
                         screen.py uses live.
  high_volume_premium   price/volume ratios off pipeline/data/backtest_cache, sliced to the
                         historical date - no different from any other price-history backtest
                         in this pipeline.
  high_52w_proximity    same cache, same slicing.
  short_term_reversal   same cache, same slicing; variant C's residualization runs inside
                         swing_signals.swing_scores exactly as it does live.

  analyst_revision      NOT reconstructable. pipeline/estimate_snapshots.py is explicitly
                         FORWARD_COLLECTION_ONLY and holds no pre-collection history - see
                         _estimates_coverage_note() for the live count. This leg is left
                         unresolved on every row for the whole backtest, which
                         swing_signals.swing_scores already handles the declared way: the
                         weight renormalizes across the legs that did resolve, and
                         leg_coverage.analyst_revision reads 0.0 throughout. This is a 4-leg
                         sub-composite of the registered model, not the model itself, and the
                         published report says so on every read.

Composite scoring, eligibility, renormalization, the legs-resolved floor and the sector cap
are not reimplemented here - every period calls swing_signals.swing_scores() directly, the
same function build_swing_screen.py calls live, across all three registered reversal variants
(swing-reversal-A/B/C, SA-2026-08-12-08). Forward outcomes use the triple-barrier labeling in
pipeline/validation/labeling.py (ATR-scaled barriers, a real trading-session vertical barrier)
rather than a naive fixed-horizon return, because a 2-to-40-session swing position is normally
exited at a target or a stop, not held blind to a fixed date. IC, ICIR, quantile spread,
deflated Sharpe and PBO reuse pipeline/evaluation.py, the same walk-forward statistics engine
already used to evaluate the research score's own shadow strategies.

**Overlap.** Rebalancing weekly against a 10-session label means adjacent periods' forward
windows overlap. Rather than weight the overlap (labeling.overlap_weights, built for a single
sequential series, not a cross-sectional panel), this backtest grades every other rebalance -
spacing graded periods by ``cadence_sessions * graded_stride`` sessions, at least the vertical
barrier length - so the graded series is genuinely non-overlapping, the same purge idea
evaluation.walk_forward's ``purge_periods`` documents for exactly this situation. The
undecimated weekly series is kept for the turnover diagnostic, which does not have an overlap
problem: it only ever compares adjacent periods' book membership.

**Known approximations, disclosed in the output under ``limitations``:** the market-cap gate
is disabled (no point-in-time share count series exists in the cache); the short-interest
negative screen is inert (no historical short-interest series exists); sector labels are the
current classification applied retroactively; and the universe is today's cache contents
walked backward, carrying the same survivorship bias backtest_monthly.py already discloses
for its own universe.

Usage:
    python pipeline/backtest_swing.py --years 3 --out pipeline/backtest_swing_results.json
    python pipeline/backtest_swing.py --years 1 --universe-limit 60   # fast smoke run
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from bisect import bisect_right
from datetime import datetime, timedelta
from statistics import mean, stdev

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from build_swing_screen import resolve_sue  # noqa: E402
from common import LOG, STORE_DIR  # noqa: E402
from panel_io import save_panel  # noqa: E402
from costs import estimate_cost_bps  # noqa: E402
from evaluation import deflated_sharpe_ratio, probability_of_backtest_overfitting, walk_forward  # noqa: E402
from screen_inputs import BACKTEST_CACHE, median_dollar_volume, universe_rows  # noqa: E402
import swing_signals  # noqa: E402
from validation.labeling import (DEFAULT_ATR_WINDOW, DEFAULT_VERTICAL_BARRIER_SESSIONS,
                                 average_true_range, triple_barrier_label)  # noqa: E402
from validation.trading_calendar import default_calendar  # noqa: E402

VARIANTS = ("A", "B", "C")
CADENCE_SESSIONS_DEFAULT = 5          # weekly rebalance
VERTICAL_SESSIONS_DEFAULT = DEFAULT_VERTICAL_BARRIER_SESSIONS   # labeling.py's own default: 10
QUANTILES_DEFAULT = 5
# The swing-reversal family's own registered trial count (harness_freeze.json
# trial_count_for_deflated_statistics.swing_reversal_variants_2026_08_12), not the repo-wide
# N=50: deflating each variant's Sharpe against a count wider than the family it was chosen
# from would be conservative in the wrong direction for what this file is measuring.
DSR_TRIALS = 3
MINIMUM_PRICE_HISTORY_SESSIONS = 60   # cheap early skip; swing_scores applies the real 253-session gate
MINIMUM_ROWS_PER_PERIOD = 20
PBO_SPLITS = 8

OUTPUT = os.path.join(HERE, "backtest_swing_results.json")


# ---------------------------------------------------------------------------
# Universe and calendar
# ---------------------------------------------------------------------------

def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def load_universe(limit=0):
    """{ticker: cached payload}, non-ETF, with a clean (no-gap) close series.

    A non-finite close in the middle of the series would silently shift every index the
    triple-barrier labeler and the ATR both compute against (both filter to finite values
    internally), so a ticker carrying one is dropped entirely rather than risking a
    mis-aligned label.
    """
    if not os.path.isdir(BACKTEST_CACHE):
        return {}
    names = sorted(name[:-5] for name in os.listdir(BACKTEST_CACHE) if name.endswith(".json"))
    if limit:
        names = names[:limit]
    universe = {}
    for ticker in names:
        try:
            with open(os.path.join(BACKTEST_CACHE, f"{ticker}.json")) as handle:
                payload = json.load(handle)
        except (OSError, ValueError):
            continue
        if payload.get("is_etf"):
            continue
        dates, closes, volumes = payload.get("dates"), payload.get("closes"), payload.get("volumes")
        if not dates or not closes or not volumes or not (len(dates) == len(closes) == len(volumes)):
            continue
        if not all(_finite(value) for value in closes):
            continue
        universe[ticker] = payload
    return universe


def rebalance_dates(calendar, years, cadence_sessions):
    """Real trading sessions, ``cadence_sessions`` apart, over the trailing ``years``."""
    sessions = calendar.sessions
    if not sessions:
        return []
    start = sessions[-1] - timedelta(days=int(years * 365.25))
    start_index = bisect_right(sessions, start)
    return sessions[start_index::max(1, cadence_sessions)]


def entry_index(dates, as_of):
    """Index of the most recent session at or before ``as_of`` in a ticker's own date list."""
    position = bisect_right(dates, as_of) - 1
    return position if position >= 0 else None


# ---------------------------------------------------------------------------
# One historical row
# ---------------------------------------------------------------------------

def current_sector_map():
    """{ticker: sector} from the live advisor snapshot.

    pipeline/data/backtest_cache carries no sector field at all (every entry's ``sector`` key
    is None - not a gap in a few names, a field the cache never populated). The live snapshot
    (screen_inputs.universe_rows) does, for the full cached universe. Using it retroactively
    is a real approximation - see the ``sector_labels`` limitation in run_backtest's output -
    but it is the only sector data that exists anywhere in this repository, and the
    alternative (no sector at all) silently breaks two things: variant C's residualization,
    which needs a sector to compute an industry-return control, and the sector concentration
    cap, which would otherwise treat the entire universe as one undifferentiated sector.
    """
    return {row["ticker"]: row.get("sector") for row in universe_rows() if row.get("ticker")}


def historical_row(ticker, payload, idx, as_of, sector=None):
    """The same shape build_swing_screen.build_rows() produces, from data visible at ``as_of``.

    Sliced to ``idx`` before anything is computed - the SUE lookup, the drift-window age, and
    every price/volume subfactor all see only sessions on or before ``as_of``. No
    ``estimate_detail`` is attached, so the analyst-revision leg's four subfactors resolve to
    None here exactly as they would for a row with no estimate data live: unresolved, not
    zero, per swing_factors' own contract.

    ``sector`` is the caller's current-sector lookup (see current_sector_map); falls back to
    the cache payload's own field, which is None for every ticker in this repository's cache
    but kept as a fallback so a future cache that does carry sector needs no code change here.
    """
    dates = payload["dates"][: idx + 1]
    closes = payload["closes"][: idx + 1]
    volumes = payload["volumes"][: idx + 1]
    sue = resolve_sue(ticker, as_of, dates)
    factors = swing_signals.swing_factors({}, closes=closes, volumes=volumes, sue=sue)
    return {
        "ticker": ticker,
        "name": payload.get("name"),
        "sector": sector if sector is not None else payload.get("sector"),
        "price": closes[-1],
        "market_cap": None,
        "median_dollar_volume_60d": median_dollar_volume(closes, volumes),
        "adv_20d_dollar_volume": swing_signals.trailing_dollar_volume(closes, volumes),
        "history_sessions": len(closes),
        "structural_score": None,
        "data_coverage": None,
        "short_percent_of_float": None,
        "days_to_cover": None,
        "factors": factors,
    }


def forward_outcome(full_closes, idx, vertical_sessions):
    """Triple-barrier return, entered at ``idx``, or None if unresolvable or not yet realized.

    ATR is measured only on the trailing slice up to ``idx`` - the barrier width a trader
    could actually have set that day. The forward path triple_barrier_label reads off
    ``full_closes`` is the real, realized future; that is the label, not a leak, the same way
    a settled option payoff in backtest_common is real while its entry price is modeled.
    """
    atr = average_true_range(None, None, full_closes[: idx + 1], window=DEFAULT_ATR_WINDOW)
    if not atr:
        return None
    label = triple_barrier_label(full_closes, idx, atr=atr, vertical_sessions=vertical_sessions)
    if label is None:
        return None
    return label["return_pct"] / 100.0


# ---------------------------------------------------------------------------
# Cost-adjusted quantile spread
# ---------------------------------------------------------------------------

def _quantile_buckets(scores, quantiles):
    """Ticker lists, top score first, split as evenly as evaluation.quantile_buckets does."""
    ordered = sorted(scores.items(), key=lambda pair: pair[1], reverse=True)
    size = len(ordered) / quantiles
    buckets = []
    for index in range(quantiles):
        start, end = int(round(index * size)), int(round((index + 1) * size))
        buckets.append([ticker for ticker, _ in ordered[start:end]])
    return buckets


def net_spread(scores, forward_returns, liquidity, quantiles):
    """Top-minus-bottom quantile spread, gross and net of a round-trip cost estimate.

    Cost is priced per name with costs.estimate_cost_bps at the ``base`` scenario (the
    canonical square-root impact law, no position size supplied so this is spread-plus-fees
    only, not market impact - a conservative understatement, same convention
    validation/ic_harness.py's tiered cost path uses), doubled for a round trip, averaged
    over every name in the top and bottom buckets.
    """
    if len(scores) < quantiles * 2:
        return None, None, None
    buckets = _quantile_buckets(scores, quantiles)
    top, bottom = buckets[0], buckets[-1]
    top_returns = [forward_returns[t] for t in top if t in forward_returns]
    bottom_returns = [forward_returns[t] for t in bottom if t in forward_returns]
    if not top_returns or not bottom_returns:
        return None, None, None
    gross = mean(top_returns) - mean(bottom_returns)
    cost_samples = []
    for ticker in (*top, *bottom):
        mdv = liquidity.get(ticker)
        if not mdv:
            continue
        one_way = estimate_cost_bps(median_dollar_volume_60d=mdv, scenario="base")["total_bps"]
        cost_samples.append(one_way * 2)
    cost_bps = mean(cost_samples) if cost_samples else None
    net = gross - cost_bps / 10_000.0 if cost_bps is not None else gross
    return round(gross, 4), round(net, 4), round(cost_bps, 2) if cost_bps is not None else None


# ---------------------------------------------------------------------------
# Estimates-coverage disclosure
# ---------------------------------------------------------------------------

def estimates_coverage_note():
    root = os.path.join(STORE_DIR, "estimates")
    if not os.path.isdir(root):
        return "pipeline/data/estimates does not exist in this checkout: zero history."
    tickers = [name for name in os.listdir(root) if os.path.isdir(os.path.join(root, name))]
    stamps = [name[:15] for ticker in tickers
              for name in os.listdir(os.path.join(root, ticker)) if name.endswith(".json")]
    if not stamps:
        return f"{len(tickers)} tickers, zero point-in-time observations recorded yet."
    return (f"{len(tickers)} tickers, {len(stamps)} point-in-time observations, "
            f"{min(stamps)} to {max(stamps)} (pipeline/estimate_snapshots.py, "
            "collection_status FORWARD_COLLECTION_ONLY -- no history exists before "
            "collection began, so the analyst_revision leg cannot be reconstructed for any "
            "date this backtest walks).")


# ---------------------------------------------------------------------------
# Walk-forward driver
# ---------------------------------------------------------------------------

def build_swing_signal_panel(periods, *, vertical_sessions):
    """Assemble the leg-level artifact pipeline/optimization_harness.py reads to search over
    technical/momentum leg weights, the same way it already reads
    pipeline/backtest_signal_panel.json for the fundamental/behavioral legs.

    ``periods`` carry variant A's (the frozen baseline's) full 5-leg standardized cross-
    section as ``leg_scores`` -- before any weight is applied -- so any candidate weight
    vector over these 5 legs, including ones that omit a leg entirely (variant B's style) or
    substitute a residualized version of one (variant C's style, which needs its own
    subfactor computed separately and is not represented here), can be tested against it
    without a new panel shape. Testing a candidate through this panel never touches
    ``swing_signals.SWING_WEIGHTS`` and does not reset the swing-v1.1.0 prospective clock --
    see harness_freeze.json's ``changes_that_reset_this_clock``.
    """
    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "model": "swing-v1.1.0",
        "primary_horizon_sessions": vertical_sessions,
        "leg_weights": dict(swing_signals.SWING_WEIGHTS),
        "note": ("Research/backtest panel only. Feeds pipeline/optimization_harness.py "
                 "candidate searches; does not feed, tune, or promote anything in production "
                 "swing_signals.py. See harness_freeze.json for the swing-v1.1.0 prospective "
                 "clock, which is the sole promotion authority for this model."),
        "periods": periods,
    }


def run_backtest(*, years=2, universe_limit=0, cadence_sessions=CADENCE_SESSIONS_DEFAULT,
                 vertical_sessions=VERTICAL_SESSIONS_DEFAULT, quantiles=QUANTILES_DEFAULT,
                 collect_signal_panel=False):
    calendar = default_calendar()
    universe = load_universe(universe_limit)
    sectors = current_sector_map()
    dates = rebalance_dates(calendar, years, cadence_sessions)
    config = {**swing_signals.DEFAULT_CONFIG, "minimum_market_cap": 0}
    graded_stride = max(1, math.ceil(vertical_sessions / max(1, cadence_sessions)))

    weekly_periods = {variant: [] for variant in VARIANTS}
    weekly_books = {variant: [] for variant in VARIANTS}
    current_members = {variant: {} for variant in VARIANTS}
    leg_hits = {variant: {leg: 0 for leg in swing_signals.SWING_WEIGHTS} for variant in VARIANTS}
    leg_totals = {variant: 0 for variant in VARIANTS}
    signal_panel_periods = [] if collect_signal_panel else None

    periods_scanned = periods_used = 0
    for session in dates:
        as_of = session.isoformat()
        periods_scanned += 1
        base_rows, idx_by_ticker = [], {}
        for ticker, payload in universe.items():
            idx = entry_index(payload["dates"], as_of)
            if idx is None or idx + 1 < MINIMUM_PRICE_HISTORY_SESSIONS:
                continue
            base_rows.append(historical_row(ticker, payload, idx, as_of, sector=sectors.get(ticker)))
            idx_by_ticker[ticker] = idx
        if len(base_rows) < MINIMUM_ROWS_PER_PERIOD:
            continue
        periods_used += 1

        period_forward_returns = {}
        for row in base_rows:
            ticker = row["ticker"]
            outcome = forward_outcome(universe[ticker]["closes"], idx_by_ticker[ticker], vertical_sessions)
            if outcome is not None:
                period_forward_returns[ticker] = outcome

        for variant in VARIANTS:
            scored = swing_signals.swing_scores(base_rows, current_members=current_members[variant],
                                                config=config, variant=variant)
            current_members[variant] = {row["ticker"]: True for row in scored
                                        if row.get("current_membership")}
            for leg in swing_signals.variant_weights(variant):
                leg_hits[variant][leg] += sum(1 for row in scored
                                              if (row.get("leg_scores") or {}).get(leg) is not None)
            leg_totals[variant] += len(scored)

            eligible = [row for row in scored if row["eligibility"]]
            scores = {row["ticker"]: row["score"] for row in eligible}
            liquidity = {row["ticker"]: row.get("median_dollar_volume_60d") for row in eligible}
            forward_returns = {ticker: value for ticker, value in period_forward_returns.items()
                               if ticker in scores}
            if scores and forward_returns:
                weekly_periods[variant].append({
                    "date": as_of, "scores": scores, "forward_returns": forward_returns,
                    "liquidity": liquidity,
                })
                if collect_signal_panel and variant == swing_signals.BASELINE_VARIANT:
                    leg_scores = {row["ticker"]: row["leg_scores"] for row in eligible
                                 if row["ticker"] in forward_returns}
                    signal_panel_periods.append({
                        "date": as_of, "leg_scores": leg_scores,
                        "forward_returns": forward_returns,
                    })
            book = {row["ticker"] for row in swing_signals.book_rows(scored, config)}
            weekly_books[variant].append(book)

        if periods_used % 20 == 0:
            LOG.info(f"backtest_swing: {periods_used} periods scored as of {as_of} "
                     f"({len(base_rows)} names)")

    results = {}
    performance_matrix = []
    graded_dates = None
    for variant in VARIANTS:
        periods = weekly_periods[variant]
        graded = periods[::graded_stride]
        if graded_dates is None:
            graded_dates = [period["date"] for period in graded]

        eval_periods = [{"date": p["date"], "scores": p["scores"],
                         "forward_returns": p["forward_returns"]} for p in graded]
        annual_factor = 252 / max(1, cadence_sessions * graded_stride)
        summary = walk_forward(eval_periods, quantiles=quantiles, periods_per_year=annual_factor)
        observations = summary["ic"]["periods"] or len(eval_periods)
        gross_deflated = deflated_sharpe_ratio(summary["spread_sharpe_per_period"],
                                               observations=observations, trials=DSR_TRIALS)

        net_spreads, gross_spreads, cost_bps_series = [], [], []
        for period in graded:
            gross, net, cost_bps = net_spread(period["scores"], period["forward_returns"],
                                              period["liquidity"], quantiles)
            if net is None:
                continue
            gross_spreads.append(gross)
            net_spreads.append(net)
            cost_bps_series.append(cost_bps)
        net_spread_sharpe = (mean(net_spreads) / stdev(net_spreads)
                             if len(net_spreads) > 2 and stdev(net_spreads) else None)
        net_deflated = deflated_sharpe_ratio(net_spread_sharpe, observations=len(net_spreads),
                                             trials=DSR_TRIALS) if net_spread_sharpe is not None else None

        turnover = []
        for before, after in zip(weekly_books[variant], weekly_books[variant][1:]):
            if not after:
                continue
            turnover.append(1 - len(before & after) / len(after))

        leg_coverage = {leg: round(leg_hits[variant][leg] / leg_totals[variant], 4)
                        if leg_totals[variant] else None
                        for leg in swing_signals.variant_weights(variant)}

        performance_matrix.append(net_spreads)
        results[variant] = {
            "variant_id": swing_signals.variant_spec(variant)["id"],
            "label": swing_signals.variant_spec(variant)["label"],
            "graded_periods": len(eval_periods),
            "weekly_periods": len(periods),
            "leg_coverage": leg_coverage,
            "ic": summary["ic"],
            "monotonic_periods": summary["monotonic_periods"],
            "mean_quantile_spread_gross": round(mean(gross_spreads), 4) if gross_spreads else None,
            "mean_quantile_spread_net_of_cost": round(mean(net_spreads), 4) if net_spreads else None,
            "mean_round_trip_cost_bps": (round(mean(cost_bps_series), 2)
                                         if cost_bps_series and all(v is not None for v in cost_bps_series)
                                         else None),
            "spread_sharpe_per_period_gross": summary["spread_sharpe_per_period"],
            "spread_sharpe_per_period_net_of_cost": (round(net_spread_sharpe, 3)
                                                      if net_spread_sharpe is not None else None),
            "deflated_sharpe_probability_gross": gross_deflated,
            "deflated_sharpe_probability_net_of_cost": net_deflated,
            "trials_considered": DSR_TRIALS,
            "mean_weekly_top_percentile_book_turnover": round(mean(turnover), 4) if turnover else None,
            "illustrative_annualized_turnover": (
                round(mean(turnover) * (252 / max(1, cadence_sessions)), 4) if turnover else None),
        }

    pbo = None
    if all(len(series) == len(performance_matrix[0]) for series in performance_matrix) \
            and performance_matrix and len(performance_matrix[0]) >= PBO_SPLITS:
        matrix = list(zip(*performance_matrix))   # [period][variant]
        pbo = probability_of_backtest_overfitting(matrix, splits=PBO_SPLITS)

    return {
        "schema_version": "1.0.0",
        "model": "swing-v1.1.0",
        "measured_legs": ["pead_drift", "high_volume_premium", "high_52w_proximity",
                          "short_term_reversal"],
        "excluded_legs": ["analyst_revision"],
        "data_window": {
            "years_requested": years,
            "rebalance_cadence_sessions": cadence_sessions,
            "vertical_barrier_sessions": vertical_sessions,
            "graded_period_stride": graded_stride,
            "periods_scanned": periods_scanned,
            "periods_used": periods_used,
            "graded_periods": len(graded_dates) if graded_dates else 0,
            "first_graded_date": graded_dates[0] if graded_dates else None,
            "last_graded_date": graded_dates[-1] if graded_dates else None,
            "universe_size": len(universe),
        },
        "variants": results,
        "probability_of_backtest_overfitting": pbo,
        "limitations": {
            "analyst_revision_leg": estimates_coverage_note(),
            "market_cap_gate": "Disabled (minimum_market_cap=0 in this backtest's config). "
                               "pipeline/data/backtest_cache does not track historical share "
                               "counts, and applying today's share count to a historical price "
                               "would be an unlabeled approximation rather than a measurement.",
            "short_interest_screen": "Inert throughout: no historical short-interest-of-float "
                                     "or days-to-cover series exists, so the negative screen "
                                     "never suppresses a name here. Every eligible name in this "
                                     "report would additionally have faced that screen live.",
            "sector_labels": "The CURRENT GICS sector is applied at every historical date "
                             "(no point-in-time sector history in the cache). Affects the "
                             "sector concentration cap and variant C's residualization.",
            "universe": "pipeline/data/backtest_cache's present ticker list walked backward - "
                       "the same current-constituent survivorship bias backtest_monthly.py "
                       "already discloses for its own universe.",
            "authority": "Supplementary historical measurement of the three already-registered "
                        "swing-reversal variants (harness_freeze.json swing_reversal_variants, "
                        "SA-2026-08-12-08). Does not replace, accelerate, or substitute for the "
                        "prospective clock starting 2026-09-01, which remains the sole "
                        "promotion authority. No new variant is introduced and no weight is "
                        "tuned on these numbers.",
        },
        "signal_panel": (build_swing_signal_panel(signal_panel_periods,
                                                  vertical_sessions=vertical_sessions)
                         if collect_signal_panel else None),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--years", type=float, default=2)
    parser.add_argument("--universe-limit", type=int, default=0,
                        help="cap the ticker universe for a fast smoke run; 0 = no limit")
    parser.add_argument("--cadence-sessions", type=int, default=CADENCE_SESSIONS_DEFAULT)
    parser.add_argument("--vertical-sessions", type=int, default=VERTICAL_SESSIONS_DEFAULT)
    parser.add_argument("--quantiles", type=int, default=QUANTILES_DEFAULT)
    parser.add_argument("--out", default=OUTPUT)
    parser.add_argument("--panel-out", default="",
                        help="Optional path to write the technical/momentum leg-level signal "
                             "panel pipeline/optimization_harness.py can search over. Empty "
                             "(default) skips it.")
    args = parser.parse_args(argv)

    result = run_backtest(years=args.years, universe_limit=args.universe_limit,
                          cadence_sessions=args.cadence_sessions,
                          vertical_sessions=args.vertical_sessions, quantiles=args.quantiles,
                          collect_signal_panel=bool(args.panel_out))
    signal_panel = result.pop("signal_panel", None)
    with open(args.out, "w") as handle:
        json.dump(result, handle, indent=2)
    for variant in VARIANTS:
        summary = result["variants"][variant]
        LOG.info(f"backtest_swing {variant}: {summary['graded_periods']} graded periods, "
                 f"mean rank IC {summary['ic'].get('mean_ic')}, "
                 f"net spread {summary['mean_quantile_spread_net_of_cost']}, "
                 f"deflated Sharpe {summary['deflated_sharpe_probability_net_of_cost']}")
    LOG.info(f"backtest_swing: wrote {args.out}")
    if args.panel_out and signal_panel:
        save_panel(args.panel_out, signal_panel)
        LOG.info(f"backtest_swing: wrote {args.panel_out}: "
                 f"{len(signal_panel['periods'])} scored cross-sections")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
