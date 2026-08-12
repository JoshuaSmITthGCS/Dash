"""Return and risk arithmetic shared by the stock and ETF models.

Before this module the two models measured "risk" in different languages: the ETF screen
used real Sharpe/Sortino ratios while the stock screen used an invented linear penalty
(``100 - max(0, vol - 12) * 2 - |drawdown| * 1.5``). Those constants were not wrong in
direction, but they are not comparable across regimes and cannot be validated against any
published result. Both models now import the same functions, so a Sharpe of 1.2 means the
same thing on either screen and both can be evaluated on the same footing.

Everything here is pure: it takes lists of floats and returns floats or None.
"""

from math import sqrt

TRADING_DAYS = 252
# Trading-day windows used across both models.
MONTH = 21
YEAR = 252
# A variance this small is floating-point residue on a flat series, not real dispersion.
# Testing against exact zero lets a constant benchmark divide through to a garbage beta.
NEAR_ZERO_VARIANCE = 1e-18


def daily_returns(closes):
    """Simple daily returns. Zero or missing prior closes are dropped, not zero-filled."""
    return [(later / earlier) - 1 for earlier, later in zip(closes[:-1], closes[1:]) if earlier]


def period_return(closes, days):
    """Percent change over the trailing ``days`` sessions. None when history is short."""
    if len(closes) <= days or not closes[-days - 1]:
        return None
    return round((closes[-1] / closes[-days - 1] - 1) * 100, 2)


def momentum_12_1(closes, *, lookback=YEAR, skip=MONTH):
    """Trailing 12-month return excluding the most recent month, in percent.

    The skip is the whole point. Jegadeesh & Titman (1993) document momentum at the
    12-month horizon alongside a well-established short-term reversal in the most recent
    month; including that month contaminates the momentum signal with the reversal that
    works against it. Standard academic construction is 12-1, not raw 12-month.
    """
    if len(closes) <= lookback + 1:
        return None
    start, end = closes[-lookback - 1], closes[-skip - 1]
    if not start or not end:
        return None
    return round((end / start - 1) * 100, 2)


def annualized_volatility(returns, window=60):
    """Annualized standard deviation of daily returns, in percent."""
    recent = returns[-window:] if window else list(returns)
    if len(recent) < 2:
        return None
    mean = sum(recent) / len(recent)
    variance = sum((value - mean) ** 2 for value in recent) / len(recent)
    return round(sqrt(max(0.0, variance)) * sqrt(TRADING_DAYS) * 100, 2)


def sharpe_ratio(returns, minimum_observations=20):
    """Annualized Sharpe on daily returns. Excess-of-cash is omitted deliberately:
    the ratio is used for ranking within a batch, where a common risk-free rate cancels."""
    if len(returns) < minimum_observations:
        return None
    mean = sum(returns) / len(returns)
    variance = sum((value - mean) ** 2 for value in returns) / len(returns)
    if variance <= NEAR_ZERO_VARIANCE:
        return None
    return round((mean / sqrt(variance)) * sqrt(TRADING_DAYS), 2)


def sortino_ratio(returns, minimum_observations=20):
    """Annualized Sortino: the same numerator over downside deviation only.

    Preferred over Sharpe as the primary risk measure because upside volatility is not
    a risk anyone is trying to avoid.
    """
    if len(returns) < minimum_observations:
        return None
    mean = sum(returns) / len(returns)
    downside = [min(0.0, value) for value in returns]
    variance = sum(value * value for value in downside) / len(downside)
    if variance <= NEAR_ZERO_VARIANCE:
        return None
    return round((mean / sqrt(variance)) * sqrt(TRADING_DAYS), 2)


def beta_vs_benchmark(returns, benchmark_returns, minimum_observations=20):
    """Ordinary least-squares beta against a benchmark return series."""
    overlap = min(len(returns), len(benchmark_returns))
    if overlap < minimum_observations:
        return None
    series, benchmark = returns[-overlap:], benchmark_returns[-overlap:]
    mean_series = sum(series) / overlap
    mean_benchmark = sum(benchmark) / overlap
    covariance = sum((a - mean_series) * (b - mean_benchmark)
                     for a, b in zip(series, benchmark)) / overlap
    variance = sum((b - mean_benchmark) ** 2 for b in benchmark) / overlap
    return round(covariance / variance, 2) if variance > NEAR_ZERO_VARIANCE else None


def max_drawdown(closes):
    """Deepest peak-to-trough fall over the window, in percent. Makes broken charts obvious."""
    if len(closes) < 2:
        return None
    peak, worst = closes[0], 0.0
    for close in closes:
        peak = max(peak, close)
        if peak:
            worst = min(worst, close / peak - 1)
    return round(worst * 100, 2)


def tracking_difference(fund_return, benchmark_return):
    """Realized gap between a fund and its index, in percentage points.

    Tracking *difference* is what an investor actually keeps or loses; tracking *error*
    (below) is only the volatility of that gap. Both are reported; this one matters more.
    """
    if fund_return is None or benchmark_return is None:
        return None
    return round(fund_return - benchmark_return, 3)


def tracking_error(returns, benchmark_returns, minimum_observations=20):
    """Annualized standard deviation of the fund-minus-index return difference, in percent."""
    overlap = min(len(returns), len(benchmark_returns))
    if overlap < minimum_observations:
        return None
    differences = [a - b for a, b in zip(returns[-overlap:], benchmark_returns[-overlap:])]
    mean = sum(differences) / overlap
    variance = sum((value - mean) ** 2 for value in differences) / overlap
    return round(sqrt(max(0.0, variance)) * sqrt(TRADING_DAYS) * 100, 3)


def excess_returns(returns, benchmark_returns, beta=None, minimum_observations=20):
    """Market-relative daily returns: ``r_stock - beta * r_market``.

    The beta term is what makes this genuinely *relative to the market* rather than a
    relabelled own-return. A raw ``r_stock - r_market`` difference subtracts the same
    benchmark number from every stock on a given day, and subtracting a constant cannot
    change a cross-sectional ranking - that is exactly the degeneracy the model audit found
    in ``relative_strength_20d`` (rho = +1.00 against ``return_20d`` across 877 published
    rows; see research/audit/CURRENT_MODEL_AUDIT.md section 6, and the reason that term is
    excluded from the live blend by ``short_horizon_treatment: neutral``).

    Scaling the market leg by each name's own beta breaks the degeneracy: a 1.6-beta name
    has to beat a 1.6x market move to read positive while a 0.4-beta name only has to beat
    0.4x of it, so the benchmark contribution differs row by row. This is the residual
    construction behind residual momentum (Blitz, Huij & Martens 2011), applied here to the
    market factor alone rather than a full factor model.

    Returns ``(excess_series, beta)``, or ``(None, None)`` when beta cannot be estimated -
    a flat or too-short benchmark. Beta is never defaulted to 1.0: assuming a beta is
    assuming the answer, and an unmeasurable name is better reported as unmeasured.
    """
    overlap = min(len(returns), len(benchmark_returns))
    if overlap < minimum_observations:
        return None, None
    series, benchmark = returns[-overlap:], benchmark_returns[-overlap:]
    if beta is None:
        beta = beta_vs_benchmark(series, benchmark, minimum_observations)
    if beta is None:
        return None, None
    return [value - beta * market for value, market in zip(series, benchmark)], beta


def relative_acceleration(closes, benchmark_closes, *, leg=63, skip=5, beta=None):
    """Whether a stock's market-relative pace is increasing or decreasing.

    Momentum asks whether a stock has been beating the market. Acceleration asks the
    second-derivative question: whether it is beating the market by *more than it recently
    was*. Gettleman & Marks (2006, "Acceleration Strategies") document that the change in
    momentum carries cross-sectional information beyond the level of momentum. That result
    is nowhere near as heavily replicated as 12-1 momentum itself, which is why this
    function is a published measurement rather than a scoring weight - see
    ``advisor_engine.technical_factors``.

    Construction:

    * daily **beta-adjusted** excess returns against the benchmark (``excess_returns``), so
      the reading is not a monotone transform of the stock's own return;
    * the most recent ``skip`` sessions are dropped, because the last week is where
      short-term reversal lives - the same reason ``momentum_12_1`` skips a whole month;
    * two adjacent ``leg``-session windows: cumulative excess over the recent leg minus
      cumulative excess over the leg immediately before it;
    * that difference divided by its own standard error, so a reading means the same thing
      on a quiet utility and on a 90%-volatility biotech. Two sums of ``leg`` daily excess
      returns have standard error ``sd * sqrt(2 * leg)``.

    The returned ``acceleration`` is therefore a t-statistic, not a percentage: +1 means
    the pickup is one standard error of noise, not one percent. ``acceleration_pct`` keeps
    the raw percentage-point pickup for anyone who wants the magnitude.

    Returns None when there is not enough overlapping history for both legs plus the skip.
    """
    if leg < 2 or skip < 0:
        raise ValueError("relative_acceleration needs leg >= 2 and skip >= 0")
    returns = daily_returns(closes)
    benchmark_returns = daily_returns(benchmark_closes or [])
    overlap = min(len(returns), len(benchmark_returns))
    if overlap < 2 * leg + skip:
        return None
    # Everything the reading uses lives inside the 2*leg sessions ending ``skip`` sessions
    # ago - beta included. Fitting beta on the full history instead would let the skipped
    # week back in through the beta estimate, and the point of skipping it is that it does
    # not inform the measurement.
    series = returns[-overlap:]
    benchmark = benchmark_returns[-overlap:]
    if skip:
        series, benchmark = series[:-skip], benchmark[:-skip]
    sample, beta = excess_returns(series[-2 * leg:], benchmark[-2 * leg:], beta)
    if sample is None:
        return None
    recent, prior = sample[leg:], sample[:leg]
    recent_excess, prior_excess = sum(recent), sum(prior)
    difference = recent_excess - prior_excess
    mean = sum(sample) / len(sample)
    variance = sum((value - mean) ** 2 for value in sample) / len(sample)
    if variance <= NEAR_ZERO_VARIANCE:
        return None
    standard_error = sqrt(variance) * sqrt(2 * leg)
    return {
        "acceleration": round(difference / standard_error, 2),
        "acceleration_pct": round(difference * 100, 2),
        "recent_excess_pct": round(recent_excess * 100, 2),
        "prior_excess_pct": round(prior_excess * 100, 2),
        "beta": round(beta, 2),
        "leg_days": leg,
        "skip_days": skip,
        "observations": len(sample),
    }


def ratio_to_score(value, *, neutral=0.0, span=1.5, floor=0.0, ceiling=100.0):
    """Map an unbounded risk-adjusted ratio onto 0-100 without inventing thresholds.

    ``neutral`` scores 50 and each ``span`` of ratio moves the score half the remaining
    range, so a Sortino of 0 is 50, 1.5 is 75, 3.0 is 87.5. The curve saturates instead of
    clipping, which keeps one extraordinary reading from dominating a blended bucket.
    """
    if value is None or span <= 0:
        return None
    excess = (value - neutral) / span
    score = 50.0 * (1 + excess / (1 + abs(excess)))
    return round(max(floor, min(ceiling, score)), 1)


def acceleration_score(t_statistic, *, span=1.0):
    """Map a ``relative_acceleration`` t-statistic onto 0-100, on the same saturating curve
    Sharpe and Sortino are scored with.

    ``span=1.0`` means one standard error of pickup scores 75 and one standard error of
    deceleration scores 25. Saturating rather than clipping keeps one violent quarter from
    pinning the reading at 100 and hiding everything behind it.
    """
    return ratio_to_score(t_statistic, neutral=0.0, span=span)


def low_beta_score(beta, *, ideal=0.85, tolerance=0.55):
    """Reward low beta, per the betting-against-beta anomaly (Frazzini & Pedersen 2014).

    High-beta assets have historically delivered lower risk-adjusted returns than their
    beta implies. This scores beta as a distance from a modestly defensive ideal rather
    than as an ad hoc volatility penalty, and treats negative beta as a hedge, not a bug.
    """
    if beta is None:
        return None
    distance = abs(beta - ideal) / tolerance
    return round(max(0.0, min(100.0, 100.0 / (1 + distance * distance))), 1)


def drawdown_score(drawdown_pct, *, tolerance=25.0):
    """Map a (negative) max-drawdown percentage onto 0-100. A 25% fall scores 50."""
    if drawdown_pct is None:
        return None
    depth = abs(min(0.0, drawdown_pct)) / tolerance
    return round(max(0.0, min(100.0, 100.0 / (1 + depth))), 1)


def volatility_percentile(value, peers, lower_is_better=True):
    """Where a volatility reading sits among its peers, 0-100. None below three peers."""
    present = [peer for peer in peers if peer is not None]
    if value is None or len(present) < 3:
        return None
    below = sum(1 for peer in present if peer < value)
    percentile = 100.0 * below / len(present)
    return round(100.0 - percentile if lower_is_better else percentile, 1)
