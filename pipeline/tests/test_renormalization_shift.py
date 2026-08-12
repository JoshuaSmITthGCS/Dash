"""The before/after diagnostic for spec amendment SA-2026-08-12-04.

The amendment's justification is that zero-filling an unresolved leg muted thin rows, that
thinness tracks size and liquidity, and that the screen therefore carried an undeclared tilt.
These tests check the diagnostic can actually detect such a tilt when one is present, because
a measurement that always reports "no change" is not evidence of anything.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "diagnostics"))

import renormalization_shift


def row(ticker, *, market_cap, dollar_volume, legs, strength):
    """A row resolving ``legs`` of the five, all pointing the same way at ``strength``."""
    factors = {"realized_volatility_60d": .30}
    available = [("revision_breadth_30d", strength),
                 ("volume_ratio_1d_50d", 1 + strength),
                 ("high_52w_drawdown_sigmas", strength - 1),
                 ("return_5d", -strength),
                 ("standardized_unexpected_earnings", strength)]
    for name, value in available[:legs]:
        factors[name] = value
    return {"ticker": ticker, "price": 50.0, "market_cap": market_cap,
            "median_dollar_volume_60d": dollar_volume, "adv_20d_dollar_volume": dollar_volume,
            "history_sessions": 400, "sector": "Technology", "factors": factors}


def test_the_diagnostic_reports_both_books_and_what_moved_between_them():
    rows = [row(f"T{index}", market_cap=1e9 + index * 1e9, dollar_volume=5e7,
                legs=5, strength=index / 20)
            for index in range(20)]

    report = renormalization_shift.compare(rows)

    assert report["amendment"] == "SA-2026-08-12-04"
    assert report["universe_scored"] == 20
    assert report["before_zero_filled"]["names"] > 0
    assert report["after_renormalized"]["names"] > 0
    assert set(report["top_decile_turnover"]) == {"entered", "left", "held", "share_changed"}
    # With every row resolving all five legs, the two rules are arithmetically identical and
    # the diagnostic must say so rather than manufacturing a difference.
    assert report["top_decile_turnover"]["share_changed"] == 0.0


def test_the_diagnostic_detects_a_tilt_when_thin_rows_are_the_small_illiquid_ones():
    """The tilt the amendment exists to remove, constructed deliberately.

    Small illiquid names resolve three legs and large liquid ones resolve five. Under
    zero-filling the thin rows are muted toward the mean and cannot reach the head; under
    renormalization their resolved legs carry full weight and they can. The diagnostic has to
    surface that as a market-cap shift rather than leave it to be inferred.
    """
    rows = []
    # Large, liquid, five legs resolved, spread across the whole range of the composite.
    for index in range(20):
        rows.append(row(f"LARGE{index}", market_cap=8e10, dollar_volume=9e8,
                        legs=5, strength=-1 + 2 * index / 19))
    # Smaller, thinner, three legs resolved, and strong on all three of them.
    for index in range(4):
        rows.append(row(f"SMALL{index}", market_cap=4e8, dollar_volume=3e7,
                        legs=3, strength=1.4 + index / 100))

    report = renormalization_shift.compare(rows)

    before = report["before_zero_filled"]["market_cap"]["median"]
    after = report["after_renormalized"]["market_cap"]["median"]
    assert before is not None and after is not None
    # The head gets smaller and less liquid once thin rows stop being muted.
    assert after < before
    assert (report["after_renormalized"]["median_dollar_volume_60d"]["median"]
            < report["before_zero_filled"]["median_dollar_volume_60d"]["median"])
    assert report["top_decile_turnover"]["share_changed"] > 0
    assert any(ticker.startswith("SMALL")
               for ticker in report["top_decile_turnover"]["entered"])


def test_rows_the_legs_resolved_floor_removes_are_counted_and_still_in_the_before_book():
    """The before side must not silently inherit the new floor, or half the change hides."""
    rows = [row(f"THIN{index}", market_cap=1e9, dollar_volume=5e7, legs=2, strength=.9)
            for index in range(6)]
    rows += [row(f"THICK{index}", market_cap=1e9, dollar_volume=5e7, legs=5, strength=.1)
             for index in range(6)]

    report = renormalization_shift.compare(rows)

    assert report["rows_excluded_by_the_legs_resolved_floor"] == 6
    assert report["before_zero_filled"]["names"] > 0
    assert all(not ticker.startswith("THIN")
               for ticker in report["top_decile_turnover"]["entered"])
