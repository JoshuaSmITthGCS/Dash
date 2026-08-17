import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import edgar_filing_signals as efs

TODAY = date(2026, 8, 17)


def filing(form, filed, items=""):
    return {"form": form, "filed": filed, "items": items}


class EightKMaterialityTests(unittest.TestCase):
    def test_restatement_scores_negative(self):
        points, detail = efs.score_8k_activity([filing("8-K", "2026-08-10", "4.02")], as_of=TODAY)
        self.assertLess(points, 0)
        self.assertEqual(detail["latest_item"], "4.02")

    def test_routine_earnings_item_scores_zero(self):
        points, detail = efs.score_8k_activity([filing("8-K", "2026-08-10", "2.02")], as_of=TODAY)
        self.assertEqual(points, 0.0)
        self.assertEqual(detail["material_items"], 0)

    def test_no_filings_reports_unavailable(self):
        points, detail = efs.score_8k_activity([], as_of=TODAY)
        self.assertEqual(points, 0.0)
        self.assertFalse(detail["available"])

    def test_worst_item_wins_when_several_cited(self):
        # Bankruptcy (1.03, weight 1.00) outranks a plain agreement termination (1.02, 0.45)
        # cited on the same filing - one event, one (the worst) classification.
        points, detail = efs.score_8k_activity(
            [filing("8-K", "2026-08-10", "1.02,1.03")], as_of=TODAY)
        self.assertEqual(detail["latest_item"], "1.03")
        bankruptcy_only, _ = efs.score_8k_activity(
            [filing("8-K", "2026-08-10", "1.03")], as_of=TODAY)
        self.assertEqual(points, bankruptcy_only)

    def test_only_the_freshest_qualifying_filing_scores(self):
        old = filing("8-K", "2026-01-01", "1.03")
        fresh = filing("8-K", "2026-08-15", "3.02")
        points, detail = efs.score_8k_activity([old, fresh], as_of=TODAY)
        self.assertEqual(detail["latest_item"], "3.02")
        # 3.02 (weight 0.35) is fresh but milder than 1.03's weight 1.00, so the fresher,
        # milder item can score a smaller penalty than an older, worse one would have.
        self.assertGreater(points, -efs.DEFAULTS_8K["max_penalty"])

    def test_signal_decays_with_age(self):
        fresh_points, _ = efs.score_8k_activity([filing("8-K", "2026-08-15", "1.03")], as_of=TODAY)
        old_points, _ = efs.score_8k_activity([filing("8-K", "2026-05-01", "1.03")], as_of=TODAY)
        self.assertLess(fresh_points, old_points)  # more negative = fresher

    def test_stale_beyond_max_age_scores_zero(self):
        points, detail = efs.score_8k_activity([filing("8-K", "2026-01-01", "1.03")], as_of=TODAY)
        self.assertEqual(points, 0.0)
        self.assertEqual(detail["material_items"], 1)


class ProxySignalTests(unittest.TestCase):
    def test_contested_proxy_scores_negative(self):
        points, detail = efs.score_proxy_activity(
            [filing("DEFC14A", "2026-08-01")], as_of=TODAY)
        self.assertLess(points, 0)
        self.assertEqual(detail["contested_filings"], 1)

    def test_soliciting_material_alone_is_not_scored(self):
        points, detail = efs.score_proxy_activity(
            [filing("DEFA14A", "2026-08-01")], as_of=TODAY)
        self.assertEqual(points, 0.0)
        self.assertEqual(detail["soliciting_material_filings"], 1)
        self.assertEqual(detail["contested_filings"], 0)

    def test_routine_annual_proxy_is_not_scored(self):
        points, detail = efs.score_proxy_activity(
            [filing("DEF 14A", "2026-08-01")], as_of=TODAY)
        self.assertEqual(points, 0.0)

    def test_no_filings_reports_unavailable(self):
        points, detail = efs.score_proxy_activity([], as_of=TODAY)
        self.assertFalse(detail["available"])


class FilingIntegrityTests(unittest.TestCase):
    def test_late_10q_notification_scores_negative(self):
        points, detail = efs.score_filing_integrity(
            [filing("10-K", "2026-02-01")], [filing("NT 10-Q", "2026-08-12")], as_of=TODAY)
        self.assertLess(points, 0)
        self.assertEqual(detail["latest_nt_form"], "NT 10-Q")

    def test_on_time_filings_score_nothing(self):
        points, detail = efs.score_filing_integrity(
            [filing("10-K", "2026-02-01")], [filing("10-Q", "2026-07-15")], as_of=TODAY)
        self.assertEqual(points, 0.0)
        self.assertEqual(detail["latest_10k_filed"], "2026-02-01")
        self.assertEqual(detail["latest_10q_filed"], "2026-07-15")

    def test_no_filings_at_all_reports_unavailable(self):
        points, detail = efs.score_filing_integrity([], [], as_of=TODAY)
        self.assertFalse(detail["available"])

    def test_signal_decays_with_age(self):
        fresh_points, _ = efs.score_filing_integrity(
            [], [filing("NT 10-Q", "2026-08-15")], as_of=TODAY)
        old_points, _ = efs.score_filing_integrity(
            [], [filing("NT 10-Q", "2026-05-01")], as_of=TODAY)
        self.assertLess(fresh_points, old_points)


if __name__ == "__main__":
    unittest.main()
