"""Phase 5's rotating enrichment ladder.

A3 (docs/ENRICHMENT-PIPELINE-AUDIT.md SS9) found that the smaller ``enrichment_rotation``
mechanism already live in ``fetch_advisor.py`` resolves "structurally locked out" but still
leaves rank score as the main gate on who gets enriched quickly: incumbents and challengers
are picked by rank, and only the 15-name rotation is rank-independent. This module is the
larger, two-armed replacement the work order specifies: a 20-name ranked ladder that walks
the preliminary-ranked universe on a fixed day-of-cycle plan (never just "prior top N"), plus
a 3-name uniform random draw kept as a genuinely separate, additive budget -- the control arm
that makes the residual rank-conditioning bias measurable instead of merely suspected, which
is what left A3 INCONCLUSIVE before the random arm existed.

Every function here is pure: no network, no disk, no glboal state. ``fetch_advisor.py`` is
responsible for persisting the cycle state (day_index, rank_cursor, enriched_this_cycle,
attempt_counts) between refreshes and for actually calling the enrichment providers with the
selection this module returns.
"""

def theme_exposure_from_screen(theme_by_ticker):
    """Per-ticker theme exposure for the ladder's Day 1, reduced from the theme screen's
    published ``by_ticker`` block (one ticker can qualify for several themes).

    Takes the maximum exposure across qualifying themes: a company's ladder priority
    should reflect its strongest thematic exposure signal, not be diluted by every
    weaker theme it also brushes up against.
    """
    result = {}
    for ticker, entries in (theme_by_ticker or {}).items():
        exposures = [entry.get("theme_exposure_score") for entry in (entries or [])
                    if isinstance(entry.get("theme_exposure_score"), (int, float))]
        if exposures:
            result[ticker] = max(exposures)
    return result


LADDER_RANKED_SIZE = 20
LADDER_RANDOM_SIZE = 3
LADDER_MAX_RETRY_ATTEMPTS = 3

DAY_TOP_RANKED = 0
DAY_THEME_EXPOSURE = 1


def ladder_day_slots(day_index, preliminary_ranked_symbols, theme_exposure_by_ticker,
                     already_enriched_this_cycle, rank_cursor, size=LADDER_RANKED_SIZE):
    """The ranked-ladder names for one day of the cycle.

    ``day_index`` 0: the current top ``size`` names by preliminary rank -- ranks are
    never skipped here even if one is already enriched from a prior cycle, since "the
    current leaders get re-enriched every cycle" is the point of this day.

    ``day_index`` 1: theme-sourced names outside the top ``size``, ranked by
    ``theme_exposure_by_ticker`` -- filing-evidence exposure, never ``opportunity``,
    which partly reflects enrichment status already (a name's business-quality leg
    falls back to price multiples until it is enriched, so ranking by opportunity would
    quietly re-favor names the ladder exists to reach). A name with no theme exposure
    at all is never a candidate on this day.

    ``day_index`` 2+: the next ``size`` NOT-yet-enriched-this-cycle names from
    ``preliminary_ranked_symbols``, walking forward from ``rank_cursor``. The window
    this scans widens past ``size`` ranks whenever overlap with names already enriched
    through another channel (incumbents, portfolio holdings, a prior ladder day, the
    random arm) forces it to skip further to find ``size`` fresh names -- this is
    deliberate, not a bug: the work order's own worked example has Day 3-4 each cover
    a 20-rank band but Day 5 cover a 40-rank band (61-100), which is exactly what
    happens when cumulative overlap by the fifth day of a cycle forces a wider scan.
    There is no fixed per-day width; there is only "the next ``size`` names not
    already spoken for."

    Returns ``(symbols, new_rank_cursor)``. ``new_rank_cursor`` must be threaded into
    the next rank-band day's call (day_index 2 and up) so the walk never rescans ranks
    it has already consumed or skipped.
    """
    enriched = set(already_enriched_this_cycle)
    if day_index == DAY_TOP_RANKED:
        return list(preliminary_ranked_symbols[:size]), rank_cursor
    if day_index == DAY_THEME_EXPOSURE:
        top_ranked = set(preliminary_ranked_symbols[:size])
        outsiders = (
            (ticker, exposure) for ticker, exposure in theme_exposure_by_ticker.items()
            if ticker not in top_ranked and ticker not in enriched
            and isinstance(exposure, (int, float))
        )
        ranked = sorted(outsiders, key=lambda item: (-item[1], item[0]))
        return [ticker for ticker, _ in ranked[:size]], rank_cursor
    symbols = []
    cursor = max(rank_cursor, size)
    universe_size = len(preliminary_ranked_symbols)
    while len(symbols) < size and cursor < universe_size:
        candidate = preliminary_ranked_symbols[cursor]
        cursor += 1
        if candidate in enriched:
            continue
        symbols.append(candidate)
    return symbols, cursor


def random_arm_slots(unenriched_symbols, already_selected, rng, size=LADDER_RANDOM_SIZE):
    """The additive random-draw control-arm names for one day.

    Uniform draw from names not yet enriched this cycle and not already claimed by the
    day's ranked ladder -- this budget is never carved from the 20 (see module
    docstring). Tag ``enrichment_source: "random"`` on whatever the caller does with
    this result; that tag, not the selection mechanism, is what lets A3's Compare view
    (docs/QUESTIONS-FOR-OWNER.md question 1) separate "this name looks strong because
    it is strong" from "this name looks strong because the ladder happened to reach
    it."
    """
    claimed = set(already_selected)
    pool = [symbol for symbol in unenriched_symbols if symbol not in claimed]
    if len(pool) <= size:
        return sorted(pool)
    return sorted(rng.sample(pool, size))


def av_quota_order(random_arm_symbols, coverage_ages, remainder_symbols, rng):
    """Reverse-rank Alpha Vantage pull order for one day: never top-down by rank.

    Priority: (1) random-arm names, ordered isn't meaningful within this tier so it is
    randomized outright; (2) everything else, ordered by largest
    ``coverage_ages[ticker]`` (days_since_last_successful_enrichment) -- the most
    statement-starved first, with ties (including every name at age 0/unknown, which
    is effectively "the remainder" the work order calls tier 3) broken randomly rather
    than by any fixed criterion, so quota exhaustion does not deterministically strike
    the same names every cycle.

    Ranking by preliminary score here would restore, one layer beneath the ladder, the
    exact rank-conditioning the ladder exists to remove.
    """
    random_set = set(random_arm_symbols)
    tier_one = list(random_arm_symbols)
    rng.shuffle(tier_one)
    remaining = [symbol for symbol in remainder_symbols if symbol not in random_set]
    tiebreak = {symbol: rng.random() for symbol in remaining}
    tier_two = sorted(remaining, key=lambda symbol: (-coverage_ages.get(symbol, 0), tiebreak[symbol]))
    return [*tier_one, *tier_two]


def advance_retry_queue(failed_symbols, attempt_counts, max_attempts=LADDER_MAX_RETRY_ATTEMPTS):
    """Classify a day's failed pulls: retry at the front of tomorrow's ranked slate, or
    give up.

    Under a daily refresh a failed pull retries tomorrow; under a rotation it would
    otherwise wait a full cycle at the same failure rate, 5-7x the exposure -- this is
    why a failed name is queued for the FRONT of the next ranked slate (never the
    random arm, which must stay a clean uniform draw) rather than simply waiting for
    its next scheduled ladder turn.

    Returns ``(retry_symbols, persistent_failures, updated_attempt_counts)``. A name
    reaching ``max_attempts`` consecutive failures is marked persistent, dropped from
    the retry queue, and re-enters only through the normal ladder cycle -- an
    unenrichable name must not consume the front of every future slate forever.
    """
    updated = dict(attempt_counts)
    retry, persistent = [], []
    for symbol in failed_symbols:
        attempts = updated.get(symbol, 0) + 1
        updated[symbol] = attempts
        if attempts >= max_attempts:
            persistent.append(symbol)
        else:
            retry.append(symbol)
    return retry, persistent, updated


def reset_attempt_count(symbol, attempt_counts):
    """A successful enrichment clears whatever consecutive-failure count a name carried."""
    if symbol not in attempt_counts:
        return attempt_counts
    updated = dict(attempt_counts)
    del updated[symbol]
    return updated
