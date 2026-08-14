import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import build_research_evidence as evidence


def test_primary_ic_target_is_projected_into_the_ui_contract(monkeypatch):
    def load(name, from_config=False):
        if from_config:
            return {"validation": {"primary_horizon": "3M",
                                   "horizons_sessions": {"3M": 63}}}
        if name == "advisor.json":
            return {"generated_at": "2026-08-14T00:00:00+00:00", "run_manifest": {}}
        if name == os.path.join("validation", "ic_validation.json"):
            return {"primary_horizon": "3M",
                    "primary_target": "sector_residual_return_over_trading_sessions",
                    "variants": {"champion": {"3M": {"periods_accumulated": 0,
                                                        "minimum_periods": 24}}}}
        return None

    monkeypatch.setattr(evidence, "load_json", load)
    monkeypatch.setattr(evidence, "_read", lambda _name: None)
    target = evidence.build_report()["headline"]["forecast_target"]
    assert target["definition"] == "sector_residual_return_over_trading_sessions"
    assert target["primary_horizon_sessions"] == 63
