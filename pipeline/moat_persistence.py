"""Moat persistence: how many recent fiscal years cleared the bar on both quality metrics.

This is a proxy, not a judgment. "Moat" in the qualitative sense — brand, network effects,
switching costs, regulatory capture, a durable cost advantage — is not observable from SEC
XBRL facts, and this module makes no attempt to read for any of it. What it measures instead
is narrower and mechanical: whether ``return_on_invested_capital`` and
``gross_profits_to_assets`` (the two profitability metrics `settings.json` already weights on
published evidence — Novy-Marx and the ROIC literature) have both stayed above their existing
"good" band, not just in the latest filing but across a multi-year trailing window. A company
whose evidence-backed profitability metrics have held up for five years is better evidence of
some durable advantage than the same metrics measured once; it is not proof of one, and a
company riding a multi-year commodity cycle or not yet disrupted by a new entrant can score
identically to one with a genuine structural edge.

The whole computation reuses ``pipeline/pit_derive.py`` against the SEC XBRL history already
backfilled to ``pipeline/data/pit/fundamentals/`` (`build_pit_fundamentals.py`) — no new data,
no network call. Each reading in the window is a trailing-twelve-month figure as of one year
before the last, exactly `pit_derive.growth`'s own "one year back" convention, so a value is
never visible before its filing date.

**Informational only.** Like `return_attribution` and `reverse_dcf`, this has no prospective
IC history to validate against yet and is not wired into `fundamentals.metric_weights` — see
`pipeline/config/settings.json`'s `moat_persistence` block and `docs/VALIDATION-METHODOLOGY.md`
for what promoting it to a scored input would require.
"""

from datetime import date, timedelta

from pit_derive import derive

DEFAULTS = {
    "years": 5,
    "minimum_years": 4,
}


def _gross_profits_to_assets(reading):
    gross_profit = reading["components"].get("gross_profit")
    assets = reading["components"].get("assets")
    if gross_profit is None or assets in (None, 0):
        return None
    return gross_profit / assets


def persistence_readings(observations, when, *, years, cik=None):
    """One reading per year in the window, newest first, each a year apart.

    Every reading is a trailing-twelve-month figure as of that anchor date — the same
    point-in-time machinery `pit_derive.derive` already uses, so a value is never visible
    before its filing date. A reading whose inputs were not yet filed is `None`, not defaulted.
    """
    anchor = date.fromisoformat(str(when)[:10])
    readings = []
    for offset in range(years):
        as_of = (anchor - timedelta(days=365 * offset)).isoformat()
        reading = derive(observations, as_of, cik=cik)
        readings.append({
            "as_of": as_of,
            "return_on_invested_capital": reading["metrics"]["return_on_invested_capital"],
            "gross_profits_to_assets": _gross_profits_to_assets(reading),
        })
    return readings


def moat_persistence(observations, when, *, cik=None, good_min_roic, good_min_gpa,
                      years=None, minimum_years=None):
    """Fraction of the trailing ``years`` years both quality metrics cleared their good band.

    ``good_min_roic``/``good_min_gpa`` are passed in rather than duplicated here — callers
    should pass `settings.json`'s existing `fundamentals.return_on_invested_capital.good_min`
    and `fundamentals.gross_profits_to_assets.good_min` so this reads the same bar the champion
    score already uses, not a second one that can drift out of sync.

    Returns ``{"available": False, ...}`` (absent, not defaulted) when fewer than
    ``minimum_years`` of the window resolved both inputs — a short or gappy filing history
    should not report a confident fraction over 1-2 known years.
    """
    years = years if years is not None else DEFAULTS["years"]
    minimum_years = minimum_years if minimum_years is not None else DEFAULTS["minimum_years"]
    readings = persistence_readings(observations, when, years=years, cik=cik)
    resolved = [r for r in readings if r["return_on_invested_capital"] is not None
                and r["gross_profits_to_assets"] is not None]
    if len(resolved) < minimum_years:
        return {
            "available": False,
            "years_resolved": len(resolved),
            "years_requested": years,
            "readings": readings,
            "reason": f"fewer than {minimum_years} of the last {years} years had both "
                      "return_on_invested_capital and gross_profits_to_assets on file",
        }
    qualifying = [r for r in resolved if r["return_on_invested_capital"] >= good_min_roic
                  and r["gross_profits_to_assets"] >= good_min_gpa]
    # resolved[0] is the most recent anchor, resolved[-1] the oldest -- persistence_readings
    # returns newest first.
    newest, oldest = resolved[0], resolved[-1]
    delta = newest["return_on_invested_capital"] - oldest["return_on_invested_capital"]
    trend = "improving" if delta > 0.01 else "declining" if delta < -0.01 else "stable"
    return {
        "available": True,
        "persistence_fraction": round(len(qualifying) / len(resolved), 3),
        "years_resolved": len(resolved),
        "years_qualifying": len(qualifying),
        "years_requested": years,
        "trend": trend,
        "readings": readings,
        "method": "fraction of the last N trailing-twelve-month years where both "
                  "return_on_invested_capital and gross_profits_to_assets cleared the "
                  "same 'good' band the champion score already uses",
    }
