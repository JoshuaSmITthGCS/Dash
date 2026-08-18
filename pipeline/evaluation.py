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
import math
import os
import random
from datetime import datetime, timezone
from itertools import combinations
from math import ceil, erf, exp, sqrt
from statistics import NormalDist

from common import LOG, STORE_DIR, save_json

EVAL_DIR = os.path.join(STORE_DIR, "evaluation")
PAPER_LOG = "paper_trading.jsonl"
# Grinold-Kahn worked examples use IC around 0.04; below roughly 0.02 a bucket is not
# earning the weight it is being given.
MEANINGFUL_IC = 0.02
TRADING_DAYS = 252


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
    """Mean IC, its volatility, ICIR, and a t-statistic against the multiple-testing bar.

    ``series`` carries the filtered per-period values themselves (not just the aggregates),
    so a caller can run a bootstrap confidence interval on the same values this summary's own
    t-statistic is computed from, without recomputing per-period IC a second time.
    """
    values = [value for value in ic_series if value is not None]
    if len(values) < 2:
        return {"periods": len(values), "mean_ic": values[0] if values else None,
                "ic_std": None, "icir": None, "t_stat": None, "meaningful": False,
                "series": values}
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
        "series": values,
    }


def bootstrap_ic_confidence_interval(ic_series, *, block_size=1, samples=2000, seed=0):
    """Block-bootstrap confidence interval on mean rank IC, nonparametric.

    ``ic_summary``'s t-statistic assumes the period IC series is approximately normal, which
    a short or skewed series does not have to be. This resamples the period-level IC values
    directly (with replacement, in contiguous blocks) rather than assuming a distribution, the
    same discipline ``block_bootstrap_return_ci`` applies to daily returns. ``block_size > 1``
    preserves period-to-period IC autocorrelation, when the caller has reason to think the
    signal's edge persists from one period to the next; the default of 1 treats periods as
    independent draws, the same assumption the analytic t-statistic already makes.
    """
    values = [value for value in ic_series if value is not None]
    n = len(values)
    if n < 10:
        return None
    rng = random.Random(seed)
    means = []
    for _ in range(samples):
        draw = []
        while len(draw) < n:
            start = rng.randrange(n)
            draw.extend(values[(start + offset) % n] for offset in range(block_size))
        means.append(sum(draw[:n]) / n)
    means.sort()
    lower = means[int(0.025 * samples)]
    upper = means[min(samples - 1, int(0.975 * samples))]
    return {
        "observations": n, "block_size": block_size, "samples": samples,
        "mean_ic": round(sum(values) / n, 4),
        "ic_ci_95": [round(lower, 4), round(upper, 4)],
        "probability_ic_positive": round(sum(1 for value in means if value > 0) / samples, 4),
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


def probabilistic_sharpe_ratio(observed_sharpe, *, observations, benchmark_sharpe=0.0,
                               skew=0.0, kurtosis=3.0):
    """Probability the true Sharpe exceeds ``benchmark_sharpe`` given this sample.

    Bailey & Lopez de Prado (2012). The deflated Sharpe above asks whether a result survives
    the *search* that produced it; this asks the prior question - whether a single track
    record is long enough to distinguish its Sharpe from the benchmark at all. Non-normality
    enters through the standard error: negative skew and fat tails widen it, which is why a
    strategy that sells tail risk needs a longer record to prove the same Sharpe.

    Sharpe figures are per-observation, not annualized.
    """
    if observed_sharpe is None or observations < 3:
        return None
    variance = 1 - skew * observed_sharpe + ((kurtosis - 1) / 4) * observed_sharpe ** 2
    if variance <= 0:
        return None
    statistic = ((observed_sharpe - benchmark_sharpe) * sqrt(observations - 1)) / sqrt(variance)
    return round(_norm_cdf(statistic), 4)


def minimum_track_record_length(observed_sharpe, *, benchmark_sharpe=0.0, skew=0.0,
                                kurtosis=3.0, confidence=0.95):
    """Observations needed before the observed Sharpe is distinguishable from the benchmark.

    The inverse of the probabilistic Sharpe: instead of "how confident am I now", it answers
    "how long until the claim is defensible". Reporting this next to a young track record is
    the honest alternative to reporting the Sharpe as though the sample size were adequate.

    Returns None when the observed Sharpe does not exceed the benchmark - no amount of
    additional data makes a claim that is not there.
    """
    if observed_sharpe is None or observed_sharpe <= benchmark_sharpe:
        return None
    variance = 1 - skew * observed_sharpe + ((kurtosis - 1) / 4) * observed_sharpe ** 2
    if variance <= 0:
        return None
    quantile = NormalDist().inv_cdf(confidence)
    return int(ceil(1 + variance * (quantile / (observed_sharpe - benchmark_sharpe)) ** 2))


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


# ---------------- robustness beyond PBO ----------------
#
# PBO asks whether the search that produced the winning configuration was itself noise.
# These four answer a related but distinct set of questions: how wide is the honest
# uncertainty band around a short return series (bootstrap CI), does the best-searched
# configuration beat the field by more than an exhaustive search would produce by chance
# alone (Reality Check / SPA), is any one stretch of the sample doing all the work (rolling
# Sharpe), and does a VaR forecast actually get breached at the rate it claims (Kupiec /
# Christoffersen). None of these need a live sample - they all run on the backtest.

def block_bootstrap_return_ci(returns, *, block_size=21, samples=2000, seed=0,
                              periods_per_year=TRADING_DAYS):
    """Block-bootstrap confidence interval for annualized return and Sharpe.

    Resampling contiguous blocks (rather than individual days) preserves the short-run
    autocorrelation a day-by-day bootstrap would destroy - momentum and mean-reversion both
    leave a signature in consecutive returns that an i.i.d. resample erases. This gives a
    defensible interval on a return series far shorter than the 252 observations
    ``min_track_record_length`` would otherwise require before trusting a single Sharpe point
    estimate.
    """
    n = len(returns)
    if n < max(20, block_size * 2):
        return None
    rng = random.Random(seed)
    annualized_returns, sharpes = [], []
    for _ in range(samples):
        draw = []
        while len(draw) < n:
            start = rng.randrange(n)
            draw.extend(returns[(start + offset) % n] for offset in range(block_size))
        draw = draw[:n]
        mean = sum(draw) / n
        variance = sum((value - mean) ** 2 for value in draw) / n
        annualized_returns.append(mean * periods_per_year)
        sharpes.append((mean / sqrt(variance)) * sqrt(periods_per_year) if variance > 0 else 0.0)
    annualized_returns.sort()
    sharpes.sort()

    def interval(values):
        lo = values[int(0.025 * samples)]
        hi = values[min(samples - 1, int(0.975 * samples))]
        return lo, hi

    return_lo, return_hi = interval(annualized_returns)
    sharpe_lo, sharpe_hi = interval(sharpes)
    return {
        "observations": n, "block_size": block_size, "samples": samples,
        "mean_annualized_return_pct": round(sum(annualized_returns) / samples * 100, 3),
        "annualized_return_ci_95_pct": [round(return_lo * 100, 3), round(return_hi * 100, 3)],
        "mean_sharpe": round(sum(sharpes) / samples, 3),
        "sharpe_ci_95": [round(sharpe_lo, 3), round(sharpe_hi, 3)],
        "probability_sharpe_positive": round(sum(1 for value in sharpes if value > 0) / samples, 4),
        "probability_return_positive": round(
            sum(1 for value in annualized_returns if value > 0) / samples, 4),
    }


def _chi2_cdf_1df(statistic):
    """Chi-squared(1) CDF via its closed form: a chi-squared(1) variate is a squared normal."""
    if statistic <= 0:
        return 0.0
    return erf(sqrt(statistic / 2))


def _bernoulli_log_likelihood(probability, successes, trials):
    if trials == 0:
        return 0.0
    if probability <= 0 or probability >= 1:
        return 0.0 if successes in (0, trials) else float("-inf")
    return successes * math.log(probability) + (trials - successes) * math.log(1 - probability)


def kupiec_pof_test(breaches, observations, confidence=0.95):
    """Kupiec (1995) proportion-of-failures test: does the breach rate match VaR's coverage.

    A likelihood-ratio test of the observed breach rate against the rate a correctly
    calibrated VaR at ``confidence`` implies (``1 - confidence``), against chi-squared(1). A
    model that breaches far more, or far less, often than it claims fails this test in
    either direction - too few breaches is not a sign of a safe model, it is a sign of a
    VaR estimate wider than the data supports.
    """
    if observations < 20 or not 0 < confidence < 1:
        return None
    expected_p = 1 - confidence
    observed_p = breaches / observations
    ll_null = _bernoulli_log_likelihood(expected_p, breaches, observations)
    ll_alt = _bernoulli_log_likelihood(observed_p, breaches, observations)
    statistic = float("inf") if not math.isfinite(ll_null) or not math.isfinite(ll_alt) \
        else max(0.0, -2 * (ll_null - ll_alt))
    p_value = 0.0 if not math.isfinite(statistic) else round(1 - _chi2_cdf_1df(statistic), 4)
    return {
        "observations": observations, "breaches": breaches,
        "expected_breach_rate": round(expected_p, 4),
        "observed_breach_rate": round(observed_p, 4),
        "likelihood_ratio_statistic": round(statistic, 4) if math.isfinite(statistic) else None,
        "p_value": p_value,
        "miscalibrated_at_95": p_value < 0.05,
    }


def christoffersen_independence_test(breach_sequence):
    """Christoffersen (1998) independence test: do breaches cluster instead of scattering.

    A VaR model can pass Kupiec's rate test and still be wrong if its breaches arrive in
    runs - a regime the trailing window has not caught up to - rather than independently
    through time. Models the breach indicator as a two-state Markov chain and tests the
    transition probabilities against the null that today's breach says nothing about
    tomorrow's, via a likelihood-ratio statistic against chi-squared(1).
    """
    if len(breach_sequence) < 21:
        return None
    n00 = n01 = n10 = n11 = 0
    for prior, current in zip(breach_sequence, breach_sequence[1:]):
        if prior == 0 and current == 0:
            n00 += 1
        elif prior == 0 and current == 1:
            n01 += 1
        elif prior == 1 and current == 0:
            n10 += 1
        else:
            n11 += 1
    total_from_0, total_from_1 = n00 + n01, n10 + n11
    total = total_from_0 + total_from_1
    if total == 0:
        return None
    pi01 = n01 / total_from_0 if total_from_0 else 0.0
    pi11 = n11 / total_from_1 if total_from_1 else 0.0
    pi = (n01 + n11) / total
    ll_null = _bernoulli_log_likelihood(pi, n01 + n11, total)
    ll_alt = (_bernoulli_log_likelihood(pi01, n01, total_from_0)
              + _bernoulli_log_likelihood(pi11, n11, total_from_1))
    statistic = float("inf") if not math.isfinite(ll_null) or not math.isfinite(ll_alt) \
        else max(0.0, -2 * (ll_null - ll_alt))
    p_value = 0.0 if not math.isfinite(statistic) else round(1 - _chi2_cdf_1df(statistic), 4)
    return {
        "observations": total + 1,
        "transitions": {"no_breach_to_no_breach": n00, "no_breach_to_breach": n01,
                        "breach_to_no_breach": n10, "breach_to_breach": n11},
        "likelihood_ratio_statistic": round(statistic, 4) if math.isfinite(statistic) else None,
        "p_value": p_value,
        "clustered_at_95": p_value < 0.05,
    }


def var_backtest(returns, *, confidence=0.95, window=TRADING_DAYS):
    """Rolling historical VaR forecast against realized breaches, graded two ways.

    For every day past the first ``window`` observations, VaR is estimated from the trailing
    window alone - no look-ahead - and checked against the return that actually followed.
    Kupiec grades whether the resulting breach rate matches what ``confidence`` promises;
    Christoffersen grades whether the breaches are independent through time rather than
    clustered in one stretch the trailing window hadn't adapted to yet.
    """
    n = len(returns)
    if n < window + 21:
        return None
    breaches = []
    for end in range(window, n):
        trailing = sorted(returns[end - window:end])
        index = max(0, min(window - 1, int(round(window * (1 - confidence))) - 1))
        var_estimate = -trailing[index]
        breaches.append(1 if returns[end] < -var_estimate else 0)
    return {
        "confidence": confidence, "window": window, "forecasts": len(breaches),
        "breaches": sum(breaches),
        "breach_rate": round(sum(breaches) / len(breaches), 4),
        "expected_breach_rate": round(1 - confidence, 4),
        "kupiec_pof": kupiec_pof_test(sum(breaches), len(breaches), confidence),
        "christoffersen_independence": christoffersen_independence_test(breaches),
    }


def reality_check_spa(performance_matrix, *, samples=1000, block_size=3, seed=0):
    """White's Reality Check / Hansen's SPA test via a recentered stationary block bootstrap.

    ``performance_matrix`` is ``[period][configuration]`` performance - the same shape PBO
    reads, built from the same trial log every tuning round has added to. The benchmark each
    configuration is judged against is the per-period mean across every configuration
    searched: the outcome an exhaustive, undirected search would have produced by picking at
    random. The test statistic is Hansen's studentized max - the best configuration's mean
    outperformance over the field, scaled by its own sampling noise - and the bootstrap
    recenters each configuration's resampled outperformance to enforce the null that no
    configuration in the search genuinely beats the field. A low p-value means the winner
    survives the fact that this many configurations were tried; a high one means the winning
    margin is within what trying this many configurations would produce from noise alone.
    """
    periods = len(performance_matrix)
    if periods < 10 or not performance_matrix[0]:
        return None
    configurations = len(performance_matrix[0])
    if configurations < 2:
        return None
    period_means = []
    for row in performance_matrix:
        values = [value for value in row if value is not None]
        period_means.append(sum(values) / len(values) if values else None)
    complete = [t for t in range(periods) if period_means[t] is not None
                and all(performance_matrix[t][k] is not None for k in range(configurations))]
    if len(complete) < 10:
        return None
    outperformance = [[performance_matrix[t][k] - period_means[t] for k in range(configurations)]
                      for t in complete]
    total = len(outperformance)
    means = [sum(row[k] for row in outperformance) / total for k in range(configurations)]
    variances = [sum((row[k] - means[k]) ** 2 for row in outperformance) / total
                for k in range(configurations)]
    studentized = [means[k] / sqrt(variances[k] / total) if variances[k] > 1e-12 else 0.0
                  for k in range(configurations)]
    observed_statistic = max(studentized)
    best = studentized.index(observed_statistic)

    rng = random.Random(seed)
    exceed = 0
    for _ in range(samples):
        indices = []
        while len(indices) < total:
            start = rng.randrange(total)
            indices.extend((start + offset) % total for offset in range(block_size))
        indices = indices[:total]
        for k in range(configurations):
            boot_mean = sum(outperformance[t][k] for t in indices) / total - means[k]
            statistic = (boot_mean / sqrt(variances[k] / total)) if variances[k] > 1e-12 else 0.0
            if k == 0 or statistic > boot_max:
                boot_max = statistic
        if boot_max >= observed_statistic:
            exceed += 1
    p_value = round(exceed / samples, 4)
    return {
        "periods": total, "configurations": configurations, "samples": samples,
        "block_size": block_size, "best_configuration_index": best,
        "observed_statistic": round(observed_statistic, 4),
        "p_value": p_value, "survives_search_at_95": p_value < 0.05,
        "configuration_statistics": [round(value, 4) for value in studentized],
    }


# ---------------- leg diagnostics ----------------
#
# A composite score with five legs and hand-assigned weights is five claims, not one. These
# functions test each claim separately: whether a leg predicts anything on its own, what the
# composite loses when the leg is removed, and whether two legs are really the same leg
# wearing different labels. None of this needs live data - it runs on any scored panel with
# forward returns attached.


def composite_score(leg_scores, weights):
    """Weighted blend of leg scores, renormalized over whichever legs are present.

    Renormalization matters for the drop-one test: removing a leg must reweight the
    survivors rather than shrink every score toward zero, or the "damage" measured is
    arithmetic rather than informational.
    """
    usable = {leg: weight for leg, weight in weights.items()
              if weight and leg_scores.get(leg) is not None}
    total = sum(usable.values())
    if not total:
        return None
    return sum(leg_scores[leg] * weight for leg, weight in usable.items()) / total


def _period_ic(period, score_of):
    """Cross-sectional rank IC for one period under an arbitrary score function."""
    forwards = period.get("forward_returns") or {}
    pairs = [(score_of(ticker), forwards[ticker]) for ticker in forwards
             if score_of(ticker) is not None and forwards[ticker] is not None]
    if len(pairs) < 5:
        return None
    return rank_ic([pair[0] for pair in pairs], [pair[1] for pair in pairs])


def per_leg_ic(periods, legs=None, *, periods_per_year=12):
    """Standalone rank IC of every leg, so dead weight becomes visible.

    ``periods`` carry ``leg_scores`` as ``{ticker: {leg: score}}``. A leg whose own IC sits
    at zero is not contributing prediction; it is contributing weight.
    """
    legs = list(legs or sorted({leg for period in periods
                                for scores in (period.get("leg_scores") or {}).values()
                                for leg in scores}))
    output = {}
    for leg in legs:
        series = [_period_ic(period, lambda ticker, leg=leg, period=period:
                             ((period.get("leg_scores") or {}).get(ticker) or {}).get(leg))
                  for period in periods]
        output[leg] = ic_summary(series, periods_per_year)
    return output


def drop_one_leg_delta_ic(periods, weights, *, periods_per_year=12):
    """Marginal IC contribution of each leg: full composite IC minus the IC without it.

    This is the test that says whether assigned weights are defensible. A leg with a
    negative delta is actively hurting the composite - the blend predicts better once it is
    gone - and no amount of intuition about why the leg *should* work survives that.
    """
    def scores_for(period, active):
        return lambda ticker: composite_score(
            (period.get("leg_scores") or {}).get(ticker) or {}, active)

    full_series = [_period_ic(period, scores_for(period, weights)) for period in periods]
    full = ic_summary(full_series, periods_per_year)
    deltas = {}
    for leg in weights:
        remaining = {name: weight for name, weight in weights.items() if name != leg}
        if not remaining:
            continue
        without = ic_summary([_period_ic(period, scores_for(period, remaining))
                              for period in periods], periods_per_year)
        both_present = full["mean_ic"] is not None and without["mean_ic"] is not None
        deltas[leg] = {
            "weight": weights[leg],
            "mean_ic_without_leg": without["mean_ic"],
            "delta_ic": round(full["mean_ic"] - without["mean_ic"], 4) if both_present else None,
            "hurts_composite": bool(both_present and full["mean_ic"] < without["mean_ic"]),
        }
    return {"composite": full, "legs": deltas}


def leg_correlation_matrix(periods, legs=None):
    """Average cross-sectional Spearman correlation between every pair of legs.

    Two legs correlated above roughly 0.7 are one leg counted twice, which quietly doubles
    its weight in the composite and overstates how many independent bets are being made.
    """
    legs = list(legs or sorted({leg for period in periods
                                for scores in (period.get("leg_scores") or {}).values()
                                for leg in scores}))
    matrix = {left: {} for left in legs}
    redundant = []
    for left in legs:
        for right in legs:
            values = []
            for period in periods:
                leg_scores = period.get("leg_scores") or {}
                pairs = [(scores.get(left), scores.get(right)) for scores in leg_scores.values()
                         if scores.get(left) is not None and scores.get(right) is not None]
                if len(pairs) < 5:
                    continue
                correlation = pearson(rank([pair[0] for pair in pairs]),
                                      rank([pair[1] for pair in pairs]))
                if correlation is not None:
                    values.append(correlation)
            average = round(sum(values) / len(values), 4) if values else None
            matrix[left][right] = average
            if left < right and average is not None and average >= 0.7:
                redundant.append({"legs": [left, right], "correlation": average})
    return {"legs": legs, "matrix": matrix, "redundant_pairs": redundant}


def rank_autocorrelation(periods):
    """Spearman correlation of composite score ranks between consecutive periods.

    Turnover is decided here, before any trade is placed: a score that reshuffles its own
    ranking every period will produce turnover no execution improvement can rescue. High
    autocorrelation means the same names keep being chosen; low means the cost line is going
    to eat whatever the signal earns.
    """
    values = []
    for previous, current in zip(periods, periods[1:]):
        before, after = previous.get("scores") or {}, current.get("scores") or {}
        common = [ticker for ticker in before if ticker in after
                  and before[ticker] is not None and after[ticker] is not None]
        if len(common) < 5:
            continue
        correlation = pearson(rank([before[ticker] for ticker in common]),
                              rank([after[ticker] for ticker in common]))
        if correlation is not None:
            values.append(round(correlation, 4))
    if not values:
        return {"periods": 0, "mean_autocorrelation": None, "series": []}
    mean = sum(values) / len(values)
    return {"periods": len(values), "mean_autocorrelation": round(mean, 4),
            "implied_period_turnover": round(1 - mean, 4), "series": values}


# ---------------- horizon and cost economics ----------------

def ic_decay_curve(periods, horizons, *, periods_per_year=12):
    """Mean IC at each forward horizon, from periods carrying returns for several horizons.

    Where the edge lives is a different question from whether it exists. A signal whose IC
    peaks at 63 days and is noise at 1 day cannot be traded daily; one that decays by day 5
    cannot survive the cost of getting in.
    """
    curve = {}
    for label in horizons:
        series = []
        for period in periods:
            forwards = (period.get("forward_returns_by_horizon") or {}).get(label) or {}
            series.append(_period_ic({"forward_returns": forwards},
                                     lambda ticker, period=period: (period.get("scores") or {}).get(ticker)))
        curve[label] = ic_summary(series, periods_per_year)
    present = {label: summary["mean_ic"] for label, summary in curve.items()
               if summary["mean_ic"] is not None}
    return {
        "horizons": curve,
        "peak_horizon": max(present, key=present.get) if present else None,
    }


def effective_breadth(weights):
    """Inverse Herfindahl of a weight vector: how many equally-sized bets this really is.

    Twenty positions with one of them at 40% is not twenty bets. Reported alongside the
    top-10 concentration because the two disagree in exactly the cases worth noticing.
    """
    values = [float(weight) for weight in weights if weight is not None and float(weight) > 0]
    total = sum(values)
    if not total:
        return None
    shares = [value / total for value in values]
    return round(1 / sum(share * share for share in shares), 2)


def breakeven_gross_alpha(annual_turnover, round_trip_cost_bps):
    """Gross alpha the signal must produce annually just to cover its own trading.

    ``annual_turnover`` is one-way turnover per year expressed as a fraction of the
    portfolio (1.0 = the book replaced once). Printed next to the expected return the IC
    implies, this settles the strategy's viability arithmetically: if breakeven exceeds
    expected gross alpha, no amount of signal work fixes it, because the signal is already
    assumed.
    """
    if annual_turnover is None or round_trip_cost_bps is None:
        return None
    return round(annual_turnover * round_trip_cost_bps / 100, 3)


def alpha_cost_crossover(spread_by_horizon, *, round_trip_cost_bps, trading_days_by_horizon,
                         trading_days_per_year=252):
    """Where the gross quantile spread starts to outrun the cost of harvesting it.

    Each horizon is annualized on its own rebalance frequency: a 1-day spread is worth 252
    of itself a year but also pays the round trip 252 times. The crossover is the shortest
    horizon whose annualized spread survives its own annualized cost - the number that
    decides how often this signal can be traded at all.
    """
    rows = []
    for label, spread in spread_by_horizon.items():
        days = trading_days_by_horizon.get(label)
        if spread is None or not days:
            continue
        rebalances = trading_days_per_year / days
        gross = spread * rebalances
        cost = round_trip_cost_bps / 10_000 * rebalances
        rows.append({
            "horizon": label,
            "trading_days": days,
            "rebalances_per_year": round(rebalances, 2),
            "gross_annualized_spread": round(gross, 4),
            "annualized_cost": round(cost, 4),
            "net_annualized_spread": round(gross - cost, 4),
        })
    rows.sort(key=lambda row: row["trading_days"])
    profitable = [row for row in rows if row["net_annualized_spread"] > 0]
    return {
        "rows": rows,
        "crossover_horizon": profitable[0]["horizon"] if profitable else None,
        "round_trip_cost_bps": round_trip_cost_bps,
    }


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
