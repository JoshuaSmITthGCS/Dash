"""Backtest: does options_common.realized_vol_percentile actually predict anything?

The options screens added this session publish five volatility/flow context fields.
Four of them (iv_skew, put_call_oi_ratio, single_expiration_gex, iv_percentile) cannot be
historically backtested with this pipeline's data: real option chains for past dates don't
exist anywhere this pipeline can reach (Yahoo serves only the live chain), and
backtest_common.synthetic_chain() - the only "historical chain" this pipeline can produce -
uses one flat IV across every strike and a constant placeholder open interest by design (see
its own module docstring), so any of those four factors computed from a synthetic chain would
be a constant or a smooth restatement of the Black-Scholes gamma curve, not a real measurement
of anything. Publishing a "backtest" of those four would be exactly the kind of fabricated
validation docs/VALIDATION-METHODOLOGY.md exists to prevent.

realized_volatility_percentile is the one exception: it is computed purely from real
historical closing prices, which pipeline/price_archive.py has archived for real, for
decades, for nearly 2,000 tickers. This module is the genuine backtest that data supports.

Two separately reported, honestly distinct questions:

1. Mean reversion (the premise a vol-selling screen implicitly assumes): does a HIGH
   realized_vol_percentile predict a FALLING realized vol over the following ~20 trading
   days? Tested as the rank-IC between percentile-at-entry and the forward change in
   realized vol (forward_vol - trailing_vol). A negative IC supports mean reversion (rich
   vol tends to fall); a positive IC would say the opposite (rich vol tends to get richer).
2. Direction (a null-result sanity check, not a claim this pipeline makes anywhere else):
   does realized_vol_percentile predict the SIGN or magnitude of the forward stock return at
   all? There's no a priori reason volatility LEVEL should predict return DIRECTION - this is
   included so a reader can see the test was run and came back null, rather than wondering why
   it wasn't tried.

Methodology mirrors pipeline/validation/ic_harness.py's rank-IC/ICIR statistics exactly - this
reuses its own _ic_summary and evaluation.rank_ic rather than inventing new statistics, for
consistency with how every other predictive claim in this pipeline is evaluated. A "period"
here is one calendar date; the cross-section is every sampled ticker with a valid reading on
that date, exactly like ic_harness's own cross-sectional periods.

Scope: computing a valid 60-sample-minimum percentile at every single trading day for every
one of ~2,000 archived tickers (some with 45+ years of history) is not the point - only the
most recent MAX_SESSIONS_PER_TICKER sessions of each sampled ticker are used, and only
SAMPLE_SIZE tickers are sampled (deterministically, alphabetically, so a rerun is
reproducible). This keeps the backtest fast without changing what it measures: a longer
lookback window would not change realized_vol_percentile's own definition, which only ever
looks back DEFAULT_LOOKBACK (252) sessions to begin with.
"""

import os
import sys
from bisect import bisect_left, insort

PIPELINE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PIPELINE_DIR not in sys.path:
    sys.path.insert(0, PIPELINE_DIR)

from evaluation import rank_ic  # noqa: E402
from options_common import MINIMUM_VOL_PERCENTILE_SAMPLES  # noqa: E402
from price_archive import ARCHIVE_DIR, load_series  # noqa: E402
from validation.ic_harness import _ic_summary  # noqa: E402

WINDOW = 20  # matches options_common.realized_vol_percentile's own rolling window
LOOKBACK = 252  # matches options_common.realized_vol_percentile's own DEFAULT_LOOKBACK
FORWARD_DAYS = 20  # holding period this test measures forward vol change/return over
SAMPLE_SIZE = 250
MAX_SESSIONS_PER_TICKER = 1500  # ~6 years - ample given LOOKBACK is only 252 sessions


def _sample_tickers(sample_size=SAMPLE_SIZE, directory=None):
    """Deterministic (alphabetical) sample of archived tickers, so a rerun reproduces
    the same universe rather than depending on directory-listing order or randomness.
    """
    directory = directory or ARCHIVE_DIR
    if not os.path.isdir(directory):
        return []
    tickers = sorted(f[:-5] for f in os.listdir(directory) if f.endswith(".json") and f != "archive_manifest.json")
    return tickers[:sample_size]


def _rolling_realized_vol(closes):
    """Same formula as options_common.realized_volatility_20d, computed once per index
    rather than once per call - O(n) instead of the O(n^2) a naive per-day call to that
    function would cost over a long history. index i holds the realized vol as of closes[i]
    (using closes[i-WINDOW:i+1]), or None where WINDOW prior closes aren't available.
    """
    import math
    series = [None] * len(closes)
    for i in range(WINDOW, len(closes)):
        window_closes = closes[i - WINDOW:i + 1]
        if any(value <= 0 for value in window_closes):
            continue
        returns = [math.log(window_closes[j] / window_closes[j - 1]) for j in range(1, len(window_closes))]
        if len(returns) > 1:
            mean_return = sum(returns) / len(returns)
            variance = sum((r - mean_return) ** 2 for r in returns) / (len(returns) - 1)
            series[i] = variance ** 0.5 * math.sqrt(252)
    return series


def _percentile_series(vol_series, lookback=LOOKBACK, minimum_samples=MINIMUM_VOL_PERCENTILE_SAMPLES):
    """Percentile (0-100) of vol_series[i] among its own trailing `lookback` non-None values,
    at every index - identical semantics to options_common.realized_vol_percentile applied
    at every historical point, computed with a maintained sorted window (bisect) so each new
    day costs O(lookback) instead of the O(n) a fresh per-day call would cost, since a sorted
    list lets both "how many trailing values are <= this one" and "insert/evict" run in
    O(lookback) rather than O(n).
    """
    percentiles = [None] * len(vol_series)
    sorted_window, raw_window = [], []
    for i, value in enumerate(vol_series):
        if value is None:
            continue
        if len(raw_window) >= lookback:
            oldest = raw_window.pop(0)
            sorted_window.pop(bisect_left(sorted_window, oldest))
        insort(sorted_window, value)
        raw_window.append(value)
        if len(sorted_window) >= minimum_samples:
            # Count of values <= `value` (not < value), matching options_common's own
            # "sum(1 for v in series if v <= current)" definition exactly: start at the
            # leftmost insertion point for `value` and walk right through any duplicates.
            count_le = bisect_left(sorted_window, value)
            while count_le < len(sorted_window) and sorted_window[count_le] <= value:
                count_le += 1
            percentiles[i] = round(100 * count_le / len(sorted_window), 2)
    return percentiles


def _ticker_observations(ticker, max_sessions=MAX_SESSIONS_PER_TICKER):
    """(date, percentile, trailing_vol, forward_vol_change, forward_return) tuples for one
    ticker - every index with both a valid percentile reading AND a full forward window to
    measure the outcome against.
    """
    series = load_series(ticker)
    dates, closes = series["dates"], series["closes"]
    if len(closes) > max_sessions:
        dates, closes = dates[-max_sessions:], closes[-max_sessions:]
    if len(closes) < WINDOW + MINIMUM_VOL_PERCENTILE_SAMPLES + FORWARD_DAYS:
        return []
    vol_series = _rolling_realized_vol(closes)
    percentile_series = _percentile_series(vol_series)
    observations = []
    for i in range(len(closes) - FORWARD_DAYS):
        percentile = percentile_series[i]
        trailing_vol = vol_series[i]
        forward_vol = vol_series[i + FORWARD_DAYS]
        if percentile is None or trailing_vol is None or forward_vol is None or not closes[i]:
            continue
        forward_return = closes[i + FORWARD_DAYS] / closes[i] - 1
        observations.append((dates[i], percentile, forward_vol - trailing_vol, forward_return))
    return observations


def run(sample_size=SAMPLE_SIZE, tickers=None):
    """Runs the backtest over `tickers` (default: a deterministic sample of the real,
    already-archived universe) and returns both IC summaries plus coverage counts.
    """
    tickers = tickers if tickers is not None else _sample_tickers(sample_size)
    by_date = {}
    tickers_with_data = 0
    for ticker in tickers:
        observations = _ticker_observations(ticker)
        if observations:
            tickers_with_data += 1
        for date, percentile, vol_change, forward_return in observations:
            by_date.setdefault(date, []).append((percentile, vol_change, forward_return))

    mean_reversion_ics, direction_ics = [], []
    for date in sorted(by_date):
        rows = by_date[date]
        percentiles = [row[0] for row in rows]
        vol_changes = [row[1] for row in rows]
        forward_returns = [row[2] for row in rows]
        mr_ic = rank_ic(percentiles, vol_changes)
        if mr_ic is not None:
            mean_reversion_ics.append(mr_ic)
        dir_ic = rank_ic(percentiles, forward_returns)
        if dir_ic is not None:
            direction_ics.append(dir_ic)

    return {
        "methodology": ("Real historical prices only (pipeline/price_archive.py), rank-IC "
                        "per calendar date across the sampled tickers with a valid reading "
                        "that date, aggregated with the same _ic_summary machinery "
                        "pipeline/validation/ic_harness.py uses for the live score."),
        "tickers_sampled": len(tickers),
        "tickers_with_sufficient_history": tickers_with_data,
        "trading_dates_covered": len(by_date),
        "mean_reversion": {
            "description": "rank-IC(realized_vol_percentile, forward_vol_change) - negative supports mean reversion",
            "summary": _ic_summary(mean_reversion_ics),
        },
        "direction": {
            "description": "rank-IC(realized_vol_percentile, forward_return) - a null-result sanity check, not a claim this pipeline makes",
            "summary": _ic_summary(direction_ics),
        },
    }


if __name__ == "__main__":
    import json
    print(json.dumps(run(), indent=2))
