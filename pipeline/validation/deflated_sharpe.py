"""Deflated Sharpe ratio and probability of backtest overfitting.

Two statistics, both prerequisites rather than extras. No variant comparison in this
repository ships without them.

**Deflated Sharpe ratio** (Bailey and Lopez de Prado, Journal of Portfolio Management 40(5),
2014). An observed Sharpe ratio is not evidence on its own once you know how many strategies
were tried to find it. The DSR tests the observed Sharpe against the Sharpe the best of N
unskilled trials would be expected to produce, and corrects for the non-normality of the
return series through its own skew and kurtosis, which matter because a Sharpe ratio's
sampling distribution is not normal when returns are not.

**Probability of backtest overfitting** (Bailey, Borwein, Lopez de Prado and Zhu, Notices of
the American Mathematical Society 61(5), 2014). Combinatorially symmetric cross-validation
splits the return matrix into blocks, forms every balanced train/test partition, and asks how
often the variant that looked best in-sample ranks below median out-of-sample. A high PBO says
the selection procedure itself is the thing generating the result.

Implemented on the standard library plus numpy, which is already a declared dependency. The
normal distribution comes from statistics.NormalDist rather than scipy, so this module runs
anywhere the pipeline runs.
"""

from __future__ import annotations

import itertools
import math
from statistics import NormalDist

NORMAL = NormalDist()
EULER_MASCHERONI = 0.5772156649015329


def _moments(returns):
    count = len(returns)
    mean = sum(returns) / count
    variance = sum((value - mean) ** 2 for value in returns) / (count - 1)
    deviation = math.sqrt(variance)
    if not deviation:
        return mean, 0.0, 0.0, 0.0
    third = sum(((value - mean) / deviation) ** 3 for value in returns) / count
    fourth = sum(((value - mean) / deviation) ** 4 for value in returns) / count
    return mean, deviation, third, fourth


def sharpe_ratio(returns, risk_free=0.0):
    """Sharpe ratio in the units the returns are given in, or None below two observations.

    Sample standard deviation with the Bessel correction, so this is the same estimator the
    DSR's variance correction assumes.
    """
    returns = [float(value) for value in returns]
    if len(returns) < 2:
        return None
    excess = [value - risk_free for value in returns]
    mean, deviation, _skew, _kurtosis = _moments(excess)
    return mean / deviation if deviation else None


def expected_maximum_sharpe(trial_variance, trials):
    """Expected maximum Sharpe of ``trials`` independent unskilled strategies.

    The order-statistic approximation from Bailey and Lopez de Prado 2014: with N trials whose
    true Sharpe is zero and whose estimates have variance V, the best of them is expected to
    land at sqrt(V) times a function of N alone. This is the bar the observed Sharpe has to
    clear before it is evidence of anything, and it rises with every variant tried.
    """
    if trials < 2 or trial_variance <= 0:
        return 0.0
    return math.sqrt(trial_variance) * (
        (1 - EULER_MASCHERONI) * NORMAL.inv_cdf(1 - 1 / trials)
        + EULER_MASCHERONI * NORMAL.inv_cdf(1 - 1 / (trials * math.e)))


def deflated_sharpe_ratio(returns, *, trials, trial_variance=None, benchmark_sharpe=None):
    """Probability the strategy's true Sharpe is above the benchmark, given the trial count.

    ``trials`` is the number of configurations tried to arrive at this one, and it is the
    whole point: quoting a DSR at a trial count of one when twelve variants were run is the
    same error as quoting the raw Sharpe.

    ``trial_variance`` is the cross-sectional variance of the Sharpe estimates across those
    trials. Supply it when the trial returns are available. When they are not, pass
    ``benchmark_sharpe`` directly, or accept the conservative default below.

    Returns a dict rather than a bare number, because a DSR without its inputs beside it
    cannot be checked and invites being quoted as if it were a p-value from a single test.
    """
    returns = [float(value) for value in returns]
    if len(returns) < 3:
        return {"status": "insufficient_observations", "observations": len(returns),
                "deflated_sharpe": None}
    observed = sharpe_ratio(returns)
    if observed is None:
        return {"status": "zero_variance", "observations": len(returns),
                "deflated_sharpe": None}
    _mean, _deviation, skew, kurtosis = _moments(returns)

    if benchmark_sharpe is None:
        if trial_variance is None:
            # With no trial return matrix, the variance of the trial Sharpes is unknown. The
            # conservative stand-in is the sampling variance of a single unskilled Sharpe
            # estimate, 1/(T-1), which understates the spread real variants show and therefore
            # understates the bar. It is labelled so a reader can see the DSR is optimistic.
            trial_variance = 1.0 / (len(returns) - 1)
            variance_source = "assumed_single_trial_sampling_variance_optimistic"
        else:
            variance_source = "measured_across_trial_sharpes"
        benchmark_sharpe = expected_maximum_sharpe(trial_variance, trials)
    else:
        variance_source = "caller_supplied_benchmark"

    # Non-normality correction: a skewed or fat-tailed return series makes the Sharpe estimate
    # noisier than the normal case, and ignoring that inflates every downstream probability.
    denominator = math.sqrt(max(1e-12,
                                1 - skew * observed + (kurtosis - 1) / 4 * observed ** 2))
    statistic = (observed - benchmark_sharpe) * math.sqrt(len(returns) - 1) / denominator
    return {
        "status": "ok",
        "observations": len(returns),
        "observed_sharpe": observed,
        "trials": trials,
        "trial_variance": trial_variance,
        "trial_variance_source": variance_source,
        "benchmark_sharpe": benchmark_sharpe,
        "skew": skew,
        "kurtosis": kurtosis,
        "t_statistic": statistic,
        "deflated_sharpe": NORMAL.cdf(statistic),
        "citation": ("Bailey and Lopez de Prado, Journal of Portfolio Management 40(5), 2014"),
    }


def sharpe_variance_across_trials(trial_returns):
    """Variance of the Sharpe estimates across a set of trials, for the DSR benchmark.

    ``trial_returns`` is {name: [returns]}. Every trial counts, including the ones abandoned:
    the trial count is a statement about how much searching happened, and dropping the losers
    from it is what makes a deflated statistic undeflated again.
    """
    sharpes = [sharpe_ratio(returns) for returns in trial_returns.values()]
    sharpes = [value for value in sharpes if value is not None]
    if len(sharpes) < 2:
        return None
    mean = sum(sharpes) / len(sharpes)
    return sum((value - mean) ** 2 for value in sharpes) / (len(sharpes) - 1)


def probability_of_backtest_overfitting(trial_returns, *, blocks=8):
    """PBO by combinatorially symmetric cross-validation.

    ``trial_returns`` is {variant: [returns]}, all series the same length and time-aligned.
    The matrix is cut into ``blocks`` contiguous blocks, every balanced split into train and
    test halves is formed, the in-sample best variant is selected on the train half, and its
    out-of-sample rank is measured on the test half. PBO is the share of splits where that
    rank falls below median.

    A PBO near 0.5 means the selection procedure is picking noise: the in-sample winner is no
    more likely than a coin flip to beat the median out of sample. The repository's promotion
    criteria require 0.50 or lower.
    """
    names = [name for name, series in trial_returns.items() if series]
    if len(names) < 2:
        return {"status": "needs_at_least_two_variants", "pbo": None}
    length = min(len(trial_returns[name]) for name in names)
    if length < blocks * 2:
        return {"status": "needs_at_least_two_observations_per_block",
                "observations": length, "blocks": blocks, "pbo": None}

    matrix = {name: [float(value) for value in trial_returns[name][:length]] for name in names}
    edges = [round(index * length / blocks) for index in range(blocks + 1)]
    block_indices = [list(range(edges[index], edges[index + 1])) for index in range(blocks)]

    logits, below_median = [], 0
    splits = 0
    for train_blocks in itertools.combinations(range(blocks), blocks // 2):
        train = [index for block in train_blocks for index in block_indices[block]]
        test = [index for block in range(blocks) if block not in train_blocks
                for index in block_indices[block]]
        if len(train) < 2 or len(test) < 2:
            continue
        in_sample = {name: sharpe_ratio([matrix[name][index] for index in train])
                     for name in names}
        out_sample = {name: sharpe_ratio([matrix[name][index] for index in test])
                      for name in names}
        if any(value is None for value in in_sample.values()) or \
                any(value is None for value in out_sample.values()):
            continue
        splits += 1
        best = max(in_sample, key=lambda name: in_sample[name])
        beaten = sum(1 for name in names
                     if name != best and out_sample[name] < out_sample[best])
        rank = beaten / (len(names) - 1)
        clamped = min(max(rank, 1e-9), 1 - 1e-9)
        logit = math.log(clamped / (1 - clamped))
        logits.append(logit)
        if logit <= 0:
            below_median += 1
    if not splits:
        return {"status": "no_usable_splits", "pbo": None}
    return {
        "status": "ok",
        "pbo": below_median / splits,
        "splits": splits,
        "blocks": blocks,
        "variants": len(names),
        "observations": length,
        "mean_logit": sum(logits) / len(logits),
        "citation": ("Bailey, Borwein, Lopez de Prado and Zhu, Notices of the American "
                     "Mathematical Society 61(5), 2014"),
    }


# Harvey, Liu & Zhu (Review of Financial Studies 29(1), 2016) argue that the volume of factors
# already tested makes the conventional t > 2.0 far too permissive, and put the hurdle for a
# newly proposed factor at t > 3.0. Every overlay variant in this repository is measured
# against this constant, not against 2.0.
HLZ_T_HURDLE = 3.0
HLZ_CITATION = "Harvey, Liu & Zhu, Review of Financial Studies 29(1), 2016"


def clears_hlz_hurdle(t_statistic, hurdle=HLZ_T_HURDLE):
    """Whether a t statistic clears the multiple-testing-corrected credibility hurdle."""
    return {
        "t_statistic": t_statistic,
        "hurdle": hurdle,
        "clears": t_statistic is not None and t_statistic > hurdle,
        "citation": HLZ_CITATION,
        "note": ("The conventional 2.0 is not used anywhere in this repository's promotion "
                 "logic. Sullivan, Timmermann & White (Journal of Finance 1999) show that "
                 "once the universe of technical rules tried is accounted for, the best "
                 "in-sample rule's apparent superiority does not survive."),
    }
