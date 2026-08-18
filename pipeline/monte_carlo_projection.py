"""Monte Carlo forward projection: a prediction, not a read-out of the past.

Every other artifact in this pipeline is deliberately backward-looking: signal_metrics.py's
tear sheet grades what the composite has already predicted. This module does the opposite on
purpose - it resamples the historical daily return distribution to project the strategy
forward over selectable horizons, and it is published as its own artifact so a reader never
mistakes a projection for a measurement.

Construction:

  * **Block bootstrap, not i.i.d. resampling** - contiguous blocks of daily returns are
    redrawn with replacement, which preserves the short-run autocorrelation an independent
    day-by-day resample would erase.
  * **Backtest history by default, live sample once it is long enough to stand on its own** -
    the backtest carries five-plus years of daily returns; the immutable production shadow
    sample does not yet, so it is the primary input only once it reaches
    ``FULL_HISTORY_OBSERVATIONS`` on its own, and is otherwise reported as a comparison that
    flags a material shift rather than silently overwriting the backtest-based projection.
  * **Vectorized, not looped** - every path's block starts are drawn as one array, and every
    path's cumulative growth and running drawdown is one array operation. There is no
    per-path Python loop; that is what keeps 10,000 paths across four horizons well under the
    five-second budget (see ``main`` for the measured figure).
  * **The mean is never published alone** - every horizon carries the 5th/25th/50th/75th/95th
    percentile of terminal value alongside the mean, plus the probability a path's own
    drawdown exceeds the worst drawdown the strategy has actually lived through. A projection
    that only prints a mean return is a promise; this is not one.

    python pipeline/monte_carlo_projection.py --help
"""

import argparse
import json
import os
import time
from datetime import datetime, timezone

import numpy as np

import risk_metrics
import signal_metrics
from common import LOG, save_json

HERE = os.path.dirname(os.path.abspath(__file__))
PUBLIC_NAME = "validation/monte_carlo_projection.json"
BACKTEST_PATH = os.path.join(HERE, "backtest_monthly_results.json")

TRADING_DAYS_PER_YEAR = 252
PATHS = 10_000
BLOCK_SIZE = 21
HORIZONS_CALENDAR_DAYS = (30, 90, 180, 365)
PERCENTILES = (5, 25, 50, 75, 95)
# Below this, no bootstrap - block or otherwise - is defensible; the "sample" would be a
# handful of blocks resampled from itself.
MINIMUM_OBSERVATIONS = 60
# The n at which a return series stops being "the current, still-thin sample" and starts
# being "full history" worth resampling from on its own, per the same bar
# min_track_record_length and the distribution-shape group already use elsewhere.
FULL_HISTORY_OBSERVATIONS = 253
LIVE_COMPARISON_MINIMUM = FULL_HISTORY_OBSERVATIONS
MATERIAL_SHIFT_RELATIVE_THRESHOLD = 0.25

DISCLOSURE = (
    "This is a projection built by resampling the historical daily return distribution, not "
    "a forecast, guarantee, or promise of future performance. Markets can and do behave "
    "differently than their own history. Read the width of the percentile band, not just the "
    "mean - the band is the honest answer, and the mean alone is false precision.")


def _read_backtest():
    if not os.path.exists(BACKTEST_PATH):
        return None
    with open(BACKTEST_PATH, encoding="utf-8") as handle:
        return json.load(handle)


def _cumulative_curve(returns):
    curve, value = [1.0], 1.0
    for value_return in returns:
        value *= 1 + value_return
        curve.append(value)
    return curve


def _trading_days(calendar_days):
    return max(1, round(calendar_days * TRADING_DAYS_PER_YEAR / 365.0))


def _simulate(returns, horizon_days, *, paths, block_size, seed):
    """Vectorized block-bootstrap terminal-value and max-drawdown distribution.

    No per-path Python loop: every path's block starts are drawn in one call, every block's
    returns are gathered by fancy indexing, and cumulative growth plus running drawdown are
    computed as array operations over all paths at once.
    """
    series = np.asarray(returns, dtype=np.float64)
    n = series.shape[0]
    rng = np.random.default_rng(seed)
    blocks_needed = int(np.ceil(horizon_days / block_size))
    starts = rng.integers(0, n, size=(paths, blocks_needed))
    offsets = np.arange(block_size)
    indices = (starts[:, :, None] + offsets[None, None, :]) % n
    drawn = series[indices].reshape(paths, blocks_needed * block_size)[:, :horizon_days]
    growth = np.cumprod(1.0 + drawn, axis=1)
    terminal = growth[:, -1]
    running_peak = np.maximum.accumulate(growth, axis=1)
    drawdown = growth / running_peak - 1.0
    path_max_drawdown = drawdown.min(axis=1)
    return terminal, path_max_drawdown


def _horizon_summary(returns, horizon_calendar_days, *, current_max_drawdown_pct,
                     paths, block_size, seed):
    trading_days = _trading_days(horizon_calendar_days)
    terminal, path_drawdown = _simulate(
        returns, trading_days, paths=paths, block_size=block_size, seed=seed)
    percentiles = np.percentile(terminal, PERCENTILES)
    mean_terminal = float(terminal.mean())
    years = trading_days / TRADING_DAYS_PER_YEAR

    def annualize(terminal_multiple):
        return float(max(terminal_multiple, 1e-6)) ** (1 / years) - 1

    percentile_map = {f"p{p}": float(value) for p, value in zip(PERCENTILES, percentiles)}
    annualized_percentiles = {key: round(annualize(value) * 100, 2)
                              for key, value in percentile_map.items()}
    current_dd_fraction = (current_max_drawdown_pct or 0.0) / 100.0
    probability_exceeds = float(np.mean(path_drawdown < current_dd_fraction))
    return {
        "calendar_days": horizon_calendar_days,
        "trading_days": trading_days,
        "mean_terminal_multiple": round(mean_terminal, 4),
        "mean_annualized_return_pct": round(annualize(mean_terminal) * 100, 2),
        "terminal_multiple_percentiles": {key: round(value, 4)
                                          for key, value in percentile_map.items()},
        "annualized_return_percentiles_pct": annualized_percentiles,
        "confidence_band_width_pct": round(
            annualized_percentiles["p95"] - annualized_percentiles["p5"], 2),
        "probability_drawdown_exceeds_current_max": round(probability_exceeds, 4),
    }


def build_report(*, backtest=None, live_return_data=None, paths=PATHS, block_size=BLOCK_SIZE,
                 seed=0):
    """Assemble the projection artifact. Any input left ``None`` is read from disk."""
    backtest = _read_backtest() if backtest is None else backtest
    live_return_data = (signal_metrics.live_shadow_returns()
                        if live_return_data is None else live_return_data)
    portfolio = (backtest or {}).get("portfolio") or {}
    history = portfolio.get("history") or []
    backtest_returns = signal_metrics.daily_returns_from_history(history)
    backtest_closes = [row.get("value") for row in history if row.get("value")]
    live_returns = (live_return_data or {}).get("returns") or []
    generated_at = datetime.now(timezone.utc).isoformat()

    if len(backtest_returns) < MINIMUM_OBSERVATIONS and len(live_returns) < MINIMUM_OBSERVATIONS:
        return {
            "schema_version": 1, "generated_at": generated_at, "status": "insufficient_data",
            "status_message": (
                f"Needs at least {MINIMUM_OBSERVATIONS} daily returns to bootstrap a "
                f"projection; {len(backtest_returns)} backtest and {len(live_returns)} live "
                "observations are available."),
            "input": None, "horizons": None, "live_comparison": None, "disclosure": DISCLOSURE,
        }

    if len(backtest_returns) >= MINIMUM_OBSERVATIONS:
        primary_returns, primary_source = backtest_returns, "backtest_daily_returns"
        current_max_drawdown_pct = risk_metrics.max_drawdown(backtest_closes)
    else:
        primary_returns, primary_source = live_returns, "live_shadow_returns"
        current_max_drawdown_pct = risk_metrics.max_drawdown(_cumulative_curve(live_returns))

    method = ("block_bootstrap_full_history" if len(primary_returns) >= FULL_HISTORY_OBSERVATIONS
              else "block_bootstrap_current_sample")
    horizons = {
        str(days): _horizon_summary(primary_returns, days,
                                    current_max_drawdown_pct=current_max_drawdown_pct,
                                    paths=paths, block_size=block_size, seed=seed + index)
        for index, days in enumerate(HORIZONS_CALENDAR_DAYS)
    }

    live_comparison = None
    if primary_source == "backtest_daily_returns" and len(live_returns) >= LIVE_COMPARISON_MINIMUM:
        live_drawdown = risk_metrics.max_drawdown(_cumulative_curve(live_returns))
        live_horizons = {
            str(days): _horizon_summary(live_returns, days,
                                        current_max_drawdown_pct=live_drawdown,
                                        paths=paths, block_size=block_size,
                                        seed=seed + 1000 + index)
            for index, days in enumerate(HORIZONS_CALENDAR_DAYS)
        }
        shift_by_horizon, material = {}, False
        for days in HORIZONS_CALENDAR_DAYS:
            key = str(days)
            backtest_mean = horizons[key]["mean_annualized_return_pct"]
            live_mean = live_horizons[key]["mean_annualized_return_pct"]
            denominator = abs(backtest_mean) if abs(backtest_mean) > 1e-9 else 1.0
            relative_shift = round(abs(live_mean - backtest_mean) / denominator, 4)
            shift_by_horizon[key] = {
                "backtest_mean_annualized_return_pct": backtest_mean,
                "live_mean_annualized_return_pct": live_mean,
                "relative_shift": relative_shift,
            }
            material = material or relative_shift > MATERIAL_SHIFT_RELATIVE_THRESHOLD
        live_comparison = {
            "observations": len(live_returns),
            "note": ("The live production sample has reached full-history length. Compared "
                     "against the backtest-based projection above rather than replacing it, "
                     "since the backtest still carries far more history."),
            "horizons": live_horizons,
            "shift_by_horizon": shift_by_horizon,
            "material_shift": material,
            "material_shift_threshold": MATERIAL_SHIFT_RELATIVE_THRESHOLD,
        }

    return {
        "schema_version": 1,
        "generated_at": generated_at,
        "status": "ready",
        "input": {
            "source": primary_source,
            "observations": len(primary_returns),
            "full_history_threshold": FULL_HISTORY_OBSERVATIONS,
            "method": method,
            "paths": paths,
            "block_size_days": block_size,
            "current_max_drawdown_pct": current_max_drawdown_pct,
            "backtest_observations": len(backtest_returns),
            "live_observations": len(live_returns),
        },
        "horizons": horizons,
        "live_comparison": live_comparison,
        "disclosure": DISCLOSURE,
    }


def write_report(report=None):
    report = report or build_report()
    save_json(PUBLIC_NAME, report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--paths", type=int, default=PATHS, help="Simulated paths per horizon")
    parser.add_argument("--seed", type=int, default=0, help="Base RNG seed, for reproducibility")
    args = parser.parse_args(argv)
    started = time.perf_counter()
    report = build_report(paths=args.paths, seed=args.seed)
    elapsed = round(time.perf_counter() - started, 3)
    if report.get("input") is not None:
        report["input"]["elapsed_seconds"] = elapsed
    write_report(report)
    LOG.info(f"Monte Carlo projection: {report['status']}, "
             f"{args.paths} paths x {len(HORIZONS_CALENDAR_DAYS)} horizons in {elapsed:.2f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
