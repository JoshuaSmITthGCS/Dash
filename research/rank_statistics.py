"""Rank statistics for factor measurement, with no dependency on any harness.

Kept separate from ``features.py`` because these are the load-bearing pieces: every
per-metric verdict in Phase 5 is one of these four functions applied to a column of scores. A
subtle error here does not raise -- it produces a plausible number and a wrong conclusion. So
they live where they can be tested without loading a price cache, a scoring configuration, or
a million filings.

The brief allows no new runtime dependencies, so there is no SciPy here and the normal tail is
inverted by bisection. That is not a compromise at this scale: one root find over a monotone
function, to three decimal places, once per run.
"""

import math
import statistics


def ranks(values):
    """Fractional ranks with ties averaged.

    Ties matter more here than in most rank code. The model's band scores are coarse by
    design -- a metric may take five distinct values across eight hundred companies -- and
    breaking those ties by input order would invent an ordering the metric does not have,
    making a five-valued score look as though it ranks the cross-section.
    """
    order = sorted(range(len(values)), key=lambda index: values[index])
    result = [0.0] * len(values)
    position = 0
    while position < len(order):
        end = position
        while end + 1 < len(order) and values[order[end + 1]] == values[order[position]]:
            end += 1
        shared = (position + end) / 2.0 + 1
        for index in range(position, end + 1):
            result[order[index]] = shared
        position = end + 1
    return result


def spearman(left, right):
    """Rank correlation of two equal-length sequences, or None where it is undefined.

    Undefined specifically includes the case where one side has no variation at all. Every
    company scoring identically on a metric is a band configuration that cannot rank
    anything, and recording that as a correlation of zero would average it in as evidence of
    no signal when it is an absence of measurement. The two are different findings.
    """
    if len(left) != len(right) or len(left) < 3:
        return None
    left_ranks, right_ranks = ranks(left), ranks(right)
    count = len(left_ranks)
    mean_left = sum(left_ranks) / count
    mean_right = sum(right_ranks) / count
    covariance = sum((a - mean_left) * (b - mean_right)
                     for a, b in zip(left_ranks, right_ranks))
    spread_left = math.sqrt(sum((a - mean_left) ** 2 for a in left_ranks))
    spread_right = math.sqrt(sum((b - mean_right) ** 2 for b in right_ranks))
    if not spread_left or not spread_right:
        return None
    return covariance / (spread_left * spread_right)


def summarise_series(coefficients):
    """Mean, dispersion and t-statistic of a series of per-date coefficients.

    A large erratic edge and a small consistent one have the same mean and are not the same
    finding, which is why the t-statistic is reported rather than the average alone.
    """
    values = [value for value in coefficients if value is not None]
    if len(values) < 2:
        return {"periods": len(values)}
    mean = statistics.mean(values)
    deviation = statistics.stdev(values)
    return {
        "periods": len(values),
        "mean_ic": mean,
        "ic_stdev": deviation,
        # Rebalances are spaced a full holding period apart, so these observations do not
        # share returns and this is a real t-statistic rather than one inflated by overlap.
        "t_statistic": (mean / deviation * math.sqrt(len(values))) if deviation else None,
        "hit_rate": sum(1 for value in values if value > 0) / len(values),
    }


def bonferroni_threshold(tests):
    """The two-sided 5% critical value corrected for ``tests`` simultaneous comparisons.

    Thirty-two metrics measured at once will produce apparent winners from noise. At a
    nominal 1.96 the expectation is more than one false positive, so a metric at t = 2.5
    looks significant alone and is not, once the other thirty-one are acknowledged.
    """
    target = 0.05 / max(tests, 1) / 2
    low, high = 0.0, 10.0
    for _ in range(200):
        middle = (low + high) / 2
        tail = 0.5 * math.erfc(middle / math.sqrt(2))
        if tail > target:
            low = middle
        else:
            high = middle
    return round((low + high) / 2, 3)
