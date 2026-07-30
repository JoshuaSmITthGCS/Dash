"""Weekly price series and benchmark-relative outcomes for the site's line charts.

Everything here is pure so the alignment logic and the hypothetical-return arithmetic can
be tested without a network call.
"""

BASIS = 500.0


def weekly_grid(dates, weeks=53):
    """Every seventh date, oldest to newest, ending on the most recent session."""
    if not dates:
        return []
    sampled = list(reversed(dates[::-1][::7]))
    return sampled[-weeks:]


def sample_on(dates, values, grid):
    """Project a daily series onto a shared date grid using the last close at or before each point.

    Holidays and mid-week listings would otherwise knock two lines out of alignment and make
    a comparison chart quietly lie.
    """
    if not dates or not values or len(dates) != len(values):
        return []
    out, index, last = [], 0, None
    for point in grid:
        while index < len(dates) and dates[index] <= point:
            last = values[index]
            index += 1
        out.append(last)
    return out


def series_payload(dates, closes, grid, digits=2):
    """A grid-aligned close series, or None when the overlap is too short to chart."""
    sampled = sample_on(dates, closes, grid)
    present = [value for value in sampled if value is not None]
    if len(present) < 8:
        return None
    first = present[0]
    return {
        "closes": [None if value is None else round(value, digits) for value in sampled],
        # Growth of the standard basis so the chart compares dollars, not price levels.
        "growth": [None if value is None else round(BASIS * value / first, 2) for value in sampled],
    }


def hypothetical_vs_benchmark(stock_growth, benchmark_growth, basis=BASIS):
    """What the same dollars did in this stock versus the S&P 500 over the charted window."""
    stock = [value for value in (stock_growth or []) if value is not None]
    benchmark = [value for value in (benchmark_growth or []) if value is not None]
    if len(stock) < 2 or len(benchmark) < 2:
        return None
    stock_value, benchmark_value = stock[-1], benchmark[-1]
    return {
        "basis": basis,
        "stock_value": round(stock_value, 2),
        "benchmark_value": round(benchmark_value, 2),
        "stock_return_pct": round((stock_value / basis - 1) * 100, 2),
        "benchmark_return_pct": round((benchmark_value / basis - 1) * 100, 2),
        "excess_return_pct": round((stock_value - benchmark_value) / basis * 100, 2),
        "dollars_ahead": round(stock_value - benchmark_value, 2),
    }


def sector_percentiles(rows, key="valuation"):
    """Rank each company's valuation score inside its own sector, 0-100 (higher is cheaper).

    'Cheap for tech' and 'cheap outright' are different claims; absolute multiples only ever
    answer the second one.
    """
    by_sector = {}
    for row in rows:
        value = (row.get("categories") or {}).get(key)
        if value is not None:
            by_sector.setdefault(row.get("sector") or "Unclassified", []).append((row["ticker"], value))
    percentiles = {}
    for peers in by_sector.values():
        if len(peers) < 4:  # too few comparables for a percentile to mean anything
            continue
        ordered = sorted(peers, key=lambda item: item[1])
        for rank, (ticker, _) in enumerate(ordered):
            percentiles[ticker] = round(100 * rank / (len(ordered) - 1), 1)
    return percentiles
