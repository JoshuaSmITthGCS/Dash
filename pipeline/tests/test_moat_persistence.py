"""Moat persistence: a fraction of qualifying trailing years, absent when the window is short.

Every observation here is annual-only (no quarters), which forces `pit_derive.derive`'s
`trailing_twelve_months` fallback to "latest filed annual" -- the simplest fixture that still
exercises the real point-in-time derivation this module builds on, matching the style of
`test_pit_derive.py`.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from moat_persistence import moat_persistence, persistence_readings

GOOD_ROIC = 0.13
GOOD_GPA = 0.22


def annual(concept, end, value, filed):
    return {"concept": concept, "period_start": None, "period_end": end, "value": value,
            "filed": filed, "available_at": filed, "period_type": "annual",
            "unit": "USD", "accession": f"{concept}-{end}"}


def instant(concept, end, value, filed):
    return {"concept": concept, "period_start": None, "period_end": end, "value": value,
            "filed": filed, "available_at": filed, "period_type": "instant",
            "unit": "USD", "accession": f"{concept}-{end}"}


def fiscal_year(year, *, revenue, gross_profit, operating_income, assets, equity):
    """One fiscal year's worth of observations, filed shortly after year-end.

    Just enough concepts for `return_on_invested_capital` and `gross_profits_to_assets` to
    resolve: revenue, gross_profit, operating_income (flows), assets/equity/long_term_debt
    (instants). `long_term_debt` is filed as zero rather than omitted: pit_derive.derive only
    resolves `invested_capital` when both `equity` and (long- or short-term) `debt` are
    present, even if debt is zero -- an omitted debt concept leaves `invested_capital`, and so
    `return_on_invested_capital`, unresolved. No tax rows, so NOPAT falls back to
    `operating_income` itself (pit_derive.derive's documented behavior when the tax ratio
    can't be computed).
    """
    end = f"{year}-12-31"
    filed = f"{year + 1}-02-15"
    return [
        annual("revenue", end, revenue, filed),
        annual("gross_profit", end, gross_profit, filed),
        annual("operating_income", end, operating_income, filed),
        instant("assets", end, assets, filed),
        instant("equity", end, equity, filed),
        instant("long_term_debt", end, 0, filed),
    ]


def observations_for(years_data):
    rows = []
    for year, values in years_data.items():
        rows.extend(fiscal_year(year, **values))
    return rows


HIGH_QUALITY_YEAR = dict(revenue=1000, gross_profit=400, operating_income=200,
                          assets=800, equity=800)
LOW_QUALITY_YEAR = dict(revenue=1000, gross_profit=150, operating_income=50,
                         assets=800, equity=800)


class PersistenceReadingsTests(unittest.TestCase):
    def test_five_readings_newest_first_one_year_apart(self):
        observations = observations_for({y: HIGH_QUALITY_YEAR for y in range(2020, 2026)})
        readings = persistence_readings(observations, "2026-06-01", years=5)
        self.assertEqual(len(readings), 5)
        as_of_dates = [r["as_of"] for r in readings]
        self.assertEqual(as_of_dates, sorted(as_of_dates, reverse=True))

    def test_a_reading_before_any_filing_is_none_not_defaulted(self):
        observations = observations_for({2025: HIGH_QUALITY_YEAR})
        readings = persistence_readings(observations, "2026-06-01", years=5)
        # Only the newest anchor (2026-06-01, after the 2025 10-K was filed) resolves;
        # anchors four and three years further back predate any filing.
        self.assertIsNotNone(readings[0]["return_on_invested_capital"])
        self.assertIsNone(readings[-1]["return_on_invested_capital"])


class MoatPersistenceTests(unittest.TestCase):
    def test_consistently_high_quality_scores_full_persistence(self):
        observations = observations_for({y: HIGH_QUALITY_YEAR for y in range(2020, 2026)})
        result = moat_persistence(observations, "2026-06-01", good_min_roic=GOOD_ROIC,
                                  good_min_gpa=GOOD_GPA, years=5, minimum_years=4)
        self.assertTrue(result["available"])
        self.assertEqual(result["persistence_fraction"], 1.0)
        self.assertEqual(result["trend"], "stable")

    def test_consistently_low_quality_scores_zero_persistence(self):
        observations = observations_for({y: LOW_QUALITY_YEAR for y in range(2020, 2026)})
        result = moat_persistence(observations, "2026-06-01", good_min_roic=GOOD_ROIC,
                                  good_min_gpa=GOOD_GPA, years=5, minimum_years=4)
        self.assertTrue(result["available"])
        self.assertEqual(result["persistence_fraction"], 0.0)

    def test_insufficient_history_is_unavailable_not_a_low_score(self):
        observations = observations_for({2025: HIGH_QUALITY_YEAR, 2024: HIGH_QUALITY_YEAR})
        result = moat_persistence(observations, "2026-06-01", good_min_roic=GOOD_ROIC,
                                  good_min_gpa=GOOD_GPA, years=5, minimum_years=4)
        self.assertFalse(result["available"])
        self.assertNotIn("persistence_fraction", result)
        self.assertLess(result["years_resolved"], 4)

    def test_recent_decline_from_a_prior_high_quality_run_is_flagged_declining(self):
        years_data = {y: HIGH_QUALITY_YEAR for y in range(2020, 2024)}
        years_data.update({2024: LOW_QUALITY_YEAR, 2025: LOW_QUALITY_YEAR})
        observations = observations_for(years_data)
        result = moat_persistence(observations, "2026-06-01", good_min_roic=GOOD_ROIC,
                                  good_min_gpa=GOOD_GPA, years=5, minimum_years=4)
        self.assertTrue(result["available"])
        self.assertEqual(result["trend"], "declining")
        self.assertLess(result["persistence_fraction"], 1.0)

    def test_missing_gross_profit_entirely_leaves_a_year_unresolved(self):
        """ROIC resolves fine (revenue/operating_income/assets/equity/debt are all present);
        gross_profits_to_assets never does, so no year counts as resolved even though the
        other half of the pair is available every year -- a reading is only as good as its
        weakest required input, not an average of what happened to be on file."""
        rows = []
        for year in range(2020, 2026):
            end, filed = f"{year}-12-31", f"{year + 1}-02-15"
            rows += [annual("revenue", end, 1000, filed),
                     annual("operating_income", end, 200, filed),
                     instant("assets", end, 800, filed),
                     instant("equity", end, 800, filed),
                     instant("long_term_debt", end, 0, filed)]
        readings = persistence_readings(rows, "2026-06-01", years=5)
        self.assertTrue(any(r["return_on_invested_capital"] is not None for r in readings))
        self.assertTrue(all(r["gross_profits_to_assets"] is None for r in readings))
        result = moat_persistence(rows, "2026-06-01", good_min_roic=GOOD_ROIC,
                                  good_min_gpa=GOOD_GPA, years=5, minimum_years=4)
        self.assertFalse(result["available"])


if __name__ == "__main__":
    unittest.main()
