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

    @patch("fred.requests.get")
    def test_client_omits_missing_observations_and_hides_key(self, get):
        get.return_value = Mock(status_code=401)
        client = FredClient(api_key="private-key")

        with self.assertRaisesRegex(FredError, r"HTTP 401") as raised:
            client.observations("DGS10", 10)

        self.assertNotIn("private-key", str(raised.exception))
