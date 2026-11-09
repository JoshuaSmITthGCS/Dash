"""Weight lab: backtest the current research-score weights against competing weightings, and
re-grade the prospective screens with overlap-aware statistics.

Part A - main model, historical panel
    ``backtest_signal_panel.json`` holds 60 month-start periods (2021-09 .. 2026-08) of
    pre-modifier leg scores and 21-session forward returns. Horizon and spacing are both about
    a month, so the periods are non-overlapping and a plain t-stat is honest.

    Competitors are scored on the identical periods and names:
      * current          - the production blend (settings.json category x ranking weights)
      * equal / single-leg / grouped blends  - fixed, no fitting
      * perturbations    - each current weight scaled x0, x0.5, x1.5, x2 (sensitivity, not search)
      * ic_weighted      - walk-forward: weights proportional to trailing positive mean IC
      * dirichlet_best   - walk-forward: best trailing ICIR of N random simplex draws

    Anything fitted is only ever scored on periods it did not see (expanding window, one-period
    embargo). Every configuration evaluated counts as a trial for the deflated Sharpe, so a
    searched winner is held to the bar its own search sets.

Part B - prospective screens
    The point-in-time stores span only ~10 weeks. ``composite_attribution.periods_from_snapshots``
    starts one period at every daily snapshot, so a 30-day horizon over 66 calendar days yields
    ~27 "periods" that share almost all of their return windows. This module reports the
    effective count (span / horizon) and a Newey-West t-stat next to the raw one, and re-runs
    the weight variants. It is diagnostic: with ~2 independent windows nothing here is evidence
    for changing a production weight.

    python pipeline/validation/weight_lab.py                 # writes pipeline/reports/weight_lab.json
    python pipeline/validation/weight_lab.py --trials 300 --seed 7
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

from common import LOG, load_json  # noqa: E402
from evaluation import deflated_sharpe_ratio  # noqa: E402

PANEL_PATH = os.path.join(PIPELINE_DIR, "backtest_signal_panel.json")
REPORT_PATH = os.path.join(PIPELINE_DIR, "reports", "weight_lab.json")  # not under public/data: no schema contract
LEGS = ["valuation", "profitability", "financial_health", "growth", "capital_allocation",
        "accounting_quality", "market_behavior", "news_sentiment"]
MIN_NAMES = 30            # a period needs this many scored names to be graded
MIN_TRAIN_PERIODS = 24    # expanding-window warm-up before any fitted config is scored
EMBARGO = 1               # periods dropped between the train window and the scored period


# --------------------------------------------------------------------------- statistics

def _rank(values):
    """Average ranks (ties share the mean rank), NaN-free input."""
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(len(values))
    ranks[order] = np.arange(len(values), dtype=float)
    sorted_vals = values[order]
    start = 0
    for index in range(1, len(values) + 1):
        if index == len(values) or sorted_vals[index] != sorted_vals[start]:
            if index - start > 1:
                ranks[order[start:index]] = (start + index - 1) / 2.0
            start = index
    return ranks


def rank_ic(scores, returns):
    mask = np.isfinite(scores) & np.isfinite(returns)
    if mask.sum() < MIN_NAMES:
        return None
    left, right = _rank(scores[mask]), _rank(returns[mask])
    left, right = left - left.mean(), right - right.mean()
    denominator = math.sqrt(float(left @ left) * float(right @ right))
    return float(left @ right) / denominator if denominator else None


def quintile_spread(scores, returns, quantile=0.2):
    """Mean forward return of the top quantile minus the bottom quantile (equal weight)."""
    mask = np.isfinite(scores) & np.isfinite(returns)
    if mask.sum() < MIN_NAMES:
        return None
    ordered = returns[mask][np.argsort(scores[mask], kind="mergesort")]
    count = max(1, int(len(ordered) * quantile))
    return float(ordered[-count:].mean() - ordered[:count].mean())


def top_excess(scores, returns, quantile=0.1):
    """Top-decile mean return minus the all-name mean: what a long-only book would see."""
    mask = np.isfinite(scores) & np.isfinite(returns)
    if mask.sum() < MIN_NAMES:
        return None
    ordered = returns[mask][np.argsort(scores[mask], kind="mergesort")]
    count = max(1, int(len(ordered) * quantile))
    return float(ordered[-count:].mean() - ordered.mean())


def newey_west_t(values, lags):
    """t-stat of the mean with a Bartlett-kernel long-run variance (lags >= 0)."""
    values = np.asarray([v for v in values if v is not None], dtype=float)
    count = len(values)
    if count < 3:
        return None
    centered = values - values.mean()
    variance = float(centered @ centered) / count
    for lag in range(1, min(lags, count - 1) + 1):
        weight = 1 - lag / (lags + 1)
        variance += 2 * weight * float(centered[lag:] @ centered[:-lag]) / count
    if variance <= 0:
        return None
    return float(values.mean() / math.sqrt(variance / count))


def summarize(series, periods_per_year=12):
    values = np.array([v for v in series if v is not None], dtype=float)
    if len(values) < 3:
        return {"periods": int(len(values)), "mean_ic": None, "icir": None, "t_stat": None,
                "hit_rate": None}
    mean, std = float(values.mean()), float(values.std(ddof=1))
    return {
        "periods": int(len(values)),
        "mean_ic": round(mean, 4),
        "icir": round(mean / std * math.sqrt(periods_per_year), 3) if std else None,
        "t_stat": round(mean / std * math.sqrt(len(values)), 2) if std else None,
        "hit_rate": round(float((values > 0).mean()), 3),
    }


def _sharpe(series):
    values = np.array([v for v in series if v is not None], dtype=float)
    if len(values) < 3 or values.std(ddof=1) == 0:
        return None, len(values), 0.0, 3.0
    mean, std = values.mean(), values.std(ddof=1)
    z = (values - mean) / std
    return float(mean / std), len(values), float((z ** 3).mean()), float((z ** 4).mean())


# --------------------------------------------------------------------------- part A

def load_panel(path=PANEL_PATH, legs=LEGS, common_names=False):
    """Dense per-period arrays: leg matrix (names x legs, NaN = unresolved) + forward return.

    ``common_names`` keeps only names every competitor can score (market_behavior resolved AND at
    least one fundamentals leg resolved), so fundamentals-only, market-only and blended configs
    are all graded on the identical stocks and periods instead of on whatever each can score.
    """
    payload = json.load(open(path))
    horizon = payload.get("primary_horizon", "21d")
    periods = []
    for period in payload["periods"]:
        forwards = (period.get("forward_returns_by_horizon") or {}).get(horizon)
        forwards = forwards if isinstance(forwards, dict) else period.get("forward_returns") or {}
        tickers = [t for t in forwards if forwards[t] is not None and t in period["leg_scores"]]
        if len(tickers) < MIN_NAMES:
            continue
        matrix = np.full((len(tickers), len(legs)), np.nan)
        for row, ticker in enumerate(tickers):
            scores = period["leg_scores"][ticker]
            for column, leg in enumerate(legs):
                if scores.get(leg) is not None:
                    matrix[row, column] = scores[leg]
        returns = np.array([forwards[t] for t in tickers], dtype=float)
        if common_names:
            fundamental = [legs.index(leg) for leg in legs if leg not in ("market_behavior", "news_sentiment")]
            keep = np.isfinite(matrix[:, legs.index("market_behavior")]) & \
                np.isfinite(matrix[:, fundamental]).any(axis=1)
            if keep.sum() < MIN_NAMES:
                continue
            matrix, returns = matrix[keep], returns[keep]
        periods.append({"date": period["date"], "legs": matrix, "returns": returns})
    return periods


def blend(matrix, weights):
    """Weighted mean over resolved legs, renormalized per row (evaluation.composite_score)."""
    weights = np.asarray(weights, dtype=float)
    present = np.isfinite(matrix) & (weights > 0)
    total = (present * weights).sum(axis=1)
    value = np.where(present, matrix, 0.0) @ weights
    with np.errstate(invalid="ignore", divide="ignore"):
        score = value / total
    score[total == 0] = np.nan
    return score


def production_weights(legs=LEGS):
    settings = load_json("settings.json", from_config=True) or {}
    ranking = settings.get("ranking_weights", {})
    category = settings.get("fundamentals", {}).get("category_weights", {})
    weights = {leg: float(ranking.get("fundamentals", 0)) * float(category.get(leg, 0)) for leg in legs}
    weights["market_behavior"] = float(ranking.get("market_behavior", 0))
    weights["news_sentiment"] = float(ranking.get("news_sentiment", 0))
    return weights


def evaluate_weights(periods, weights):
    """Per-period IC, quintile spread and top-decile excess for one fixed weight vector."""
    vector = np.array([weights.get(leg, 0.0) for leg in LEGS])
    out = {"ic": [], "spread": [], "excess": []}
    for period in periods:
        score = blend(period["legs"], vector)
        out["ic"].append(rank_ic(score, period["returns"]))
        out["spread"].append(quintile_spread(score, period["returns"]))
        out["excess"].append(top_excess(score, period["returns"]))
    return out


def _report_row(name, series, indices, trials, note=None):
    """Summary of a config over the period indices it is graded on."""
    ic = [series["ic"][i] for i in indices]
    spread = [series["spread"][i] for i in indices]
    excess = [series["excess"][i] for i in indices]
    sharpe, count, skew, kurt = _sharpe(spread)
    deflated = deflated_sharpe_ratio(sharpe, observations=count, trials=trials, skew=skew,
                                     kurtosis=kurt) if sharpe is not None else None
    row = {"config": name, **summarize(ic),
           "mean_quintile_spread_pct": None if not any(v is not None for v in spread)
           else round(100 * float(np.mean([v for v in spread if v is not None])), 2),
           "mean_top_decile_excess_pct": None if not any(v is not None for v in excess)
           else round(100 * float(np.mean([v for v in excess if v is not None])), 2),
           "deflated_sharpe_prob": deflated, "trials_assumed": trials}
    if note:
        row["note"] = note
    return row


def dirichlet_candidates(count, seed, legs=LEGS, active=None):
    rng = np.random.default_rng(seed)
    active = active or legs
    columns = [LEGS.index(leg) for leg in active]
    draws = rng.dirichlet(np.ones(len(columns)), size=count)
    vectors = np.zeros((count, len(LEGS)))
    vectors[:, columns] = draws
    return vectors


def walk_forward_pick(series_by_candidate, count, selector, warmup=MIN_TRAIN_PERIODS):
    """For each period t >= warm-up, pick a candidate using only periods < t - embargo."""
    picks, ic, spread, excess = {}, {}, {}, {}
    for t in range(warmup, count):
        train = range(0, t - EMBARGO)
        choice = selector(train)
        picks[t] = choice
        ic[t] = series_by_candidate[choice]["ic"][t]
        spread[t] = series_by_candidate[choice]["spread"][t]
        excess[t] = series_by_candidate[choice]["excess"][t]
    return picks, ic, spread, excess


def _icir(values):
    values = [v for v in values if v is not None]
    if len(values) < 3:
        return -9.0
    std = float(np.std(values, ddof=1))
    return float(np.mean(values) / std) if std else -9.0


def run_part_a(trials=300, seed=7, panel_path=PANEL_PATH, common_names=True):
    periods = load_panel(panel_path, common_names=common_names)
    count = len(periods)
    # Expanding-window warm-up: 24 periods when the panel is long, half the panel when short.
    warmup = MIN_TRAIN_PERIODS if count >= 2 * MIN_TRAIN_PERIODS else max(6, count // 2)
    underpowered = count - warmup < 20
    current = production_weights()
    active = [leg for leg in LEGS
              if np.isfinite(np.concatenate([p["legs"][:, LEGS.index(leg)] for p in periods])).any()]
    dead_legs = [leg for leg in LEGS if leg not in active]
    current_active = {leg: current[leg] for leg in active}
    total = sum(current_active.values())
    current_active = {leg: weight / total for leg, weight in current_active.items()}

    named = {"current": current_active}
    named["equal_weight"] = {leg: 1 / len(active) for leg in active}
    for leg in active:
        named[f"only_{leg}"] = {leg: 1.0}
    fundamentals = [leg for leg in active if leg != "market_behavior"]
    named["fundamentals_only"] = {leg: current_active[leg] for leg in fundamentals}
    named["quality_only"] = {leg: 1.0 for leg in ("profitability", "financial_health",
                                                  "accounting_quality") if leg in active}
    named["value_plus_quality"] = {leg: 1.0 for leg in ("valuation", "profitability") if leg in active}
    named["market_heavy_50"] = {**{leg: 0.5 * current_active[leg] / (1 - current_active["market_behavior"])
                                   for leg in fundamentals}, "market_behavior": 0.5}
    for leg in active:
        for factor in (0.0, 0.5, 1.5, 2.0):
            scaled = dict(current_active)
            scaled[leg] = scaled[leg] * factor
            if sum(scaled.values()) > 0:
                named[f"{leg}_x{factor:g}"] = scaled

    evaluated = {name: evaluate_weights(periods, weights) for name, weights in named.items()}

    vectors = dirichlet_candidates(trials, seed, active=active)
    candidate_series = [evaluate_weights(periods, dict(zip(LEGS, vector))) for vector in vectors]

    all_idx = list(range(count))
    oos_idx = list(range(warmup, count))
    half = len(oos_idx) // 2
    total_trials = len(named) + trials

    # IC-weighted: weights proportional to trailing positive per-leg mean IC.
    leg_series = {leg: evaluate_weights(periods, {leg: 1.0})["ic"] for leg in active}

    def ic_weighted_weights(train):
        raw = {leg: max(0.0, float(np.mean([v for v in (leg_series[leg][i] for i in train)
                                           if v is not None] or [0.0]))) for leg in active}
        return raw if sum(raw.values()) > 0 else dict(current_active)

    ic_weighted_ic, ic_weighted_spread, ic_weighted_excess, ic_weight_history = {}, {}, {}, {}
    for t in oos_idx:
        weights = ic_weighted_weights(range(0, t - EMBARGO))
        ic_weight_history[t] = weights
        result = evaluate_weights([periods[t]], weights)
        ic_weighted_ic[t], ic_weighted_spread[t], ic_weighted_excess[t] = (
            result["ic"][0], result["spread"][0], result["excess"][0])
    evaluated["ic_weighted_wf"] = {"ic": [ic_weighted_ic.get(i) for i in all_idx],
                                   "spread": [ic_weighted_spread.get(i) for i in all_idx],
                                   "excess": [ic_weighted_excess.get(i) for i in all_idx]}

    picks, search_ic, search_spread, search_excess = walk_forward_pick(
        candidate_series, count,
        lambda train: max(range(trials), key=lambda k: _icir([candidate_series[k]["ic"][i] for i in train])),
        warmup=warmup)
    evaluated["dirichlet_best_wf"] = {"ic": [search_ic.get(i) for i in all_idx],
                                      "spread": [search_spread.get(i) for i in all_idx],
                                      "excess": [search_excess.get(i) for i in all_idx]}
    distinct_picks = len(set(picks.values()))

    def table(indices, label):
        rows = []
        for name, series in evaluated.items():
            fitted = name.endswith("_wf")
            note = "walk-forward fitted, scored out-of-sample only" if fitted else None
            rows.append(_report_row(name, series, [i for i in indices if series["ic"][i] is not None],
                                    total_trials if fitted else len(named), note))
        rows.sort(key=lambda row: (row["icir"] is None, -(row["icir"] or 0)))
        return {"window": label, "periods": len(indices), "rows": rows}

    # Per-leg attribution on the full panel: own IC, and drop-one delta for the current blend.
    full_ic = evaluated["current"]["ic"]
    attribution = {}
    for leg in active:
        own = summarize(leg_series[leg])
        without = {k: v for k, v in current_active.items() if k != leg}
        dropped = evaluate_weights(periods, without)["ic"]
        pairs = [(a, b) for a, b in zip(full_ic, dropped) if a is not None and b is not None]
        delta = float(np.mean([a - b for a, b in pairs])) if pairs else None
        coverage = float(np.mean([np.isfinite(p["legs"][:, LEGS.index(leg)]).mean() for p in periods]))
        attribution[leg] = {"weight": round(current_active[leg], 4), "own": own,
                            "delta_ic_when_present": None if delta is None else round(delta, 4),
                            "mean_name_coverage": round(coverage, 3)}

    return {
        "universe": "common names (market_behavior + >=1 fundamentals leg)" if common_names
        else "all scored names per config (samples differ between configs)",
        "mean_names_per_period": round(float(np.mean([len(p["returns"]) for p in periods])), 1),
        "panel_periods": count, "walk_forward_warmup": warmup,
        "oos_periods": count - warmup,
        "underpowered": underpowered,
        "underpowered_note": "fewer than 20 out-of-sample periods: fitted rows are illustrative, "
                             "no ranking between configs is statistically supported" if underpowered else None,
        "first_period": periods[0]["date"], "last_period": periods[-1]["date"],
        "legs_with_data": active, "legs_without_data": dead_legs,
        "current_weights_renormalized_over_live_legs": {k: round(v, 4) for k, v in current_active.items()},
        "trials": {"fixed_configs": len(named), "dirichlet_draws": trials, "seed": seed,
                   "distinct_walk_forward_picks": distinct_picks},
        "full_window": table(all_idx, "all periods (fixed configs are not fitted; *_wf rows are OOS-only)"),
        "oos_window": table(oos_idx, f"periods {warmup}+ (all configs scored on identical periods)"),
        "oos_first_half": table(oos_idx[:half], "OOS first half"),
        "oos_second_half": table(oos_idx[half:], "OOS second half"),
        "leg_attribution": attribution,
        "last_ic_weights": {leg: round(w / sum(ic_weight_history[oos_idx[-1]].values()), 4)
                            for leg, w in ic_weight_history[oos_idx[-1]].items()},
    }


# --------------------------------------------------------------------------- part B

def _screen_defs():
    from research_screens_v2 import MOMENTUM_WEIGHTS, TACTICAL_WEIGHTS
    from swing_signals import SWING_WEIGHTS
    import earnings_timeliness_pit_store as etps
    import momentum_pit_store as mps
    import swing_pit_store as sps
    return {
        "swing": (sps, "composite_z", dict(SWING_WEIGHTS), 14, "z"),
        "earnings_timeliness": (etps, "tactical_score", dict(TACTICAL_WEIGHTS), 30, "rank"),
        "momentum": (mps, "score", dict(MOMENTUM_WEIGHTS), 30, "z"),
    }


def _load_store(module):
    out = []
    for date in module.snapshot_dates():
        rows = module.load_snapshot(date) or []
        if rows:
            out.append((date, rows))
    return out


def _forward_pairs(snapshots, horizon_days):
    """(start_idx, end_idx) pairs: nearest later snapshot at least ``horizon_days`` out."""
    stamps = [datetime.fromisoformat(d).replace(tzinfo=timezone.utc).timestamp() for d, _ in snapshots]
    pairs = []
    for i, start in enumerate(stamps):
        target = start + horizon_days * 86400
        end = next((j for j in range(i + 1, len(stamps)) if stamps[j] >= target), None)
        if end is not None:
            pairs.append((i, end))
    return pairs


def run_part_b():
    report = {}
    for name, (module, composite_field, weights, horizon, _scale) in _screen_defs().items():
        snapshots = _load_store(module)
        pairs = _forward_pairs(snapshots, horizon)
        legs = list(weights)
        span_days = (datetime.fromisoformat(snapshots[-1][0]) - datetime.fromisoformat(snapshots[0][0])).days

        def period_ic(start, end, scorer):
            end_prices = {r["ticker"]: r.get("price") for r in snapshots[end][1]}
            scores, returns = [], []
            for row in snapshots[start][1]:
                price, later = row.get("price"), end_prices.get(row["ticker"])
                if not price or not later:
                    continue
                scores.append(scorer(row))
                returns.append(later / price - 1)
            return rank_ic(np.array(scores, dtype=float), np.array(returns, dtype=float))

        def composite(row):
            value = row.get(composite_field)
            return np.nan if value is None else float(value)

        def weighted(active):
            def scorer(row):
                present = {leg: w for leg, w in active.items() if row.get(leg) is not None and w > 0}
                total = sum(present.values())
                return sum(float(row[leg]) * w for leg, w in present.items()) / total if total else np.nan
            return scorer

        def variant_row(label, scorer):
            series = [period_ic(s, e, scorer) for s, e in pairs]
            clean = [v for v in series if v is not None]
            lag = max(1, int(round(horizon / max(1, span_days / max(1, len(snapshots) - 1)))))
            non_overlap = []
            last_end = -1
            for (s, e), value in zip(pairs, series):
                if value is not None and s >= last_end:
                    non_overlap.append(value)
                    last_end = e
            return {"config": label, **summarize(series),
                    "newey_west_t": None if len(clean) < 3 else round(newey_west_t(clean, lag) or 0, 2),
                    "independent_windows": len(non_overlap),
                    "independent_mean_ic": None if not non_overlap else round(float(np.mean(non_overlap)), 4)}

        variants = [variant_row("published_composite", composite),
                    variant_row("current_weights_recomputed", weighted(weights)),
                    variant_row("equal_weights", weighted({leg: 1.0 for leg in legs}))]
        own = {leg: variant_row(f"only_{leg}", weighted({leg: 1.0})) for leg in legs}
        negative = [leg for leg in legs if (own[leg]["mean_ic"] or 0) < 0]
        if negative and len(negative) < len(legs):
            kept = {leg: w for leg, w in weights.items() if leg not in negative}
            variants.append(variant_row("drop_negative_legs(in-sample, illustrative)", weighted(kept)))
        report[name] = {
            "snapshots": len(snapshots), "span_days": span_days, "horizon_days": horizon,
            "overlapping_periods": len(pairs),
            "effective_independent_windows": round(span_days / horizon, 1),
            "variants": variants,
            "legs": {leg: {"weight": weights[leg], **{k: own[leg][k] for k in
                     ("mean_ic", "icir", "newey_west_t", "independent_windows")}} for leg in legs},
            "caveat": "stores hold only each screen's published top rows (range-restricted "
                      "sample); ~%s independent windows; descriptive only" % round(span_days / horizon, 1),
        }
    return report


# --------------------------------------------------------------------------- main

def build_report(trials=300, seed=7):
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "method": __doc__.strip().split("\n\n")[0],
        "part_a_main_model": run_part_a(trials=trials, seed=seed, common_names=True),
        "part_a_all_names": run_part_a(trials=trials, seed=seed, common_names=False),
        "part_b_screens": run_part_b(),
        "disclosures": [
            "Part A leg scores are pre-modifier. Fundamental legs resolve for only a minority of "
            "names per period (the pre-2026-08-24 enrichment cap), so fundamentals blends are "
            "graded on a selected subset; market_behavior covers the whole universe.",
            "growth and news_sentiment legs have no historical data in the panel and are excluded; "
            "current weights are renormalized over the live legs.",
            "No production weight is changed by this report. Per docs/VALIDATION-METHODOLOGY.md a "
            "change needs out-of-sample IC improvement after deflation for the trials run here.",
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--trials", type=int, default=300)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args(argv)
    report = build_report(args.trials, args.seed)
    if not args.no_write:
        os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
        with open(REPORT_PATH, "w") as handle:
            json.dump(report, handle, indent=1, default=str)
    LOG.info("weight_lab: report built")
    return report


if __name__ == "__main__":
    main()
