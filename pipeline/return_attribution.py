"""Multiple-expansion decomposition: how much of a realized return was re-rating vs delivery.

Price = Multiple x Fundamental (e.g. Price = P/E x EPS), so the return between two dates
factors cleanly without ever needing the fundamental itself -- only the two dates' price and
the same valuation multiple, both of which pipeline/pit_store.py already archives every run:

    price_now / price_then = (multiple_now / multiple_then) * (fundamental_now / fundamental_then)

The right-hand side's first factor is re-rating (a pure multiple-change effect); the second,
solved for algebraically, is "delivery" -- the fundamental growth the market's re-rating choice
implies, without ever measuring EPS/FFO/ARR directly. A name whose return over the window is
mostly the first factor has been re-rated, not delivered to (Mauboussin & Rappaport's
return-attribution framing) -- exactly the momentum-free "is this priced in" read this pipeline
already applies via pipeline/reverse_dcf.py's market-implied growth, from a different angle.

This is a return-attribution *explanation* of what already happened, not a price-momentum
signal read forward: nothing here ranks or selects on the direction of a recent price move, and
it is never wired into pipeline/themes.py's per-company exposure scoring, where a price-derived
signal is rejected outright. It is informational only, like reverse_dcf and the sector metrics
in fundamentals_extended.py, for the same reason: a brand-new signal has no prospective IC
history to validate against yet.
"""


def decompose_return(*, price_then, price_now, multiple_then, multiple_now):
    """One window's return split into multiple_change (re-rating) and delivery_growth.

    Returns ``None`` when the inputs can't support the decomposition: a non-positive price or
    multiple makes the ratio meaningless, and a multiple that fell to (or through) zero percent
    change of the wrong sign can make the implied delivery growth undefined.
    """
    if price_then is None or price_now is None or multiple_then is None or multiple_now is None:
        return None
    if price_then <= 0 or price_now <= 0 or multiple_then <= 0 or multiple_now <= 0:
        return None
    total_return = price_now / price_then - 1
    multiple_change = multiple_now / multiple_then - 1
    denominator = 1 + multiple_change
    if denominator == 0:
        return None
    delivery_growth = (1 + total_return) / denominator - 1
    # A read only meaningful when the stock actually moved: re-rating share of a ~0% return is
    # a divide-by-noise question, not a real "how did we get here" answer.
    mostly_re_rating = (
        abs(total_return) > 0.01 and abs(multiple_change) > abs(delivery_growth)
        and (multiple_change > 0) == (total_return > 0)
    )
    return {
        "total_return": round(total_return, 4),
        "multiple_change": round(multiple_change, 4),
        "delivery_growth": round(delivery_growth, 4),
        "mostly_re_rating": mostly_re_rating,
    }


def attribute_return_from_history(ticker, *, multiple_field, months_back, pit_store):
    """Pull the two dated observations this needs from pipeline/pit_store.py and decompose.

    ``pit_store`` is passed in (not imported) so this stays testable against a fake store with
    no file I/O; the real caller passes the ``pit_store`` module itself, whose ``as_of`` already
    returns "latest observed on or before this date," which is exactly the point-in-time
    semantics a lookback needs.
    """
    from datetime import date, timedelta

    now_state = pit_store.as_of(ticker, None)
    cutoff = (date.today() - timedelta(days=months_back * 30)).isoformat()
    then_state = pit_store.as_of(ticker, cutoff)
    if not now_state or not then_state:
        return None
    now_values, then_values = now_state["values"], then_state["values"]
    result = decompose_return(
        price_then=then_values.get("price"), price_now=now_values.get("price"),
        multiple_then=then_values.get(multiple_field), multiple_now=now_values.get(multiple_field))
    if result is None:
        return None
    return {**result, "multiple_field": multiple_field, "months_back": months_back,
           "as_of_then": then_state.get("as_of"),
           "observed_at_now": (now_state.get("observed_at") or {}).get("price")}
