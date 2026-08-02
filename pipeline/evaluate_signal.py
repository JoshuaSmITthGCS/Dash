"""Grade a scoring configuration against the point-in-time store.

    python pipeline/evaluate_signal.py --help
    python pipeline/evaluate_signal.py --horizon-days 21 --trials 40
    python pipeline/evaluate_signal.py --paper-log candidate_v2

This is the gate a weight change goes through before it ships. It reconstructs what every
company scored at each past observation date, using only what the point-in-time store says
was known then, pairs those scores with the returns that actually followed, and reports rank
IC, ICIR, quantile spread, and a deflated verdict.

It needs history to work on, and history only accumulates from running the pipeline. Early
on it will say so rather than produce a confident number from four observations - which is
the correct output, not a failure.
"""

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime

import evaluation
import pit_store
from common import LOG, load_json
from scorer import valuation_score

# Below this many rebalance periods, an IC estimate is noise with error bars wider than any
# effect it could detect. Reporting it as a finding would be worse than reporting nothing.
MIN_PERIODS_FOR_A_VERDICT = 8


def observation_dates(rows, minimum_names=20):
    """Dates with enough simultaneous observations to rank cross-sectionally."""
    counts = defaultdict(set)
    for row in rows:
        counts[row.get("observation_date")].add(row.get("ticker"))
    return sorted(date for date, tickers in counts.items()
                  if date and len(tickers) >= minimum_names)


def prices_by_date(rows):
    """{ticker: {date: price}} drawn from the observed history, for forward returns."""
    prices = defaultdict(dict)
    for row in rows:
        price = (row.get("values") or {}).get("price")
        if price:
            prices[row.get("ticker")][row.get("observation_date")] = price
    return prices


def forward_return(series, start_date, horizon_days):
    """Return from ``start_date`` to the first observation at least ``horizon_days`` later."""
    start = series.get(start_date)
    if not start:
        return None
    try:
        origin = datetime.fromisoformat(start_date).date()
    except (TypeError, ValueError):
        return None
    candidates = []
    for date_text, price in series.items():
        try:
            when = datetime.fromisoformat(date_text).date()
        except (TypeError, ValueError):
            continue
        gap = (when - origin).days
        if gap >= horizon_days:
            candidates.append((gap, price))
    if not candidates:
        return None
    return min(candidates)[1] / start - 1


def score_as_of(ticker, date_text, rows):
    """Re-score one company using only what was observed on or before a date."""
    snapshot = pit_store.as_of(ticker, date_text, rows=rows)
    if not snapshot:
        return None
    score, _ = valuation_score({**snapshot["values"], "is_etf": False})
    return score


def build_periods(horizon_days, minimum_names):
    """Assemble ``{date, scores, forward_returns}`` from the point-in-time store."""
    rows = pit_store._read(pit_store.OBSERVATIONS)  # noqa: SLF001 - same package
    if not rows:
        return [], "the point-in-time store is empty; run the pipeline a few times first"
    dates = observation_dates(rows, minimum_names)
    prices = prices_by_date(rows)
    periods = []
    for date_text in dates:
        tickers = {row["ticker"] for row in rows if row.get("observation_date") == date_text}
        scores, forwards = {}, {}
        for ticker in tickers:
            score = score_as_of(ticker, date_text, rows)
            realized = forward_return(prices.get(ticker, {}), date_text, horizon_days)
            if score is not None and realized is not None:
                scores[ticker] = score
                forwards[ticker] = realized
        if len(scores) >= minimum_names:
            periods.append({"date": date_text, "scores": scores, "forward_returns": forwards})
    if not periods:
        return [], (f"no observation date yet has {minimum_names}+ companies with a "
                    f"{horizon_days}-day forward return recorded after it")
    return periods, None


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--horizon-days", type=int, default=21,
                        help="forward-return horizon in calendar days (default: 21)")
    parser.add_argument("--quantiles", type=int, default=5,
                        help="number of score buckets (default: 5)")
    parser.add_argument("--min-names", type=int, default=20,
                        help="minimum companies per period for a cross-sectional rank")
    parser.add_argument("--trials", type=int, default=1,
                        help="how many configurations were tried. Be honest: understating "
                             "this re-inflates the deflated Sharpe it is meant to correct")
    parser.add_argument("--paper-log", metavar="CONFIG",
                        help="log the current scored universe as a frozen paper-trading "
                             "period under this config name, then exit")
    parser.add_argument("--json", action="store_true", help="emit the raw report as JSON")
    args = parser.parse_args()

    if args.paper_log:
        advisor = load_json("advisor.json") or {}
        rows = [*advisor.get("research", []), *advisor.get("screen_universe", [])]
        scores = {row["ticker"]: row["score"] for row in rows if row.get("score") is not None}
        if not scores:
            LOG.error("no scored universe in advisor.json to log")
            return 1
        logged = evaluation.log_paper_period(args.paper_log, str(advisor.get("generated_at"))[:10],
                                             scores, quantiles=args.quantiles)
        print(f"Logged {logged['universe']} scored names for {args.paper_log} "
              f"at {logged['period']}. Grade it once the forward returns exist.")
        return 0

    periods, problem = build_periods(args.horizon_days, args.min_names)
    if problem:
        print(f"Cannot evaluate yet: {problem}")
        print("\nThe store accumulates one observation per pipeline run and cannot be "
              "rebuilt retroactively, so this becomes answerable with time, not with a flag.")
        depth = pit_store.depth()
        print(f"Store depth: {depth['observations']} observations across {depth['tickers']} "
              f"tickers spanning {depth['days']} days.")
        return 2

    report = evaluation.evaluate_candidate(periods, trials=args.trials,
                                           quantiles=args.quantiles)
    evaluation.publish(report)

    if args.json:
        print(json.dumps(report, indent=2, default=str))
        return 0

    ic = report["ic"]
    print(f"Periods evaluated      : {ic['periods']} ({args.horizon_days}-day forward returns)")
    print(f"Mean rank IC           : {ic['mean_ic']}")
    print(f"ICIR (annualized)      : {ic['icir']}")
    print(f"t-statistic            : {ic['t_stat']}")
    print(f"Periods with IC > 0    : {ic['hit_rate']}")
    print(f"Mean quantile spread   : {report['mean_quantile_spread']}")
    print(f"Monotonic periods      : {report['monotonic_periods']}/{ic['periods']}")
    print(f"Deflated Sharpe prob.  : {report['deflated_sharpe_probability']} "
          f"(after {args.trials} trial(s))")
    print(f"\nVerdict: {'SHIP' if report['ship'] else 'DO NOT SHIP'}")
    for blocker in report.get("ship_blockers", []):
        print(f"  - {blocker}")
    if ic["periods"] < MIN_PERIODS_FOR_A_VERDICT:
        print(f"\nCaution: {ic['periods']} periods is too few to conclude much either way. "
              f"Treat anything above as provisional until there are at least "
              f"{MIN_PERIODS_FOR_A_VERDICT}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
