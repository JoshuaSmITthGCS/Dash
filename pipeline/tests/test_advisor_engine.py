import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from advisor_engine import RANKING_WEIGHTS, build_research, technical_factors


class AdvisorEngineTests(unittest.TestCase):
    def test_ranking_is_fundamentals_dominant(self):
        self.assertEqual(RANKING_WEIGHTS, {
            "fundamentals": 0.75, "market_behavior": 0.15, "news_sentiment": 0.10,
        })

    def test_peg_pe_and_price_to_sales_change_the_rank_score(self):
        base = {
            "ticker": "TEST", "name": "Test Co", "sector": "Technology", "is_etf": False,
            "price_to_book": 3, "return_on_equity": 0.18, "free_cash_flow_yield": 0.06,
            "profit_margin": 0.15, "debt_to_equity": 0.6, "current_ratio": 1.5,
            "revenue_growth": 0.10, "earnings_growth": 0.10,
        }
        attractive = {**base, "peg": 0.9, "forward_pe": 20, "price_to_sales": 4}
        expensive = {**base, "peg": 3.2, "forward_pe": 55, "price_to_sales": 26}
        closes = [100 + index * 0.1 for index in range(100)]
        good = build_research("TEST", attractive, closes, closes, [])
        bad = build_research("TEST", expensive, closes, closes, [])
        self.assertGreater(good["components"]["fundamentals"], bad["components"]["fundamentals"])
        self.assertGreater(good["score"], bad["score"])

    def test_technical_score_has_risk_and_relative_strength(self):
        closes = [100 + index * 0.4 for index in range(300)]
        benchmark = [100 + index * 0.1 for index in range(300)]
        volumes = [1_000_000.0] * 300
        score, detail = technical_factors(closes, benchmark, volumes)
        self.assertGreater(score, 50)
        self.assertGreater(detail["relative_strength_20d"], 0)
        self.assertEqual(detail["coverage"], 1.0)

    def test_max_drawdown_and_volume_confirmation_are_scored(self):
        rising = [100 + index for index in range(300)]
        broken = [100 + index for index in range(150)] + [250 - index * 1.2 for index in range(150)]
        volumes = [1_000_000.0] * 300
        healthy_score, healthy = technical_factors(rising, rising, volumes)
        broken_score, damaged = technical_factors(broken, rising, volumes)
        self.assertGreater(healthy_score, broken_score)
        self.assertLess(damaged["max_drawdown_252d"], -30)
        self.assertGreaterEqual(healthy["volume_ratio_60d"], 1.0)

    def test_fundamentals_drive_research_score_and_explanations(self):
        snap = {
            "ticker": "TEST", "name": "Test Co", "sector": "Technology", "is_etf": False,
            "peg": 0.9, "forward_pe": 22, "price_to_sales": 4, "price_to_book": 2.5,
            "return_on_equity": 0.22, "free_cash_flow_yield": 0.08, "profit_margin": 0.21,
            "debt_to_equity": 0.4, "current_ratio": 2.0, "revenue_growth": 0.15,
            "earnings_growth": 0.18, "return_on_invested_capital": 0.21, "cash_conversion": 1.05,
            "interest_coverage": 18, "net_debt_to_ebitda": 0.4, "altman_z": 6.0,
            "ev_to_ebitda": 11, "ev_to_fcf": 20, "fcf_growth_3y": 0.14,
            "operating_margin_trend": 0.02, "net_buyback_yield": 0.03,
            "stock_comp_to_revenue": 0.02, "capex_to_depreciation": 1.1,
            "accruals_ratio": -0.02, "piotroski_f": 8.0, "price_to_tangible_book": 3.0,
            "days_sales_outstanding_trend": -0.02, "inventory_days_trend": 0.01,
        }
        closes = [100 + index * 0.3 for index in range(100)]
        row = build_research("TEST", snap, closes, closes, [], extended=snap)
        self.assertGreater(row["components"]["fundamentals"], 75)
        self.assertIn(row["stance"], ("ATTRACTIVE", "PROMISING"))
        self.assertTrue(any("valuation" in item.lower() for item in row["strengths"]))
        self.assertGreater(row["confidence"], 0.8)
        self.assertEqual(row["recommendation"]["action"], "HOLD")

    def test_two_factors_are_required_before_any_trim(self):
        weak = {
            "ticker": "TEST", "name": "Test Co", "sector": "Technology", "is_etf": False,
            "peg": 4.0, "forward_pe": 70, "price_to_sales": 30, "price_to_book": 18,
            "return_on_equity": 0.01, "free_cash_flow_yield": -0.02, "profit_margin": -0.05,
            "debt_to_equity": 3.5, "current_ratio": 0.6, "revenue_growth": -0.15,
            "earnings_growth": -0.4, "interest_coverage": 1.1, "accruals_ratio": 0.18,
            "piotroski_f": 2.0, "cash_conversion": 0.2, "return_on_invested_capital": 0.01,
        }
        # Fundamentals broken and the chart broken: two independent factors, so guidance acts.
        falling = [200 - index * 0.6 for index in range(300)]
        rising = [100 + index * 0.3 for index in range(300)]
        acted = build_research("TEST", weak, falling, rising, [], extended=weak)
        self.assertIn(acted["recommendation"]["action"], ("TRIM", "SELL"))
        self.assertGreaterEqual(acted["recommendation"]["agreement_count"], 2)
        self.assertGreater(acted["recommendation"]["suggested_trim_pct"], 0)

        # Same broken fundamentals, healthy chart: one factor only, so it is a watch item.
        watched = build_research("TEST", weak, rising, rising, [], extended=weak)
        self.assertEqual(watched["recommendation"]["action"], "WATCH")
        self.assertEqual(watched["recommendation"]["suggested_trim_pct"], 0)

    def test_modifiers_are_bounded_and_explained(self):
        snap = {"ticker": "TEST", "name": "Test Co", "sector": "Technology", "is_etf": False,
                "peg": 1.1, "forward_pe": 22, "price_to_sales": 5, "return_on_equity": 0.18}
        crowded = {"short_percent_of_float": 0.22, "days_to_cover": 9.0,
                   "average_dollar_volume": 2_000_000}
        closes = [100 + index * 0.2 for index in range(300)]
        plain = build_research("TEST", snap, closes, closes, [])
        pressured = build_research("TEST", snap, closes, closes, [], extended=crowded)
        self.assertLess(pressured["score"], plain["score"])
        self.assertGreaterEqual(pressured["modifiers"]["total"], -15)
        self.assertTrue(pressured["modifiers"]["notes"])
        self.assertEqual(plain["base_score"], pressured["base_score"])

    def test_missing_evidence_lowers_confidence(self):
        sparse = {"ticker": "TEST", "name": "Test Co", "sector": "Technology", "is_etf": False, "forward_pe": 20}
        row = build_research("TEST", sparse, [100 + i for i in range(100)], None, [])
        self.assertLess(row["confidence"], 0.5)


if __name__ == "__main__":
    unittest.main()
