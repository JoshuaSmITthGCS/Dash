import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from common import load_json

REQUIRED_KEYS = {
    "name", "horizon_trading_days", "ranking", "hard_filters", "risk_controls",
    "sort", "rebalance", "implementation_status", "implemented_in",
}


class ScreenPresetRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = load_json("screen_presets.json", from_config=True)

    def test_all_sixteen_presets_from_the_brief_are_present(self):
        self.assertEqual(len(self.registry["presets"]), 16)

    def test_every_preset_declares_the_full_contract(self):
        for preset_id, preset in self.registry["presets"].items():
            missing = REQUIRED_KEYS - set(preset)
            self.assertFalse(missing, f"{preset_id} missing {missing}")

    def test_every_preset_has_at_least_one_ranking_signal(self):
        for preset_id, preset in self.registry["presets"].items():
            self.assertTrue(preset["ranking"], f"{preset_id} has no ranking signals")

    def test_wired_presets_cite_a_real_implementation(self):
        # A preset cannot claim "wired" without saying exactly where the ranking actually
        # runs -- this is the same honesty discipline as the rest of the upgrade.
        for preset_id, preset in self.registry["presets"].items():
            if preset["implementation_status"] == "wired":
                self.assertIsNotNone(preset["implemented_in"], f"{preset_id} is wired but cites no implementation")

    def test_specification_only_presets_do_not_claim_an_implementation(self):
        for preset_id, preset in self.registry["presets"].items():
            if preset["implementation_status"] == "specification_only":
                self.assertIsNone(preset["implemented_in"], f"{preset_id} is spec-only but cites an implementation")


if __name__ == "__main__":
    unittest.main()
