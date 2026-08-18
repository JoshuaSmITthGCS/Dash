"""Real sector-index Brinson allocation effect: does the book's sector tilt help or hurt,
independent of which specific names it holds.

Brinson attribution decomposes active return into three effects: allocation (over- or
underweighting a sector versus the benchmark), selection (picking better names within a
sector than the benchmark's own constituents), and interaction (the cross term). This module
computes the allocation effect only, and says why the other two are not published rather than
fabricating them: selection needs the book's own realized return *within each sector*, which
needs a per-holding return time series joined to a historical sector classification that
neither this pipeline's committed backtest artifacts nor its point-in-time sector log
currently carry. Publishing a selection or interaction number without that would be
inventing an observation, exactly what this codebase's other metrics refuse to do.

Allocation effect for sector *i*: ``(w_p,i - w_b,i) * (R_b,i - R_b)``

  * ``w_p,i`` / ``w_b,i`` - the book's and the benchmark's weight in sector *i*, from the
    latest recorded sector-weight snapshot (the same snapshot
    ``signal_metrics.py``'s ``sector_active_weights`` metric already reads).
  * ``R_b,i`` - the benchmark's own realized return *within* sector *i*, from that sector's
    SPDR ETF (XLK, XLF, ...) - a real, tradeable, dividend-adjusted total return, not a
    name-level reconstruction.
  * ``R_b`` - the benchmark's overall realized return (SPY) over the same window.

The window is the span the sector-weight log itself covers, from its earliest to its latest
recorded date - the only period this pipeline has direct, logged evidence of what the book's
sector tilts actually were, rather than assuming today's positioning held further back than
it has actually been observed.
"""

import stress_scenarios

SECTOR_ETF = {
    "basic_materials": "XLB", "communication_services": "XLC", "consumer_cyclical": "XLY",
    "consumer_defensive": "XLP", "energy": "XLE", "financial_services": "XLF",
    "healthcare": "XLV", "industrials": "XLI", "real_estate": "XLRE",
    "technology": "XLK", "utilities": "XLU",
}
BENCHMARK_ETF = "SPY"
# Below this, a two-point allocation effect from a handful of days either side of a single
# rebalance is not evidence of anything -- it is one snapshot's arithmetic.
MINIMUM_SNAPSHOTS = 5


def allocation_effect(history, *, etf_dir=stress_scenarios.ETF_DIR):
    """Allocation effect per sector and in total, from the sector-weight snapshot log.

    ``history`` is the list of rows ``pipeline/sector_weight_history.py`` appends - the same
    list ``signal_metrics.py``'s ``construction_metrics`` already reads for
    ``sector_active_weights``. Returns ``None`` when fewer than ``MINIMUM_SNAPSHOTS`` usable
    rows exist, when the snapshots do not span more than one calendar day, or when SPY's own
    return over that window cannot be read.
    """
    usable = [row for row in history or []
             if row.get("strategy_sector_weights") and row.get("benchmark_sector_weights")
             and row.get("as_of")]
    if len(usable) < MINIMUM_SNAPSHOTS:
        return None
    usable.sort(key=lambda row: row["as_of"])
    start, end = str(usable[0]["as_of"])[:10], str(usable[-1]["as_of"])[:10]
    if start >= end:
        return None

    latest = usable[-1]
    strategy_weights = latest["strategy_sector_weights"]
    benchmark_weights = latest["benchmark_sector_weights"]

    spy_prices = stress_scenarios.read_etf_prices(BENCHMARK_ETF, etf_dir)
    benchmark_return = stress_scenarios.window_return(spy_prices, start, end)
    if benchmark_return is None:
        return None

    sectors, total_effect = {}, 0.0
    for sector, ticker in SECTOR_ETF.items():
        weight_strategy = strategy_weights.get(sector) or 0.0
        weight_benchmark = benchmark_weights.get(sector) or 0.0
        sector_prices = stress_scenarios.read_etf_prices(ticker, etf_dir)
        sector_return = stress_scenarios.window_return(sector_prices, start, end)
        if sector_return is None:
            sectors[sector] = {
                "ticker": ticker, "strategy_weight": round(weight_strategy, 4),
                "benchmark_weight": round(weight_benchmark, 4),
                "active_weight": round(weight_strategy - weight_benchmark, 4),
                "sector_return_pct": None, "allocation_effect_pct": None,
            }
            continue
        effect = (weight_strategy - weight_benchmark) * (sector_return - benchmark_return)
        total_effect += effect
        sectors[sector] = {
            "ticker": ticker, "strategy_weight": round(weight_strategy, 4),
            "benchmark_weight": round(weight_benchmark, 4),
            "active_weight": round(weight_strategy - weight_benchmark, 4),
            "sector_return_pct": round(sector_return * 100, 2),
            "allocation_effect_pct": round(effect * 100, 3),
        }

    return {
        "start": start, "end": end, "snapshots": len(usable), "as_of": latest.get("as_of"),
        "benchmark_return_pct": round(benchmark_return * 100, 2),
        "total_allocation_effect_pct": round(total_effect * 100, 3),
        "sectors": sectors,
    }
