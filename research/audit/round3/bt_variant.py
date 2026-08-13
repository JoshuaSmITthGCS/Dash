"""Run backtest_monthly with a component variant patched in, offline from cache.

Usage: bt_variant.py <variant> <out.json>
Variants:
  fundamentals_only   RANKING_WEIGHTS = fundamentals 1.0, modifiers disabled
  no_modifiers        production weights, modifiers disabled
  growth_zeroed       production weights, fundamentals growth category weight = 0
"""
import sys
import os

HERE = "/Users/eyerise/Documents/GitHub/Dash/pipeline"
sys.path.insert(0, HERE)

variant, out = sys.argv[1], sys.argv[2]

import advisor_engine  # noqa: E402
import scorer  # noqa: E402

if variant == "fundamentals_only":
    advisor_engine.RANKING_WEIGHTS = {"fundamentals": 1.0}
    advisor_engine.apply_modifiers = lambda base, *a, **k: (round(base, 1), {"applied": {}, "total": 0.0})
elif variant == "no_modifiers":
    advisor_engine.apply_modifiers = lambda base, *a, **k: (round(base, 1), {"applied": {}, "total": 0.0})
elif variant == "growth_zeroed":
    scorer.SETTINGS["fundamentals"]["category_weights"]["growth"] = 0.0
else:
    raise SystemExit(f"unknown variant {variant}")

import backtest_monthly  # noqa: E402

sys.argv = ["backtest_monthly.py", "--cache-only", "--years", "5", "--out", out]
backtest_monthly.main()
