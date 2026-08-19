"""The scored-universe freeze: Phase 5's `in_scored_universe` immutability guarantee.

Rank IC is cross-sectional -- a shifting scored population makes periods incomparable,
and `quantile_spread` needs its bottom quintile to exist every period. Phase 5 lets low
scorers be dropped from the advisor REFRESH queue (`enrichment_eligible: false`) to save
provider budget, but they must remain in the SCORED universe (`in_scored_universe: true`,
scored from price multiples) for as long as the universe is frozen -- 24 periods from the
prospective harness's 2026-09-01 start (pipeline/validation/harness_freeze.json).

This module is the runtime guard: it raises rather than silently publishing a payload that
drops a name the freeze requires stay scored. Before the freeze date it is a no-op by
construction (there is nothing frozen yet), so building and testing it now costs nothing
and closes the gap before it can matter.
"""

from datetime import datetime, timezone

SCORED_UNIVERSE_FREEZE_DATE = "2026-09-01"


class ScoredUniverseViolation(Exception):
    """Raised when a refresh would remove a name the freeze requires stay scored."""


def _tickers(rows):
    return {str(row.get("ticker") or "").upper() for row in rows if row.get("ticker")}


def assert_scored_universe_immutable(previous_rows, new_rows, as_of=None,
                                     freeze_date=SCORED_UNIVERSE_FREEZE_DATE):
    """Raise ``ScoredUniverseViolation`` if ``new_rows`` drops a previously frozen name.

    ``previous_rows``/``new_rows`` are each the full set of scored rows for one refresh
    (``research`` + ``screen_universe`` combined). A no-op before ``freeze_date`` --
    membership is free to change while the universe is still being assembled, and only
    becomes immutable once the prospective clock actually starts.
    """
    as_of = as_of or datetime.now(timezone.utc).isoformat()
    if as_of[:10] < freeze_date:
        return
    previously_scored = {
        str(row.get("ticker") or "").upper()
        for row in previous_rows
        if row.get("ticker") and row.get("in_scored_universe", True)
    }
    if not previously_scored:
        return
    still_scored = {
        str(row.get("ticker") or "").upper()
        for row in new_rows
        if row.get("ticker") and row.get("in_scored_universe", True)
    }
    dropped = sorted(previously_scored - still_scored)
    if dropped:
        raise ScoredUniverseViolation(
            f"{len(dropped)} name(s) removed from the frozen scored universe on or after "
            f"{freeze_date}, violating the 24-period immutability guarantee: {dropped[:10]}"
            + ("..." if len(dropped) > 10 else ""))
