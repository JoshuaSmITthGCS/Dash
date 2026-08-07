"""Validate a scoring change by measuring whether the score predicts forward returns.

The wrong way to evaluate a scoring model is the tempting one: run a backtest, look at the
equity curve, ship it if the line goes up. A single equity curve from a config you tuned is
not evidence - it is the best of however many configurations you tried, and you will have
tried a lot.

What this module measures instead:

  * **Rank information coefficient** - the Spearman correlation between score and forward
    return, computed cross-sectionally each period. This is the quantity in Grinold & Kahn's
    fundamental law of active management (IR is approximately IC times the square root of
    breadth). Spearman rather than Pearson because the model only ever claims a monotonic
    score-to-return relationship, and rank correlation is robust to the outliers that
    dominate return distributions. A mean monthly rank IC around 0.03-0.05 is the
    practitioner's threshold for a signal worth having on a broad universe.
  * **ICIR** - mean IC over the standard deviation of IC, annualized. Consistency matters
    more than one good quarter.
  * **Quantile spread and monotonicity** - top-minus-bottom decile forward return, plus
    whether the deciles actually line up in order. A score that only works at the extremes
    is a screen, not a ranking.
  * **Deflated Sharpe ratio** (Bailey & Lopez de Prado, *JPM* 40(5), 2014), which corrects
    for selection bias under multiple testing and for non-normal returns - the two things
    that make a tuned backtest look better than it is.
  * **Probability of backtest overfitting** via combinatorially-symmetric cross-validation
    (Bailey, Borwein, Lopez de Prado & Zhu, *Journal of Computational Finance* 20(4), 2017).

Because tuning means trying many configurations, the significance hurdle is raised
accordingly: Harvey, Liu & Zhu argue for a t-statistic near 3 rather than 2. The shipping
rule this module encodes is simple - a change ships only if it improves *deflated*
out-of-sample IC.
"""

import json
import os
from datetime import datetime, timezone
from itertools import combinations
from math import erf, exp, sqrt
from statistics import NormalDist

from common import LOG, STORE_DIR, save_json

EVAL_DIR = os.path.join(STORE_DIR, "evaluation")
PAPER_LOG = "paper_trading.jsonl"
# Grinold-Kahn worked examples use IC around 0.04; below roughly 0.02 a bucket is not
# earning the weight it is being given.
MEANINGFUL_IC = 0.02


# ---------------- rank correlation ----------------

def rank(values):
    """Fractional ranks, averaging ties. The basis of every Spearman number below."""
    indexed = sorted(range(len(values)), key=lambda index: values[index])
    ranks = [0.0] * len(values)
    position = 0
    while position < len(indexed):
        end = position
        while end + 1 < len(indexed) and values[indexed[end + 1]] == values[indexed[position]]:
            end += 1
        shared = (position + end) / 2 + 1
        for index in range(position, end + 1):
            ranks[indexed[index]] = shared
        position = end + 1
    return ranks


def pearson(left, right):
    n = len(left)
    if n < 3:
        return None
    mean_left, mean_right = sum(left) / n, sum(right) / n
    covariance = sum((a - mean_left) * (b - mean_right) for a, b in zip(left, right))
    variance_left = sum((a - mean_left) ** 2 for a in left)
    variance_right = sum((b - mean_right) ** 2 for b in right)
    if variance_left <= 0 or variance_right <= 0:
        return None
    return covariance / sqrt(variance_left * variance_right)


def rank_ic(scores, forward_returns):
    """Spearman correlation between score and forward return for one period.

    Pairs where either side is missing are dropped rather than filled: an imputed return is
    an invented observation, and inventing observations is how a weak signal starts looking
    strong.
    """
    pairs = [(score, forward) for score, forward in zip(scores, forward_returns)
             if score is not None and forward is not None]
    if len(pairs) < 5:
        return None
    return pearson(rank([pair[0] for pair in pairs]), rank([pair[1] for pair in pairs]))


def ic_summary(ic_series, periods_per_year=12):
    """Mean IC, its volatility, ICIR, and a t-statistic against the multiple-testing bar."""
    values = [value for value in ic_series if value is not None]
    if len(values) < 2:
        return {"periods": len(values), "mean_ic": values[0] if values else None,
                "ic_std": None, "icir": None, "t_stat": None, "meaningful": False}
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    deviation = sqrt(variance)
    icir = (mean / deviation) * sqrt(periods_per_year) if deviation else None
    t_stat = (mean / deviation) * sqrt(len(values)) if deviation else None
    return {
        "periods": len(values),
        "mean_ic": round(mean, 4),
        "ic_std": round(deviation, 4),
        "icir": round(icir, 3) if icir is not None else None,
        "t_stat": round(t_stat, 3) if t_stat is not None else None,
        "hit_rate": round(sum(1 for value in values if value > 0) / len(values), 3),
        "meaningful": abs(mean) >= MEANINGFUL_IC,
        # Harvey, Liu & Zhu: with hundreds of candidate signals tested across the
        # literature, a t-stat of 2 is not a 5% false-positive rate. 3 is the honest bar.
        "clears_multiple_testing_bar": t_stat is not None and abs(t_stat) >= 3.0,
    }


# ---------------- quantile analysis ----------------

def quantile_buckets(scores, forward_returns, quantiles=5):
    """Average forward return per score quantile, top bucket first."""
    pairs = [(score, forward) for score, forward in zip(scores, forward_returns)
             if score is not None and forward is not None]
    if len(pairs) < quantiles * 2:
        return None
    pairs.sort(key=lambda pair: pair[0], reverse=True)
    size = len(pairs) / quantiles
    buckets = []
    for index in range(quantiles):
        start, end = int(round(index * size)), int(round((index + 1) * size))
        chunk = pairs[start:end]
        if not chunk:
            continue
        buckets.append({
            "quantile": index + 1,
            "count": len(chunk),
            "mean_forward_return": round(sum(pair[1] for pair in chunk) / len(chunk), 4),
            "mean_score": round(sum(pair[0] for pair in chunk) / len(chunk), 2),
        })
    return buckets


def quantile_spread(buckets):
    """Top-minus-bottom spread and whether the buckets are actually monotone.

    A good score should be monotone across quantiles, not merely good at the extremes.
    Non-monotonic deciles with a wide top-bottom gap usually mean the signal is picking up
    one concentrated effect, which is far more fragile than it looks in the headline number.
    """
    if not buckets or len(buckets) < 2:
        return None
    returns = [bucket["mean_forward_return"] for bucket in buckets]
    descending = all(earlier >= later for earlier, later in zip(returns, returns[1:]))
    inversions = sum(1 for earlier, later in zip(returns, returns[1:]) if earlier < later)
    return {
        "top_minus_bottom": round(returns[0] - returns[-1], 4),
        "monotonic": descending,
        "inversions": inversions,
        "buckets": buckets,
    }


# ---------------- overfitting controls ----------------

def _norm_cdf(value):
    return 0.5 * (1 + erf(value / sqrt(2)))


def expected_max_sharpe(trials, variance_of_trials):
    """Expected maximum Sharpe from ``trials`` independent strategies with zero true skill.

    This is the benchmark a tuned backtest must beat. Try enough weight combinations and one
    of them looks good by construction; this quantifies how good "by construction" already is.

    ``variance_of_trials`` is the variance of the *estimated* Sharpe ratios across the trials,
    in per-observation units - not 1.0. Getting that wrong is the easy way to make this
    function reject everything or accept everything.
    """
    if trials < 2:
        return 0.0
    euler = 0.5772156649015329
    quantile_a = NormalDist().inv_cdf(1 - 1 / trials)
    quantile_b = NormalDist().inv_cdf(1 - 1 / (trials * exp(1)))
    return sqrt(variance_of_trials) * ((1 - euler) * quantile_a + euler * quantile_b)


def deflated_sharpe_ratio(observed_sharpe, *, observations, trials=1, skew=0.0,
                          kurtosis=3.0, variance_of_trials=None):
    """Probability the observed Sharpe reflects real skill rather than selection and noise.

    Corrects for the two sources of inflation Bailey & Lopez de Prado identify: selection
    bias under multiple testing (via the expected maximum Sharpe above) and non-normally
    distributed returns (via skew and kurtosis in the standard error). Returns a probability
    in [0, 1]; below ~0.95 the result does not survive its own search process.

    Sharpe figures here are per-observation, not annualized - deflate before annualizing.
    When the spread of trial Sharpes is unknown, it defaults to the sampling variance of a
    per-observation Sharpe estimate under the null, which is approximately ``1/observations``.
    """
    if observations < 3 or observed_sharpe is None:
        return None
    if variance_of_trials is None:
        variance_of_trials = 1.0 / observations
    benchmark = expected_max_sharpe(trials, variance_of_trials) if trials > 1 else 0.0
    denominator = 1 - skew * observed_sharpe + ((kurtosis - 1) / 4) * observed_sharpe ** 2
    if denominator <= 0:
        return None
    statistic = ((observed_sharpe - benchmark) * sqrt(observations - 1)) / sqrt(denominator)
    return round(_norm_cdf(statistic), 4)


def probability_of_backtest_overfitting(performance_matrix, *, splits=8):
    """PBO via combinatorially-symmetric cross-validation.

    ``performance_matrix`` is ``[period][configuration]`` performance. CSCV splits the
    periods into ``splits`` blocks, forms every balanced in-sample/out-of-sample partition,
    picks the in-sample winner, and records where that winner lands out-of-sample. PBO is
    the share of partitions where the in-sample winner finishes below the out-of-sample
    median - that is, where the selection procedure itself produced the result.

    A PBO above roughly 0.5 means the tuning process is generating winners at random.
    """
    periods = len(performance_matrix)
    if periods < splits or splits % 2 or not performance_matrix[0]:
        return None
    configurations = len(performance_matrix[0])
    if configurations < 2:
        return None
    block_size = periods // splits
    blocks = [list(range(index * block_size,
                         (index + 1) * block_size if index < splits - 1 else periods))
              for index in range(splits)]

    below_median = total = 0
    for chosen in combinations(range(splits), splits // 2):
        in_sample = [row for index in chosen for row in blocks[index]]
        out_sample = [row for index in range(splits) if index not in chosen
                      for row in blocks[index]]
        if not in_sample or not out_sample:
            continue

        def mean_for(rows, configuration):
            values = [performance_matrix[row][configuration] for row in rows
                      if performance_matrix[row][configuration] is not None]
            return sum(values) / len(values) if values else None

        in_means = [mean_for(in_sample, configuration) for configuration in range(configurations)]
        scored = [(value, index) for index, value in enumerate(in_means) if value is not None]
        if not scored:
            continue
        best = max(scored)[1]
        out_means = [mean_for(out_sample, configuration) for configuration in range(configurations)]
        present = [value for value in out_means if value is not None]
        if out_means[best] is None or len(present) < 2:
            continue
        # Lopez de Prado's relative rank: rank r of the in-sample winner among N
        # out-of-sample results (1 = worst), scaled by N+1 so the statistic is unbiased
        # under the null. Dividing by N instead skews PBO downward on small N.
        worse_or_equal = sum(1 for value in present if value <= out_means[best])
        relative_rank = worse_or_equal / (len(present) + 1)
        total += 1
        if relative_rank <= 0.5:
            below_median += 1
    return round(below_median / total, 4) if total else None


# ---------------- walk-forward driver ----------------

def walk_forward(periods, *, quantiles=5, periods_per_year=12, purge_periods=0, embargo_periods=0):
    """Evaluate a scored universe period by period.

    ``periods`` is a sequence of ``{"date", "scores": {ticker: score},
    "forward_returns": {ticker: return}}``. Each period is scored against the returns that
    followed it and nothing else, so there is no way for a later observation to leak in.

    ``embargo_periods`` drops that many periods off the *end* of the series - a period whose
    forward-return window is this recent may not be the full label horizon yet, so grading it
    would score against a partially-realized outcome. ``purge_periods`` keeps only every
    ``(purge_periods + 1)``-th period; with a label that spans ``purge_periods + 1`` periods
    (e.g. a 63-session/~3-month label against monthly periods, purge_periods=2), adjacent
    periods' forward-return windows overlap, and grading every one of them would feed
    pseudo-replicated (not independent) observations into the IC series and inflate its
    apparent statistical significance. Both default to 0 (every period graded, none
    dropped), which reproduces the exact prior behavior;
    ``validation_framework.DEFAULT_LABEL_OVERLAP_PERIODS`` is the recommended value for
    monthly periods graded against the primary 3M horizon.
    """
    if embargo_periods:
        periods = periods[:len(periods) - embargo_periods] if embargo_periods < len(periods) else []
    if purge_periods:
        periods = periods[::purge_periods + 1]
    ic_series, spreads, rows = [], [], []
    for period in periods:
        scores = period.get("scores") or {}
        forwards = period.get("forward_returns") or {}
        tickers = [ticker for ticker in scores if ticker in forwards]
        score_values = [scores[ticker] for ticker in tickers]
        return_values = [forwards[ticker] for ticker in tickers]
        period_ic = rank_ic(score_values, return_values)
        buckets = quantile_buckets(score_values, return_values, quantiles)
        spread = quantile_spread(buckets)
        ic_series.append(period_ic)
        if spread:
            spreads.append(spread["top_minus_bottom"])
        rows.append({"date": period.get("date"), "names": len(tickers),
                     "rank_ic": round(period_ic, 4) if period_ic is not None else None,
                     "quantile_spread": spread["top_minus_bottom"] if spread else None,
                     "monotonic": spread["monotonic"] if spread else None})

    summary = ic_summary(ic_series, periods_per_year)
    spread_mean = sum(spreads) / len(spreads) if spreads else None
    spread_sharpe = None
    if len(spreads) > 2:
        mean = sum(spreads) / len(spreads)
        variance = sum((value - mean) ** 2 for value in spreads) / (len(spreads) - 1)
        deviation = sqrt(variance)
        spread_sharpe = mean / deviation if deviation else None
    return {
        "periods": rows,
        "ic": summary,
        "mean_quantile_spread": round(spread_mean, 4) if spread_mean is not None else None,
        "monotonic_periods": sum(1 for row in rows if row["monotonic"]),
        "spread_sharpe_per_period": round(spread_sharpe, 3) if spread_sharpe is not None else None,
    }


def evaluate_candidate(periods, *, trials=1, quantiles=5, periods_per_year=12,
                       baseline=None):
    """Full verdict on one candidate configuration, deflation included.

    ``trials`` must be the honest count of configurations tried, not one. Understating it is
    the most common way a deflated Sharpe gets quietly re-inflated.
    """
    result = walk_forward(periods, quantiles=quantiles, periods_per_year=periods_per_year)
    deflated = deflated_sharpe_ratio(
        result["spread_sharpe_per_period"],
        observations=result["ic"]["periods"] or len(periods),
        trials=trials,
    )
    verdict = {
        **result,
        "trials_considered": trials,
        "deflated_sharpe_probability": deflated,
        # The shipping rule, stated in the output rather than left to memory.
        "ship": bool(
            result["ic"]["meaningful"]
            and result["ic"].get("clears_multiple_testing_bar")
            and (deflated is None or deflated >= 0.95)
            and (baseline is None or (result["ic"]["mean_ic"] or 0) > (baseline.get("mean_ic") or 0))
        ),
    }
    if not verdict["ship"]:
        reasons = []
        if not result["ic"]["meaningful"]:
            reasons.append(f"mean rank IC {result['ic']['mean_ic']} is below the "
                           f"{MEANINGFUL_IC} threshold for a signal worth its weight")
        if not result["ic"].get("clears_multiple_testing_bar"):
            reasons.append("t-statistic below 3, the bar appropriate after multiple testing")
        if deflated is not None and deflated < 0.95:
            reasons.append(f"deflated Sharpe probability {deflated} does not survive "
                           f"{trials} trials of selection")
        if baseline is not None and (result["ic"]["mean_ic"] or 0) <= (baseline.get("mean_ic") or 0):
            reasons.append("does not improve on the baseline out-of-sample IC")
        verdict["ship_blockers"] = reasons
    return verdict


# ---------------- paper trading ----------------

def log_paper_period(config_name, period_date, scores, *, quantiles=5, directory=EVAL_DIR):
    """Freeze a configuration and log the quantile portfolios it would have held.

    Between backtesting and trusting a change there should be a period where the config is
    frozen and its forward predictions are recorded before the returns are known. This
    writes that record; ``score_paper_log`` grades it once the returns exist.
    """
    os.makedirs(directory, exist_ok=True)
    ranked = sorted(((ticker, score) for ticker, score in scores.items() if score is not None),
                    key=lambda pair: pair[1], reverse=True)
    if not ranked:
        return None
    size = max(1, len(ranked) // quantiles)
    row = {
        "logged_at": datetime.now(timezone.utc).isoformat(),
        "config": config_name,
        "period": period_date,
        "universe": len(ranked),
        "top_quantile": [ticker for ticker, _ in ranked[:size]],
        "bottom_quantile": [ticker for ticker, _ in ranked[-size:]],
        "scores": {ticker: round(score, 2) for ticker, score in ranked},
    }
    path = os.path.join(directory, PAPER_LOG)
    with open(path, "a") as handle:
        handle.write(json.dumps(row, default=str) + "\n")
    return row


def read_paper_log(directory=EVAL_DIR):
    path = os.path.join(directory, PAPER_LOG)
    if not os.path.exists(path):
        return []
    rows = []
    with open(path) as handle:
        for line in handle:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    continue
    return rows


def score_paper_log(returns_by_period, *, config=None, directory=EVAL_DIR):
    """Grade logged paper periods against realized returns.

    ``returns_by_period`` maps a logged period to ``{ticker: realized_forward_return}``.
    Realized forward IC that falls well short of the backtest IC is the signal that the
    backtest was fitted rather than discovered - which is exactly what this is here to catch.
    """
    rows = [row for row in read_paper_log(directory)
            if config is None or row.get("config") == config]
    periods = []
    for row in rows:
        realized = returns_by_period.get(row.get("period"))
        if not realized:
            continue
        periods.append({"date": row["period"], "scores": row.get("scores", {}),
                        "forward_returns": realized})
    if not periods:
        return {"periods": 0, "note": "no logged periods have realized returns yet"}
    return {"config": config, "graded_periods": len(periods), **walk_forward(periods)}


def publish(report, name="evaluation.json"):
    """Write an evaluation report next to the other pipeline outputs."""
    save_json(name, report, to_store=True)
    LOG.info(f"Wrote {name}: mean rank IC {report.get('ic', {}).get('mean_ic')}, "
             f"ship={report.get('ship')}")
    return report
