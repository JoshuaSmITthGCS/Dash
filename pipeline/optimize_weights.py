"""
optimize_weights.py

Monte Carlo empirical search over the two weight blends behind the research score, built on
top of backtest_historical.py's point-in-time reconstruction and portfolio simulation:

1. "blend" -- RANKING_WEIGHTS: fundamentals vs market behavior vs news sentiment
   (currently 75/15/10, in pipeline/advisor_engine.py).
2. "categories" -- the fundamentals category_weights: valuation, profitability,
   financial_health, growth, capital_allocation, accounting_quality
   (currently 28/22/16/12/12/10, in pipeline/config/settings.json).

The expensive step -- fetching ~2 years of prices and up to 8 trailing quarters of statements
per candidate -- happens ONCE and is cached to disk. Every trial after that just re-scores and
re-simulates the SAME historical weeks with a different, randomly sampled weight vector (a
Dirichlet draw over the simplex, so weights are non-negative and always sum to 1), which is
fast: no network calls. Trial 0 in every sweep is always today's actual configuration, so every
random draw has an honest baseline to beat.

This is a tool for exploring the weight space, not an instruction to adopt whatever wins one
run. A handful of trials beating the baseline by half a point of score is noise from which
weeks happened to fall in the window; look at whether a *region* of the weight space -- not
one lucky draw -- consistently outperforms before touching pipeline/config/settings.json or
advisor_engine.RANKING_WEIGHTS. This script never writes those files itself.

Needs real network access + yfinance for the first (uncached) fetch -- same caveat as
backtest_historical.py, which this script imports and reuses rather than duplicating.

Use --holdout-weeks (and --holdout-folds for multiple walk-forward windows) before trusting any
result: it reserves the most recent weeks, searches only the earlier ones, then re-checks the
top finishers against weeks the search never saw. A config that only wins on the weeks it was
fit to is overfit, not an improvement -- this is the difference between the two.

Usage:
  python3 pipeline/optimize_weights.py --weeks 52 --trials 200 --sweep both
  python3 pipeline/optimize_weights.py --weeks 104 --trials 200 --sweep categories --seed 7 \
      --holdout-weeks 40 --holdout-folds 4
"""

import argparse
import hashlib
import json
import os
import random
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from common import LOG  # noqa: E402
import advisor_engine  # noqa: E402
from scorer import SETTINGS  # noqa: E402
import backtest_historical as bt  # noqa: E402

CACHE_DIR = os.path.join(HERE, "cache", "backtest")

RANKING_KEYS = ["fundamentals", "market_behavior", "news_sentiment"]
CATEGORY_KEYS = ["valuation", "profitability", "financial_health", "growth", "capital_allocation", "accounting_quality"]


# ---------------- weight sampling ----------------

def dirichlet(n, concentration=1.0):
    """A random point on the n-dimensional simplex (non-negative, sums to 1).

    concentration=1.0 samples uniformly over the whole simplex -- an unbiased search.
    Lower values push draws toward the corners (one factor dominating); higher values
    pull them toward an even split.
    """
    samples = [random.gammavariate(concentration, 1.0) for _ in range(n)]
    total = sum(samples)
    return [s / total for s in samples]


def random_weights(keys, concentration):
    return dict(zip(keys, dirichlet(len(keys), concentration)))


# ---------------- cached universe fetch ----------------

def cache_key(symbols, weeks, report_lag_days, benchmark_symbols):
    payload = json.dumps({
        "symbols": sorted(symbols), "weeks": weeks,
        "lag": report_lag_days, "benchmarks": sorted(benchmark_symbols),
    }, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def fetch_and_cache(symbols, benchmark_symbols, delay, weeks, report_lag_days, refresh):
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, f"universe-{cache_key(symbols, weeks, report_lag_days, benchmark_symbols)}.json")

    if os.path.exists(path) and not refresh:
        LOG.info(f"Loading cached candidate data from {path} (use --refresh-cache to re-fetch)")
        with open(path, encoding="utf-8") as f:
            payload = json.load(f)
        return payload["universe_data"], payload["benchmarks"]

    try:
        import yfinance as yf
    except ImportError:
        LOG.error("yfinance not installed. pip install -r pipeline/requirements.txt")
        sys.exit(1)

    LOG.info(f"Fetching {len(symbols)} candidates + {benchmark_symbols} (not cached yet, this is the slow part)...")
    universe_data = {}
    for i, symbol in enumerate(symbols, 1):
        data = bt.fetch_ticker_data(yf, symbol, delay)
        if data:
            universe_data[symbol] = data
        if i % 20 == 0:
            LOG.info(f"...{i}/{len(symbols)} candidates fetched ({len(universe_data)} usable)")
    LOG.info(f"Usable candidates: {len(universe_data)}/{len(symbols)}")

    benchmarks = {}
    for symbol in benchmark_symbols:
        data = bt.fetch_benchmark(yf, symbol, delay)
        if data:
            benchmarks[symbol] = data
    if "SPY" not in benchmarks:
        LOG.error("Could not fetch SPY; aborting (it's required as the primary benchmark).")
        sys.exit(1)

    with open(path, "w", encoding="utf-8") as f:
        json.dump({"universe_data": universe_data, "benchmarks": benchmarks}, f)
    LOG.info(f"Cached candidate data to {path} for future runs")
    return universe_data, benchmarks


# ---------------- one trial ----------------

def run_trial(universe_data, benchmarks, week_dates, ranking_weights, category_weights, top_n,
             monthly_contribution, report_lag_days):
    """Re-rank every cached week with these weights and re-simulate the portfolio. No network calls."""
    advisor_engine.RANKING_WEIGHTS = dict(ranking_weights)
    SETTINGS["fundamentals"]["category_weights"] = dict(category_weights)

    weekly_rankings = []
    for as_of in week_dates:
        idx = bt.price_index(benchmarks["SPY"]["dates"], as_of)
        spy_closes_to_date = benchmarks["SPY"]["closes"][:idx + 1] if idx is not None else []
        weekly_rankings.append(bt.rank_week(universe_data, spy_closes_to_date, as_of, report_lag_days))

    portfolio = bt.simulate_portfolio(weekly_rankings, week_dates, top_n, monthly_contribution)
    spy = bt.simulate_benchmark_dca(benchmarks["SPY"]["dates"], benchmarks["SPY"]["closes"], week_dates, monthly_contribution)
    return {
        "return_pct": portfolio["return_pct"],
        "final_value": portfolio["final_value"],
        "score_vs_spy": bt.score_out_of_ten(portfolio["return_pct"], spy["return_pct"]),
    }


# ---------------- a full sweep ----------------

def run_sweep(name, keys, baseline, other_fixed_ranking, other_fixed_categories, universe_data,
             benchmarks, week_dates, trials, concentration, top_n, monthly_contribution, report_lag_days):
    """`name` is 'blend' or 'categories'; the other weight group stays fixed at its baseline."""
    configs = [{k: baseline[k] for k in keys}] + [random_weights(keys, concentration) for _ in range(trials)]

    results = []
    for i, weights in enumerate(configs):
        ranking_weights = weights if name == "blend" else other_fixed_ranking
        category_weights = weights if name == "categories" else other_fixed_categories
        outcome = run_trial(universe_data, benchmarks, week_dates, ranking_weights, category_weights,
                            top_n, monthly_contribution, report_lag_days)
        results.append({"trial": i, "is_baseline": i == 0, "weights": weights, **outcome})
        if (i + 1) % 25 == 0 or i == len(configs) - 1:
            LOG.info(f"[{name}] {i + 1}/{len(configs)} trials done")

    results.sort(key=lambda r: r["score_vs_spy"] if r["score_vs_spy"] is not None else -1, reverse=True)
    return results


def split_into_folds(dates, folds):
    """Consecutive, roughly-equal chunks of a date list. Any remainder joins the last chunk."""
    if folds <= 1 or len(dates) <= 1:
        return [dates]
    fold_size = max(1, len(dates) // folds)
    chunks = [dates[i:i + fold_size] for i in range(0, len(dates), fold_size)]
    if len(chunks) > folds:
        merged = []
        for chunk in chunks[folds - 1:]:
            merged.extend(chunk)
        chunks[folds - 1:] = [merged]
    return chunks


def evaluate_holdout(name, results, top_k, other_fixed_ranking, other_fixed_categories, universe_data,
                     benchmarks, test_folds, top_n, monthly_contribution, report_lag_days):
    """Re-score the top-K training winners (plus the baseline) on one or more holdout folds --
    consecutive stretches of weeks the search never touched.

    A weight vector that only wins on the weeks it was searched against is fit to that specific
    history, not evidence of a better methodology. Checking several separate folds (not just one)
    is the difference between "won once" and "wins consistently" -- one lucky fold is still
    possible with a single holdout window. Mutates and returns the same result dicts with
    holdout_* fields attached.
    """
    baseline = next(r for r in results if r["is_baseline"])
    to_check = {id(r): r for r in results[:top_k]}
    to_check[id(baseline)] = baseline

    for r in to_check.values():
        ranking_weights = r["weights"] if name == "blend" else other_fixed_ranking
        category_weights = r["weights"] if name == "categories" else other_fixed_categories
        folds = []
        for fold_dates in test_folds:
            outcome = run_trial(universe_data, benchmarks, fold_dates, ranking_weights, category_weights,
                                top_n, monthly_contribution, report_lag_days)
            folds.append({"return_pct": outcome["return_pct"], "score_vs_spy": outcome["score_vs_spy"]})
        scores = [f["score_vs_spy"] for f in folds if f["score_vs_spy"] is not None]
        r["holdout_folds"] = folds
        r["holdout_mean_score"] = round(sum(scores) / len(scores), 2) if scores else None
        r["holdout_min_score"] = min(scores) if scores else None

    baseline_folds = baseline["holdout_folds"]
    for r in to_check.values():
        if r is baseline:
            continue
        wins = sum(
            1 for mine, base in zip(r["holdout_folds"], baseline_folds)
            if mine["score_vs_spy"] is not None and base["score_vs_spy"] is not None
            and mine["score_vs_spy"] > base["score_vs_spy"]
        )
        r["holdout_folds_beating_baseline"] = f"{wins}/{len(baseline_folds)}"
    return results


def print_leaderboard(name, keys, results, top=10, holdout=False):
    baseline = next(r for r in results if r["is_baseline"])
    baseline_rank = next(i for i, r in enumerate(results, 1) if r["is_baseline"])
    print(f"\n{'=' * 88}\n{name.upper()} SWEEP -- {len(results) - 1} random trials + baseline\n{'=' * 88}")
    holdout_header = f" {'ho.mean':>8} {'ho.min':>8} {'ho.wins':>8}" if holdout else ""
    print(f"{'#':>3} {'score':>6} {'return':>8} {'final $':>12}{holdout_header}  " + "  ".join(f"{k[:10]:>10}" for k in keys))
    for rank, r in enumerate(results[:top], 1):
        tag = " <- BASELINE (today's config)" if r["is_baseline"] else ""
        score = "—" if r["score_vs_spy"] is None else f"{r['score_vs_spy']:.1f}"
        ret = "—" if r["return_pct"] is None else f"{r['return_pct']:+.1f}%"
        weights_str = "  ".join(f"{r['weights'][k] * 100:9.1f}%" for k in keys)
        holdout_cols = ""
        if holdout:
            mean = r.get("holdout_mean_score")
            low = r.get("holdout_min_score")
            wins = "n/a" if r["is_baseline"] else r.get("holdout_folds_beating_baseline", "—")
            holdout_cols = (f" {('—' if mean is None else f'{mean:.1f}'):>8}"
                            f" {('—' if low is None else f'{low:.1f}'):>8}"
                            f" {str(wins):>8}")
        print(f"{rank:>3} {score:>6} {ret:>8} {r['final_value']:>12,.0f}{holdout_cols}  {weights_str}{tag}")
    print(f"\nBaseline (today's weights) ranked #{baseline_rank} of {len(results)} "
          f"-- score {baseline['score_vs_spy']}, return {baseline['return_pct']:+.1f}%.")
    if holdout:
        base_scores = [f["score_vs_spy"] for f in baseline.get("holdout_folds", [])]
        print(f"Baseline holdout scores by fold: {base_scores}")
        print("ho.mean/ho.min = that row's average/worst score across the same folds; "
              "ho.wins = how many of those folds it beat the baseline on. Look for consistency "
              "(most or all folds won) over a single strong fold.")


# ---------------- entry point ----------------

def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--weeks", type=int, default=52)
    parser.add_argument("--universe-limit", type=int, default=120)
    parser.add_argument("--tickers", type=str, default="")
    parser.add_argument("--top-n", type=int, default=20)
    parser.add_argument("--monthly-contribution", type=float, default=1000.0)
    parser.add_argument("--report-lag-days", type=int, default=bt.REPORT_LAG_DAYS_DEFAULT)
    parser.add_argument("--delay", type=float, default=0.3, help="Seconds between yfinance requests during fetch")
    parser.add_argument("--sweep", choices=["blend", "categories", "both"], default="both",
                        help="Which weight group to search. Each sweep holds the other group at today's baseline.")
    parser.add_argument("--trials", type=int, default=200, help="Random draws per sweep, on top of the baseline trial")
    parser.add_argument("--concentration", type=float, default=1.0,
                        help="Dirichlet concentration for the random draws (1.0 = uniform over the simplex)")
    parser.add_argument("--seed", type=int, default=None, help="Random seed, for a reproducible sweep")
    parser.add_argument("--refresh-cache", action="store_true", help="Re-fetch candidate data instead of using the cache")
    parser.add_argument("--holdout-weeks", type=int, default=0,
                        help="Reserve the most recent N weeks as a holdout: the sweep searches only the "
                             "earlier weeks, then the top finishers are re-scored on the weeks the search "
                             "never saw. 0 disables this (the default) and searches the full window, which "
                             "will happily find weights that fit that exact history -- use a holdout before "
                             "trusting a result enough to act on it.")
    parser.add_argument("--holdout-top-k", type=int, default=10,
                        help="How many top training finishers (plus the baseline) get holdout-checked")
    parser.add_argument("--holdout-folds", type=int, default=1,
                        help="Split the holdout weeks into this many consecutive folds and check top "
                             "finishers against each separately (walk-forward), instead of one lump "
                             "holdout window -- a config that wins on every fold is far more credible "
                             "than one that won a single lucky stretch. Requires --holdout-weeks; "
                             "each fold needs enough weeks left to mean something (a handful at least).")
    parser.add_argument("--out", type=str, default=os.path.join(HERE, "optimize_weights_results.json"))
    args = parser.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    baseline_ranking = dict(advisor_engine.RANKING_WEIGHTS)
    baseline_categories = dict(SETTINGS["fundamentals"]["category_weights"])

    symbols = bt.load_universe(args.universe_limit, args.tickers)
    universe_data, benchmarks = fetch_and_cache(
        symbols, ["SPY"], args.delay, args.weeks, args.report_lag_days, args.refresh_cache,
    )
    week_dates = bt.weekly_dates(args.weeks)
    if args.holdout_weeks:
        if args.holdout_weeks >= len(week_dates):
            LOG.error(f"--holdout-weeks ({args.holdout_weeks}) must be smaller than --weeks ({args.weeks})")
            sys.exit(1)
        train_dates, test_dates = week_dates[:-args.holdout_weeks], week_dates[-args.holdout_weeks:]
        test_folds = split_into_folds(test_dates, args.holdout_folds)
        LOG.info(f"Searching on {len(train_dates)} weeks, holding out the most recent {len(test_dates)} "
                 f"weeks across {len(test_folds)} fold(s) for validation")
    else:
        if args.holdout_folds > 1:
            LOG.warn("--holdout-folds has no effect without --holdout-weeks")
        train_dates, test_folds = week_dates, None

    output = {"generated_at": datetime.utcnow().isoformat() + "Z", "weeks": args.weeks, "trials": args.trials,
              "concentration": args.concentration, "seed": args.seed, "holdout_weeks": args.holdout_weeks,
              "holdout_folds": len(test_folds) if test_folds else 0, "sweeps": {}}

    try:
        if args.sweep in ("blend", "both"):
            results = run_sweep("blend", RANKING_KEYS, baseline_ranking, None, baseline_categories,
                                universe_data, benchmarks, train_dates, args.trials, args.concentration,
                                args.top_n, args.monthly_contribution, args.report_lag_days)
            if test_folds:
                evaluate_holdout("blend", results, args.holdout_top_k, None, baseline_categories,
                                 universe_data, benchmarks, test_folds, args.top_n,
                                 args.monthly_contribution, args.report_lag_days)
            print_leaderboard("blend (fundamentals / behavior / news)", RANKING_KEYS, results, holdout=bool(test_folds))
            output["sweeps"]["blend"] = results

        if args.sweep in ("categories", "both"):
            results = run_sweep("categories", CATEGORY_KEYS, baseline_categories, baseline_ranking, None,
                                universe_data, benchmarks, train_dates, args.trials, args.concentration,
                                args.top_n, args.monthly_contribution, args.report_lag_days)
            if test_folds:
                evaluate_holdout("categories", results, args.holdout_top_k, baseline_ranking, None,
                                 universe_data, benchmarks, test_folds, args.top_n,
                                 args.monthly_contribution, args.report_lag_days)
            print_leaderboard("fundamentals categories", CATEGORY_KEYS, results, holdout=bool(test_folds))
            output["sweeps"]["categories"] = results
    finally:
        # Global scoring state was monkey-patched per trial above; always leave it as found.
        advisor_engine.RANKING_WEIGHTS = baseline_ranking
        SETTINGS["fundamentals"]["category_weights"] = baseline_categories

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, default=str)
    LOG.info(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
