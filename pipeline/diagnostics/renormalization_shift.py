"""Before and after: what per-row renormalization did to the top decile's size and liquidity.

Spec amendment SA-2026-08-12-04 replaced zero-filling an unresolved leg with renormalizing the
declared weights across the legs that resolved. The argument for the change is that zero-fill
pulls every thin row toward the cross-sectional mean, that thinness tracks size and liquidity,
and that the screen was therefore running an undeclared size and liquidity tilt inside a rule
presented as conservative.

That is an argument, not a measurement. This module is the measurement. It scores one
cross-section both ways and reports what moved in the traded head of the book:

    market capitalization      median, quartiles, and the decile's share of the largest names
    dollar volume              median and quartiles of 60-day median dollar volume
    idiosyncratic proxy        median 60-day realized volatility
    coverage                   median legs resolved, and how many rows the floor excluded
    membership                 how many names entered and left the top decile

If the distributions barely move, the old tilt was immaterial and the amendment is a tidy-up.
If they move, the tilt was real and the amendment is a defect fix. The point of running it is
that either answer is publishable.

    python pipeline/diagnostics/renormalization_shift.py                     # live screen inputs
    python pipeline/diagnostics/renormalization_shift.py --out report.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from swing_signals import DEFAULT_CONFIG, swing_scores  # noqa: E402

TOP_DECILE_PERCENTILE = 90


def _quantile(values, share):
    ordered = sorted(value for value in values if isinstance(value, (int, float)))
    if not ordered:
        return None
    if len(ordered) == 1:
        return ordered[0]
    position = share * (len(ordered) - 1)
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    weight = position - low
    return ordered[low] * (1 - weight) + ordered[high] * weight


def _distribution(rows, key, factor_key=None):
    values = [((row.get("factors") or {}).get(factor_key) if factor_key else row.get(key))
              for row in rows]
    values = [value for value in values if isinstance(value, (int, float))]
    if not values:
        return {"n": 0, "p25": None, "median": None, "p75": None}
    return {"n": len(values),
            "p25": _quantile(values, .25),
            "median": _quantile(values, .50),
            "p75": _quantile(values, .75)}


def zero_filled_scores(scored, config):
    """Re-rank the same rows on the superseded zero-filled score.

    Uses ``score_zero_filled``, which swing_scores publishes on every row precisely so this
    comparison does not need a second scoring implementation that could drift away from the
    first one.
    """
    config = {**DEFAULT_CONFIG, **(config or {})}
    # The old rule had no legs-resolved floor, so rows the floor now removes are put back for
    # the before side. Comparing the new head against a before side that already applied the
    # new floor would hide half of what the amendment did.
    eligible = [row for row in scored
                if not [code for code in (row.get("reason_codes") or [])
                        if code != "INSUFFICIENT_LEGS_RESOLVED"]]
    ordered = sorted(eligible, key=lambda row: row["score_zero_filled"])
    for rank, row in enumerate(ordered):
        row["_zero_filled_percentile"] = 100 * rank / max(1, len(ordered) - 1)
    return ordered


def top_decile(rows, percentile_key, cutoff=TOP_DECILE_PERCENTILE):
    return [row for row in rows if (row.get(percentile_key) or 0) >= cutoff]


def compare(rows, config=None):
    """Score one cross-section both ways and report what moved in the top decile.

    The sector concentration cap is switched off on both sides. It is a different amendment
    with its own justification, it trims by sector rather than by coverage, and leaving it on
    would mix its effect into a measurement that exists to isolate the scoring change. Run
    pipeline/build_swing_screen.py for the published book, which has the cap on.
    """
    config = {**DEFAULT_CONFIG, "sector_concentration_cap": 1.0, **(config or {})}
    scored = swing_scores(rows, config=config)
    zero_filled_scores(scored, config)

    after = top_decile([row for row in scored if row.get("eligibility")], "percentile")
    before = top_decile(scored, "_zero_filled_percentile")

    after_tickers = {row.get("ticker") for row in after}
    before_tickers = {row.get("ticker") for row in before}

    def profile(book):
        return {
            "names": len(book),
            "market_cap": _distribution(book, "market_cap"),
            "median_dollar_volume_60d": _distribution(book, "median_dollar_volume_60d"),
            "realized_volatility_60d": _distribution(book, None, "realized_volatility_60d"),
            "legs_resolved": _distribution(book, "legs_resolved"),
            "coverage": _distribution(book, "coverage"),
        }

    return {
        "diagnostic": "renormalization_shift",
        "amendment": "SA-2026-08-12-04",
        "universe_scored": len(scored),
        "rows_excluded_by_the_legs_resolved_floor": sum(
            1 for row in scored
            if "INSUFFICIENT_LEGS_RESOLVED" in (row.get("reason_codes") or [])),
        "before_zero_filled": profile(before),
        "after_renormalized": profile(after),
        "top_decile_turnover": {
            "entered": sorted(after_tickers - before_tickers),
            "left": sorted(before_tickers - after_tickers),
            "held": len(after_tickers & before_tickers),
            "share_changed": (round(len(after_tickers ^ before_tickers)
                                    / max(1, len(after_tickers | before_tickers)), 4)),
        },
        "reading": ("A large shift in the market-cap or dollar-volume medians means the "
                    "zero-filled rule was running a size and liquidity tilt nobody declared, "
                    "and the amendment is a defect fix. A small shift means the tilt was "
                    "immaterial on this universe and the amendment is a tidy-up. Both are "
                    "publishable answers and neither was chosen in advance."),
        "caveat": ("One cross-section on one date. This measures the mechanical effect of the "
                   "scoring change, not its effect on returns, which only the prospective "
                   "clock starting 2026-09-01 can report."),
    }


def _live_rows():
    from build_swing_screen import build_rows  # noqa: PLC0415 - heavy import, only for a live run
    from screen_inputs import universe_rows    # noqa: PLC0415

    return build_rows(universe_rows())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=None, help="write the report here instead of stdout")
    args = parser.parse_args(argv)

    rows = _live_rows()
    if not rows:
        print(json.dumps({"status": "no_universe_on_disk"}, indent=2))
        return 1
    report = compare(rows)
    text = json.dumps(report, indent=2, default=str)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(text + "\n")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
