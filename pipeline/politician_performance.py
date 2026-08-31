"""Per-politician, market-relative performance scoring for the Political Trading screen.

Scoped display-only signal, never an ``advisor_engine`` input - see ``congress_signal.py``'s
docstring for why the research score's one political exception is deliberately narrow
(breadth x freshness of *any* disclosed purchase, nothing about whether that politician's
past picks were any good). This module answers a different question - "given this
politician's disclosed track record, how much weight should their trade carry in the
feed?" - and only ever changes how the Political Trading page ranks and badges rows, not
the research score itself.

**Alpha, not raw return.** Most disclosed purchases simply ride a rising market, so a
politician's raw "since purchase" return mostly measures how the market did over their
holding window, not their skill. Every trade's contribution here is against SPY over the
identical [transaction_date, price_as_of] window (``backtest_monthly.committed_benchmark``,
the same committed series every other backtest in this pipeline reads, so this needs no
network access). A politician's win rate is the fraction of their priced buys that beat
that benchmark, not the fraction that were merely profitable.

**Shrinkage, not a hard trade-count cutoff.** A politician with 3 lucky trades should not
outrank one with 40 solid ones just because 3-for-3 looks perfect. Both the average alpha
and the win rate are pulled toward the population's pooled values with weight
``n / (n + PRIOR_STRENGTH)`` - the standard empirical-Bayes shrinkage for a per-group
average estimated from few observations (see e.g. Efron & Morris 1975). A brand-new
politician with zero priced trades gets exactly the population average, not a zero or a
crash; a politician with hundreds of trades is barely pulled at all.

Only *buys* enter this scoring - a sale has no "did this pick pay off" question to answer,
and ``build_congress_screen.compute_price_performance`` never prices anything else.
"""

from __future__ import annotations

import bisect
import math
from datetime import date, datetime

DEFAULTS = {
    "prior_strength": 8.0,      # pseudo-trades pulled toward the population mean/win-rate
    "alpha_scale": 15.0,        # % alpha at which the alpha component is ~85% saturated
    "alpha_weight": 0.6,        # performance_score = alpha_weight*alpha_component + winrate_weight*win_rate
    "winrate_weight": 0.4,
    "signal_floor": 0.4,        # performance_multiplier range for signal_strength: [floor, floor+range]
    "signal_range": 1.2,
    "size_reference": 1_000_000.0,  # same NOTABLE_SIGNAL_SIZE_REFERENCE build_congress_screen uses
    "confidence_low_max": 2,    # n <= this -> "low"
    "confidence_medium_max": 9,  # n <= this -> "medium", else "high"
}


def _parse_date(value):
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _nearest_close(dates, closes, target, *, before=False):
    """The benchmark close on ``target`` or the nearest available trading day.

    ``before=False`` (entry price) looks forward from ``target`` first, since a purchase
    date can fall on a weekend/holiday the market didn't trade; ``before=True`` (exit
    price) looks backward first, matching how ``price_as_of`` is itself always a real
    session date from the priced trade's own history.
    """
    if not dates:
        return None
    target = target.isoformat() if isinstance(target, date) else str(target)
    index = bisect.bisect_left(dates, target)
    if before:
        if index < len(dates) and dates[index] == target:
            return closes[index]
        if index > 0:
            return closes[index - 1]
        return closes[0] if dates else None
    if index < len(dates):
        return closes[index]
    return closes[-1] if dates else None


def benchmark_return_pct(benchmark, start_date, end_date):
    """SPY's % return from ``start_date`` to ``end_date`` (inclusive), or None without data."""
    if not benchmark or not benchmark.get("dates"):
        return None
    dates, closes = benchmark["dates"], benchmark["closes"]
    start_close = _nearest_close(dates, closes, start_date, before=False)
    end_close = _nearest_close(dates, closes, end_date, before=True)
    if not start_close or not end_close:
        return None
    return (end_close / start_close - 1) * 100


def trade_alpha(row, benchmark):
    """One priced buy's return relative to SPY over the same window, or None if unpriced."""
    realized = row.get("return_since_purchase_pct")
    start = _parse_date(row.get("transaction_date"))
    end = _parse_date(row.get("price_as_of"))
    if realized is None or start is None or end is None or end < start:
        return None
    spy_return = benchmark_return_pct(benchmark, start, end)
    if spy_return is None:
        return None
    return realized - spy_return


def _is_priced_buy(row):
    from build_congress_screen import is_buy
    return bool(row.get("representative")) and is_buy(row.get("transaction_type"))


def raw_stats_by_politician(rows, benchmark):
    """Each politician's un-shrunk alpha observations from their priced disclosed buys."""
    by_rep = {}
    for row in rows:
        if not _is_priced_buy(row):
            continue
        alpha = trade_alpha(row, benchmark)
        if alpha is None:
            continue
        by_rep.setdefault(row["representative"], []).append(alpha)
    return by_rep


def confidence_label(n, config):
    if n <= config["confidence_low_max"]:
        return "low"
    if n <= config["confidence_medium_max"]:
        return "medium"
    return "high"


def performance_score(shrunk_avg_alpha, shrunk_win_rate, config):
    """Blend shrunk alpha and shrunk win rate into one bounded [0, 1] score.

    The alpha term goes through ``tanh`` rather than a linear clamp so one extreme outlier
    trade saturates it instead of dominating the whole politician's score - the multiplicative
    signal_strength formula already lets performance swing a trade's weight by up to 1.6x,
    and an unbounded alpha term compounding with amount and freshness would let a single
    huge, lucky trade produce an implausibly large per-politician swing.
    """
    alpha_component = 0.5 + 0.5 * math.tanh(shrunk_avg_alpha / config["alpha_scale"])
    score = config["alpha_weight"] * alpha_component + config["winrate_weight"] * shrunk_win_rate
    return round(max(0.0, min(1.0, score)), 4)


def compute_performance_scores(rows, *, benchmark, config=None):
    """Every politician's shrunk performance stats, plus the population baseline used for
    both the shrinkage prior and a brand-new politician's default score.

    Returns ``{"politicians": {representative: {...}}, "population": {...}, "config": {...}}``.
    A politician who has never disclosed a priced buy is simply absent from
    ``"politicians"`` - callers fall back to ``"population"`` for them (see
    ``score_for_politician``), which is exactly the shrinkage formula's own n=0 limit.
    """
    settings = {**DEFAULTS, **(config or {})}
    by_rep = raw_stats_by_politician(rows, benchmark)

    pooled = [alpha for alphas in by_rep.values() for alpha in alphas]
    population_mean_alpha = sum(pooled) / len(pooled) if pooled else 0.0
    population_win_rate = (sum(1 for a in pooled if a > 0) / len(pooled)) if pooled else 0.5
    prior_strength = settings["prior_strength"]

    politicians = {}
    for representative, alphas in by_rep.items():
        n = len(alphas)
        raw_avg_alpha = sum(alphas) / n
        raw_wins = sum(1 for a in alphas if a > 0)
        raw_win_rate = raw_wins / n
        shrunk_avg_alpha = (n * raw_avg_alpha + prior_strength * population_mean_alpha) / (n + prior_strength)
        shrunk_win_rate = (raw_wins + prior_strength * population_win_rate) / (n + prior_strength)
        politicians[representative] = {
            "n_priced_buys": n,
            "raw_avg_alpha_pct": round(raw_avg_alpha, 2),
            "raw_win_rate": round(raw_win_rate, 4),
            "avg_alpha_pct": round(shrunk_avg_alpha, 2),
            "win_rate": round(shrunk_win_rate, 4),
            "performance_score": performance_score(shrunk_avg_alpha, shrunk_win_rate, settings),
            "confidence": confidence_label(n, settings),
        }

    population_score = performance_score(population_mean_alpha, population_win_rate, settings)
    return {
        "politicians": politicians,
        "population": {
            "n_priced_buys": len(pooled),
            "avg_alpha_pct": round(population_mean_alpha, 2),
            "win_rate": round(population_win_rate, 4),
            "performance_score": population_score,
        },
        "config": settings,
    }


def score_for_politician(representative, performance):
    """A politician's stats, or the population baseline (shrinkage's own n=0 case) for one
    performance has never seen - never ``None``, so callers always have a number to show."""
    return (performance.get("politicians") or {}).get(representative) or {
        **performance.get("population", {}), "n_priced_buys": 0, "confidence": "low",
    }


def signal_strength(row, performance, *, as_of=None):
    """A trade's badge-facing strength: disclosed size x recency x the filer's performance
    track record. Not directional - it says how much weight this politician's trade
    deserves in general, from the same buy-side track record regardless of whether this
    particular row is itself a buy or a sell.
    """
    from insider_signal import decay

    config = performance.get("config") or DEFAULTS
    as_of_date = as_of or date.today()
    when = _parse_date(row.get("disclosure_date") or row.get("transaction_date"))
    days_since = (as_of_date - when).days if when else None
    freshness = decay(days_since)
    if freshness <= 0:
        return 0.0
    size_component = min(1.0, (row.get("amount_lower") or 0) / config["size_reference"])
    stats = score_for_politician(row.get("representative"), performance)
    multiplier = config["signal_floor"] + config["signal_range"] * stats["performance_score"]
    return round(size_component * freshness * multiplier, 4)


def annotate_row(row, performance, *, as_of=None):
    """The fields ``build_congress_screen.run`` merges onto each published result row."""
    stats = score_for_politician(row.get("representative"), performance)
    return {
        "signal_strength": signal_strength(row, performance, as_of=as_of),
        "performance_score": stats["performance_score"],
        "performance_confidence": stats["confidence"],
    }


def load_spy_benchmark():
    """SPY's committed price series - lazy import, same circular-import avoidance pattern
    ``build_congress_screen.py`` already uses for ``fetch_advisor``/``insider_signal``.
    ``backtest_monthly`` does not import anything from this pipeline's congress modules, so
    this direction is safe; the reverse (importing this module from ``backtest_monthly``)
    would not be."""
    from backtest_monthly import committed_benchmark
    return committed_benchmark("SPY")


def leaderboard(performance, *, top_n=None):
    """The politician leaderboard for publication: performance_score descending, ties
    broken by more priced trades (more evidence beats a shorter hot streak at the same
    score), then name for determinism."""
    rows = [{"politician": representative, **stats}
            for representative, stats in (performance.get("politicians") or {}).items()]
    rows.sort(key=lambda row: (-row["performance_score"], -row["n_priced_buys"], row["politician"]))
    if top_n is not None:
        rows = rows[:top_n]
    for position, row in enumerate(rows, 1):
        row["rank"] = position
    return rows
