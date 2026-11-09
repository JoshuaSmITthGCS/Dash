"""Reweighting study for the swing and momentum screens.

Backtests the screens' declared weights against re-weighted competitors on long, price-derived
histories instead of the ~10 weeks of prospective snapshots:

  momentum  every factor (12-1, 12-7, 6-1, 52w proximity, industry-relative) is a pure function
            of price, so it is rebuilt at each month-end from ``data/backtest_cache`` exactly the
            way ``research_screens_v2.momentum_factors`` computes it, winsorized and z-scored
            across the cross-section like ``momentum_scores``. Graded on the next month's return.
  swing     ``backtest_swing.py --panel-out`` writes the 5-leg standardized cross-section for every
            weekly rebalance (analyst_revision is not reconstructable and is NaN throughout).
            Graded on the triple-barrier return and, as in that module, on every second period so
            the 10-session barrier never overlaps the next graded period.

Competitors, all scored on identical periods and names:
  current, equal, drop-one, single-leg, each weight x0/x0.5/x1.5/x2, shrunk toward equal,
  walk-forward IC-weighted, walk-forward IC-weighted shrunk 50% toward current, and the
  walk-forward winner of N random simplex weightings (best trailing ICIR).

Anything fitted only ever scores a period it did not see (expanding window, one-period embargo).
Every configuration counts as a trial in the deflated Sharpe. A final single split (fit on the
first 70%, score the last 30%) is reported for the best searched weights next to current.

Survivorship: the cache is today's ticker list walked backward, and sectors are today's. Both
inflate absolute IC for every config equally; the comparison between weightings is what this
measures, not the level.

    python pipeline/validation/screen_reweight.py --swing-panel <path from backtest_swing.py>
"""

import argparse
import json
import math
import os
import sys
from datetime import datetime, timezone

import numpy as np

PIPELINE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PIPELINE_DIR not in sys.path:
    sys.path.insert(0, PIPELINE_DIR)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from evaluation import deflated_sharpe_ratio  # noqa: E402
from weight_lab import (_sharpe, newey_west_t, quintile_spread, rank_ic, summarize,  # noqa: E402
                        top_excess)

CACHE_DIR = os.path.join(PIPELINE_DIR, "data", "backtest_cache")
REPORT_PATH = os.path.join(PIPELINE_DIR, "reports", "screen_reweight.json")
MIN_NAMES = 30
EMBARGO = 1


# --------------------------------------------------------------------------- scoring

def blend(matrix, weights):
    """Weighted mean over resolved legs (swing_signals rule SA-2026-08-12-04)."""
    weights = np.asarray(weights, dtype=float)
    present = np.isfinite(matrix) & (weights > 0)
    total = (present * weights).sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        score = np.where(present, matrix, 0.0) @ weights / total
    score[total == 0] = np.nan
    return score


def period_metrics(period, weights):
    score = blend(period["legs"], weights)
    return (rank_ic(score, period["returns"]), quintile_spread(score, period["returns"]),
            top_excess(score, period["returns"]))


def evaluate(periods, weights):
    out = {"ic": [], "spread": [], "excess": []}
    for period in periods:
        ic, spread, excess = period_metrics(period, weights)
        out["ic"].append(ic)
        out["spread"].append(spread)
        out["excess"].append(excess)
    return out


def _icir(values):
    values = [v for v in values if v is not None]
    if len(values) < 5:
        return -9.0
    std = float(np.std(values, ddof=1))
    return float(np.mean(values) / std) if std else -9.0


def _mean(values):
    values = [v for v in values if v is not None]
    return float(np.mean(values)) if values else None


# --------------------------------------------------------------------------- panels

def build_momentum_panel(cache_dir=CACHE_DIR, start="2017-10-01", min_price=5.0,
                         min_dollar_volume=2_000_000, min_peers=4):
    """Month-end momentum z-score cross-sections with next-month forward returns."""
    from research_screens_v2 import winsorize, zscores
    from backtest_swing import current_sector_map

    sectors = current_sector_map()
    series, month_end_dates = {}, {}
    for name in sorted(os.listdir(cache_dir)):
        if not name.endswith(".json"):
            continue
        payload = json.load(open(os.path.join(cache_dir, name)))
        if payload.get("is_etf") or not payload.get("closes"):
            continue
        closes = np.array(payload["closes"], dtype=float)
        if not np.isfinite(closes).all():
            continue
        last_session = {}
        for index, day in enumerate(payload["dates"]):
            last_session[day[:7]] = index
            month_end_dates[day[:7]] = max(day, month_end_dates.get(day[:7], day))
        series[payload["symbol"]] = {
            "closes": closes, "labels": last_session, "months": sorted(last_session),
            "volumes": np.array(payload.get("volumes") or np.zeros(len(closes)), dtype=float),
            "sector": sectors.get(payload["symbol"]) or "unknown"}
    months_sorted = [m for m in sorted(month_end_dates) if month_end_dates[m] >= start]

    fields = ["momentum_12_1", "momentum_12_7", "momentum_6_1", "high_52w_proximity",
              "industry_relative_momentum"]
    periods = []
    for position, month in enumerate(months_sorted[:-1]):
        next_month = months_sorted[position + 1]
        rows = []
        for ticker, data in series.items():
            end, nxt = data["labels"].get(month), data["labels"].get(next_month)
            if end is None or nxt is None or end < 252:
                continue
            closes = data["closes"]
            values = [closes[data["labels"][m]] for m in data["months"] if m <= month]
            if len(values) < 14:
                continue
            high = closes[end - 251:end + 1].max()
            dollar_volume = float(np.median(closes[end - 59:end + 1] * data["volumes"][end - 59:end + 1]))
            if closes[end] < min_price or dollar_volume < min_dollar_volume:
                continue
            forward = closes[nxt] / closes[min(end + 1, nxt)] - 1   # trade the session after the signal
            if not math.isfinite(forward):
                continue
            rows.append({"ticker": ticker, "sector": data["sector"],
                         "momentum_12_1": values[-2] / values[-13] - 1,
                         "momentum_12_7": values[-8] / values[-13] - 1,
                         "momentum_6_1": values[-2] / values[-7] - 1,
                         "high_52w_proximity": closes[end] / high, "forward": forward})
        if len(rows) < MIN_NAMES:
            continue
        by_sector = {}
        for row in rows:
            by_sector.setdefault(row["sector"], []).append(row)
        for row in rows:  # leave-one-out sector median of 12-1, like industry_relative_returns
            peers = [p["momentum_12_1"] for p in by_sector[row["sector"]] if p is not row]
            row["industry_relative_momentum"] = (row["momentum_12_1"] - float(np.median(peers))
                                                 if len(peers) >= min_peers else None)
        columns = [zscores(winsorize([r[f] for r in rows])) for f in fields]
        matrix = np.array([[np.nan if column[i] is None else column[i] for column in columns]
                           for i in range(len(rows))], dtype=float)
        periods.append({"date": month_end_dates[month], "legs": matrix,
                        "returns": np.array([r["forward"] for r in rows], dtype=float)})
    return fields, periods


def load_swing_panel(path, legs, stride=2):
    payload = json.load(open(path))
    periods = []
    for period in payload["periods"]:
        tickers = [t for t in period["forward_returns"] if t in period["leg_scores"]]
        if len(tickers) < MIN_NAMES:
            continue
        matrix = np.full((len(tickers), len(legs)), np.nan)
        for row, ticker in enumerate(tickers):
            for column, leg in enumerate(legs):
                value = period["leg_scores"][ticker].get(leg)
                if value is not None:
                    matrix[row, column] = value
        periods.append({"date": period["date"], "legs": matrix,
                        "returns": np.array([period["forward_returns"][t] for t in tickers])})
    return periods[::stride]


# --------------------------------------------------------------------------- study

def _row(name, series, indices, trials, periods_per_year, note=None, lags=0):
    ic = [series["ic"][i] for i in indices]
    spread = [series["spread"][i] for i in indices]
    excess = [series["excess"][i] for i in indices]
    base = summarize(ic, periods_per_year)
    sharpe, count, skew, kurt = _sharpe(spread)
    dsr = deflated_sharpe_ratio(sharpe, observations=count, trials=trials, skew=skew,
                                kurtosis=kurt) if sharpe is not None else None
    clean = [v for v in ic if v is not None]
    row = {"config": name, **base,
           "newey_west_t": None if len(clean) < 5 else round(newey_west_t(clean, lags) or 0, 2),
           "mean_quintile_spread_pct": None if _mean(spread) is None else round(100 * _mean(spread), 3),
           "mean_top_decile_excess_pct": None if _mean(excess) is None else round(100 * _mean(excess), 3),
           "deflated_sharpe_prob": dsr, "trials_assumed": trials}
    if note:
        row["note"] = note
    return row


def run_study(label, legs, periods, current, *, periods_per_year, warmup, trials=500, seed=7,
              lags=0):
    count = len(periods)
    k = len(legs)
    base = np.array([current[leg] for leg in legs], dtype=float)
    base = base / base.sum()
    named = {"current": base, "equal_weight": np.ones(k) / k}
    for i, leg in enumerate(legs):
        only = np.zeros(k)
        only[i] = 1
        named[f"only_{leg}"] = only
        drop = base.copy()
        drop[i] = 0
        named[f"drop_{leg}"] = drop / drop.sum()
        for factor in (0.5, 1.5, 2.0):
            scaled = base.copy()
            scaled[i] *= factor
            named[f"{leg}_x{factor:g}"] = scaled / scaled.sum()
    for blend_to_equal in (0.25, 0.5):
        named[f"shrink_to_equal_{int(blend_to_equal * 100)}"] = \
            (1 - blend_to_equal) * base + blend_to_equal * np.ones(k) / k
    evaluated = {name: evaluate(periods, w) for name, w in named.items()}

    rng = np.random.default_rng(seed)
    draws = rng.dirichlet(np.ones(k), size=trials)
    searched = [evaluate(periods, w) for w in draws]

    leg_ic = [evaluate(periods, np.eye(k)[i])["ic"] for i in range(k)]
    all_idx, oos = list(range(count)), list(range(warmup, count))
    total_trials = len(named) + trials

    def walk_forward(make_weights):
        series = {"ic": [None] * count, "spread": [None] * count, "excess": [None] * count}
        history = {}
        for t in oos:
            weights = make_weights(range(0, t - EMBARGO))
            history[t] = weights
            ic, spread, excess = period_metrics(periods[t], weights)
            series["ic"][t], series["spread"][t], series["excess"][t] = ic, spread, excess
        return series, history

    def ic_weights(train):
        raw = np.array([max(0.0, _mean([leg_ic[i][j] for j in train]) or 0.0) for i in range(k)])
        return raw / raw.sum() if raw.sum() > 0 else base

    def icir_weights(train):
        raw = np.array([max(0.0, _icir([leg_ic[i][j] for j in train])) for i in range(k)])
        return raw / raw.sum() if raw.sum() > 0 else base

    def search_pick(train):
        best = max(range(trials), key=lambda n: _icir([searched[n]["ic"][j] for j in train]))
        return draws[best]

    fitted = {}
    fitted["ic_weighted_wf"], hist_ic = walk_forward(ic_weights)
    fitted["icir_weighted_wf"], _ = walk_forward(icir_weights)
    fitted["ic_weighted_shrunk50_wf"], _ = walk_forward(lambda tr: 0.5 * ic_weights(tr) + 0.5 * base)
    fitted["random_search_best_wf"], hist_search = walk_forward(search_pick)
    evaluated.update(fitted)

    def table(indices, name):
        rows = []
        for config, series in evaluated.items():
            is_fitted = config in fitted
            rows.append(_row(config, series, [i for i in indices if series["ic"][i] is not None],
                             total_trials if is_fitted else len(named), periods_per_year,
                             "fitted on earlier periods only" if is_fitted else None, lags))
        rows.sort(key=lambda r: (r["icir"] is None, -(r["icir"] or 0)))
        return {"window": name, "periods": len(indices), "rows": rows}

    # Single split: fit on first 70 %, score last 30 %. One pick, no peeking.
    cut = int(count * 0.7)
    train_range = range(0, cut - EMBARGO)
    split_best = int(max(range(trials), key=lambda n: _icir([searched[n]["ic"][j] for j in train_range])))
    split_ic_weights = ic_weights(train_range)
    holdout = list(range(cut, count))
    holdout_rows = [_row("current", evaluated["current"], holdout, len(named) + 2, periods_per_year, None, lags)]
    for name, weights in (("split_best_random_search", draws[split_best]),
                          ("split_ic_weighted", split_ic_weights),
                          ("split_ic_weighted_shrunk50", 0.5 * split_ic_weights + 0.5 * base)):
        series = evaluate(periods, weights)
        holdout_rows.append(_row(name, series, [i for i in holdout if series["ic"][i] is not None],
                                 len(named) + trials, periods_per_year,
                                 "weights: " + json.dumps({l: round(float(w), 3)
                                                           for l, w in zip(legs, weights)}), lags))

    drift = {leg: {"first_half_ic": _mean(leg_ic[i][:count // 2]),
                   "second_half_ic": _mean(leg_ic[i][count // 2:])} for i, leg in enumerate(legs)}
    avg_pick = np.mean([hist_search[t] for t in oos], axis=0) if oos else base
    avg_ic = np.mean([hist_ic[t] for t in oos], axis=0) if oos else base
    return {
        "screen": label, "legs": legs, "periods": count,
        "first_period": periods[0]["date"], "last_period": periods[-1]["date"],
        "mean_names_per_period": round(float(np.mean([len(p["returns"]) for p in periods])), 0),
        "walk_forward_warmup": warmup, "oos_periods": count - warmup,
        "trials": {"fixed_configs": len(named), "random_draws": trials, "seed": seed},
        "current_weights": {l: round(float(w), 4) for l, w in zip(legs, base)},
        "all_periods": table(all_idx, "all periods (fitted rows are out-of-sample only)"),
        "oos_window": table(oos, f"periods {warmup}+ (identical for every config)"),
        "oos_first_half": table(oos[:len(oos) // 2], "OOS first half"),
        "oos_second_half": table(oos[len(oos) // 2:], "OOS second half"),
        "single_split_holdout": {"fit_periods": cut, "holdout_periods": count - cut,
                                 "rows": holdout_rows},
        "leg_stability": drift,
        "average_walk_forward_weights": {
            "ic_weighted": {l: round(float(w), 3) for l, w in zip(legs, avg_ic)},
            "random_search_best": {l: round(float(w), 3) for l, w in zip(legs, avg_pick)}},
        "own_ic_full_sample": {l: summarize(leg_ic[i], periods_per_year) for i, l in enumerate(legs)},
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--swing-panel", default="")
    parser.add_argument("--trials", type=int, default=500)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--out", default=REPORT_PATH)
    args = parser.parse_args(argv)

    from research_screens_v2 import MOMENTUM_WEIGHTS
    from swing_signals import SWING_WEIGHTS
    report = {"generated_at": datetime.now(timezone.utc).isoformat(), "method": __doc__.strip()}

    legs, periods = build_momentum_panel()
    report["momentum"] = run_study("momentum", legs, periods, MOMENTUM_WEIGHTS, periods_per_year=12,
                                   warmup=max(24, len(periods) // 3), trials=args.trials,
                                   seed=args.seed, lags=0)
    if args.swing_panel:
        swing_legs = list(SWING_WEIGHTS)
        swing_periods = load_swing_panel(args.swing_panel, swing_legs)
        report["swing"] = run_study("swing", swing_legs, swing_periods, SWING_WEIGHTS,
                                    periods_per_year=126, warmup=max(40, len(swing_periods) // 3),
                                    trials=args.trials, seed=args.seed, lags=0)
    report["disclosures"] = [
        "Cache is today's ticker list walked backward (survivorship) and sectors are today's.",
        "Swing analyst_revision is not reconstructable and is NaN throughout; current weights "
        "renormalize over the four legs that resolve.",
        "No production weight is changed by this report.",
    ]
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as handle:
        json.dump(report, handle, indent=1, default=str)
    return report


if __name__ == "__main__":
    main()
