import os
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fred import FredClient, FredError, NOTICE, derive_regime


class FredTests(unittest.TestCase):
    def test_derive_regime_is_bounded_and_reports_coverage(self):
        monthly_cpi = [{"date": f"2026-{month:02d}-01", "value": 310 - month * 0.3} for month in range(1, 15)]
        regime = derive_regime({
            "treasury_10y": [{"date": "2026-07-29", "value": 4.2}, {"date": "2026-05-01", "value": 4.0}],
            "fed_funds": [{"date": "2026-07-29", "value": 4.0}, {"date": "2026-06-01", "value": 4.1}],
            "cpi": monthly_cpi,
            "unemployment": [{"date": "2026-07-01", "value": 4.1}, {"date": "2026-04-01", "value": 4.0}],
            "yield_curve": [{"date": "2026-07-29", "value": 0.4}, {"date": "2026-05-01", "value": 0.1}],
            "sahm": [{"date": "2026-07-01", "value": 0.2}],
        })

        self.assertGreaterEqual(regime["score"], 0)
        self.assertLessEqual(regime["score"], 100)
        self.assertEqual(regime["coverage"], 1.0)
        self.assertEqual(regime["notice"], NOTICE)
        self.assertNotIn("observations", regime)
        self.assertEqual(regime["risk_free_rates"]["fed_funds"]["annual_percent"], 4.0)
        self.assertEqual(regime["risk_free_rates"]["fed_funds"]["series_id"], "DFF")

    def _five_series(self):
        monthly_cpi = [{"date": f"2026-{month:02d}-01", "value": 310 - month * 0.3} for month in range(1, 15)]
        return {
            "treasury_10y": [{"date": "2026-07-29", "value": 4.2}, {"date": "2026-05-01", "value": 4.0}],
            "fed_funds": [{"date": "2026-07-29", "value": 4.0}, {"date": "2026-06-01", "value": 4.1}],
            "cpi": monthly_cpi,
            "unemployment": [{"date": "2026-07-01", "value": 4.1}, {"date": "2026-04-01", "value": 4.0}],
            "yield_curve": [{"date": "2026-07-29", "value": 0.4}, {"date": "2026-05-01", "value": 0.1}],
            "sahm": [{"date": "2026-07-01", "value": 0.2}],
        }

    def test_vix_publishes_as_its_own_factor_without_moving_the_composite_score(self):
        baseline = derive_regime(self._five_series())
        with_vix = derive_regime({
            **self._five_series(),
            "vix": [{"date": "2026-07-29", "value": 35.0}, {"date": "2026-06-01", "value": 15.0}],
        })
        # VIX is published (visible, computed) but excluded from the weighted composite and
        # from coverage -- adding it must not silently move the score every sector's live
        # modifier reads coverage and weights from downstream.
        self.assertEqual(with_vix["score"], baseline["score"])
        self.assertEqual(with_vix["coverage"], baseline["coverage"])
        self.assertIn("volatility", with_vix["factors"])
        self.assertNotIn("volatility", baseline["factors"])
        self.assertEqual(with_vix["series"]["vix"], "VIXCLS")

    def test_a_spiking_vix_reads_restrictive_and_a_calm_one_reads_supportive(self):
        spiking = derive_regime({"vix": [{"date": "2026-07-29", "value": 35.0},
                                         {"date": "2026-06-01", "value": 15.0}]})
        calm = derive_regime({"vix": [{"date": "2026-07-29", "value": 12.0},
                                      {"date": "2026-06-01", "value": 14.0}]})
        self.assertEqual(spiking["factors"]["volatility"]["label"], "restrictive")
        self.assertEqual(calm["factors"]["volatility"]["label"], "supportive")
        self.assertGreaterEqual(spiking["factors"]["volatility"]["score"], 0)
        self.assertLessEqual(calm["factors"]["volatility"]["score"], 100)

    def test_no_weighted_series_falls_back_to_a_neutral_composite_rather_than_crashing(self):
        # Only vix supplied: none of rates/inflation/labor/yield_curve are present. Not
        # reachable through fetch_regime()'s own >=2-series gate today, but derive_regime()
        # is a public function and must not divide by zero if called directly.
        result = derive_regime({"vix": [{"date": "2026-07-29", "value": 20.0}]})
        self.assertEqual(result["score"], 50.0)
        self.assertEqual(result["label"], "neutral")
        self.assertEqual(result["coverage"], 0)

    @patch("fred.requests.get")
    def test_client_omits_missing_observations_and_hides_key(self, get):
        get.return_value = Mock(status_code=401)
        client = FredClient(api_key="private-key")

        with self.assertRaisesRegex(FredError, r"HTTP 401") as raised:
            client.observations("DGS10", 10)

        self.assertNotIn("private-key", str(raised.exception))
