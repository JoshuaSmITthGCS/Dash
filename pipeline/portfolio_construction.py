"""Turnover controls: stop trading on noise without stopping trading on information.

The published backtest replaces **64.9% of a 20-name book every month**, cycling 397 distinct
tickers through 20 slots over five years, from a signal that is 78% fundamentals reading inputs
that update quarterly. Something with a much shorter half-life is driving the ranking, and every
one of those trades is charged for.

`docs/P0-Q2-TURNOVER.md` measured what moves the score at the refresh-to-refresh horizon and
found the brief's leading hypothesis was probably wrong: band-crossing on effectively unchanged
inputs accounted for 0.42% of score-change events, while metric availability flicker accounted
for 96.72%. That points at coverage consistency rather than discretization. But whatever the
cause, a portfolio does not have to act on every rank wobble, and these controls make that
choice explicit and testable instead of implicit.

Each control is a pure function over `(previous_holdings, ranked_candidates)`. They are
**challengers**, not champion behaviour: `backtest_monthly.py` exposes them behind flags that
default to the existing unbuffered selection, so nothing changes unless it is asked for.

Whether any of them improves net-of-cost return cannot be measured here -- that needs a backtest
re-run over ~860 names of daily price history, which needs network access. What *is* established
here is that each behaves exactly as specified, which is the precondition for trusting the
measurement when it runs.

Usage: imported by backtest_monthly.py; see --rank-buffer / --min-holding-months /
--score-smoothing / --replacement-margin.
"""

from collections import OrderedDict

# Challenger grids, fixed in advance and deliberately small. A wide sweep over these would be
# the data-snooping this whole exercise exists to avoid, and would inflate the trial count that
# feeds Deflated Sharpe and PBO.
RANK_BUFFER_MULTIPLES = (1.25, 1.5, 2.0)
MINIMUM_HOLDING_MONTHS = (1, 3, 6)
SCORE_SMOOTHING_ALPHAS = (0.5, 0.7)
REPLACEMENT_MARGINS = (2.0, 5.0)


def select_top_n(ranked, top_n):
    """The champion's behaviour: take the top N every period, whatever moved."""
    return [row["ticker"] for row in ranked[:top_n]]


def rank_buffer_selection(previous_holdings, ranked, top_n, buffer_multiple=1.5):
    """BUY when rank <= N, HOLD while rank <= buffer_multiple * N, SELL once past it.

    A name that drifts from rank 18 to rank 22 has not told you anything: it is inside the
    noise band of a ranking whose inputs update quarterly. Selling it and buying rank 19 pays a
    full round trip for no information. The buffer makes incumbency worth something, bounded --
    past the outer band the name leaves regardless.
    """
    if buffer_multiple < 1.0:
        raise ValueError("buffer_multiple must be at least 1.0")
    outer = int(round(top_n * buffer_multiple))
    rank_of = {row["ticker"]: index + 1 for index, row in enumerate(ranked)}
    held = [ticker for ticker in previous_holdings
            if rank_of.get(ticker, len(ranked) + 1) <= outer]
    selected = OrderedDict((ticker, None) for ticker in held[:top_n])
    for row in ranked:
        if len(selected) >= top_n:
            break
        selected.setdefault(row["ticker"], None)
    return list(selected)


def minimum_holding_selection(previous_holdings, ranked, top_n, held_months,
                              minimum_months=3, thesis_break_rank=None):
    """Hold a name for at least ``minimum_months`` unless its thesis breaks.

    Without an escape hatch this is dangerous: a name that collapses would be held anyway. So
    ``thesis_break_rank`` (default: outside the top 3N) releases the floor. That keeps the rule
    from becoming "ignore bad news for six months", which is not a turnover control, it is a
    refusal to update.
    """
    if minimum_months < 1:
        raise ValueError("minimum_months must be at least 1")
    break_rank = thesis_break_rank if thesis_break_rank is not None else top_n * 3
    rank_of = {row["ticker"]: index + 1 for index, row in enumerate(ranked)}
    locked = [
        ticker for ticker in previous_holdings
        if held_months.get(ticker, 0) < minimum_months
        and rank_of.get(ticker, len(ranked) + 1) <= break_rank
    ]
    selected = OrderedDict((ticker, None) for ticker in locked[:top_n])
    for row in ranked:
        if len(selected) >= top_n:
            break
        selected.setdefault(row["ticker"], None)
    return list(selected)


def smooth_scores(previous_scores, ranked, alpha=0.7):
    """Exponentially weighted score smoothing: ``alpha * new + (1 - alpha) * prior``.

    Applied to the score before ranking rather than to the holdings after it, so it dampens the
    input rather than overriding the decision. A name with no prior score enters at its own
    value -- seeding it at a neutral prior would penalize every new name for being new.
    """
    if not 0.0 < alpha <= 1.0:
        raise ValueError("alpha must be in (0, 1]")
    smoothed = []
    for row in ranked:
        prior = previous_scores.get(row["ticker"])
        score = row["score"] if prior is None else alpha * row["score"] + (1 - alpha) * prior
        smoothed.append({**row, "score": score, "raw_score": row["score"]})
    smoothed.sort(key=lambda row: row["score"], reverse=True)
    return smoothed


def replacement_margin_selection(previous_holdings, ranked, top_n, margin=2.0):
    """A challenger must beat the incumbent it displaces by ``margin`` score points.

    Rank buffering asks "has this name fallen far enough to sell". This asks the complementary
    question: "is the replacement actually better, or merely different". A 0.1-point score gap
    is not a reason to pay a round trip.
    """
    if margin < 0:
        raise ValueError("margin must be non-negative")
    score_of = {row["ticker"]: row["score"] for row in ranked}
    incumbents = [ticker for ticker in previous_holdings if ticker in score_of]
    selected = OrderedDict()
    challengers = [row for row in ranked if row["ticker"] not in set(incumbents)]
    # Rank incumbents and challengers together, but require a challenger to clear the worst
    # incumbent it would displace by the margin before it takes the slot.
    ordered_incumbents = sorted(incumbents, key=lambda ticker: -score_of[ticker])
    keep = ordered_incumbents[:top_n]
    for ticker in keep:
        selected[ticker] = None
    for row in challengers:
        if len(selected) < top_n:
            selected.setdefault(row["ticker"], None)
            continue
        weakest = min(selected, key=lambda ticker: score_of.get(ticker, float("-inf")))
        weakest_score = score_of.get(weakest, float("-inf"))
        if row["score"] - weakest_score > margin:
            del selected[weakest]
            selected[row["ticker"]] = None
    return list(selected)


def turnover(previous_holdings, selected):
    """One-way turnover: the share of the book replaced."""
    if not selected:
        return 0.0
    previous = set(previous_holdings)
    if not previous:
        return 1.0
    return len(set(selected) - previous) / len(selected)


def apply_controls(previous_holdings, ranked, top_n, *, previous_scores=None, held_months=None,
                   rank_buffer=None, minimum_months=None, smoothing_alpha=None,
                   replacement_margin=None):
    """Compose the controls in the only order that makes sense.

    Smoothing acts on scores, so it runs first and changes the ranking every later control
    reads. The holding-period floor is a hard constraint and outranks the soft ones. The rank
    buffer and the replacement margin are both soft and are applied in that order.

    Every control defaults to off, so calling this with no options reproduces ``select_top_n``
    exactly -- proved by test.
    """
    previous_scores = previous_scores or {}
    held_months = held_months or {}
    if smoothing_alpha is not None:
        ranked = smooth_scores(previous_scores, ranked, smoothing_alpha)
    if minimum_months is not None:
        return minimum_holding_selection(previous_holdings, ranked, top_n, held_months,
                                         minimum_months)
    if rank_buffer is not None:
        return rank_buffer_selection(previous_holdings, ranked, top_n, rank_buffer)
    if replacement_margin is not None:
        return replacement_margin_selection(previous_holdings, ranked, top_n,
                                            replacement_margin)
    return select_top_n(ranked, top_n)
