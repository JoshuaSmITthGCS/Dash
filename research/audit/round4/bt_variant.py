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
elif variant == "cross_sectional":
    # Refit the challenger normalizer on each month's own prepared universe, then route
    # every valuation_score call through cross-sectional mode. rank_week is re-implemented
    # with the same body plus the per-month fit.
    import backtest_historical as bh
    from scorer import CrossSectionalNormalizer

    _orig_valuation_score = scorer.valuation_score
    _state = {"nz": None}

    def _patched_valuation_score(snap, **kwargs):
        return _orig_valuation_score(snap, mode="cross_sectional", normalizer=_state["nz"])

    def _cs_rank_week(universe_data, benchmark_closes_to_date, as_of, report_lag_days,
                      allow_current_shares=True, allow_empty_fundamentals=False):
        prepared = {}
        for symbol, ticker_data in universe_data.items():
            built = bh.build_snapshot(ticker_data, as_of, report_lag_days,
                                      allow_current_shares, allow_empty_fundamentals)
            if built is None:
                continue
            prepared[symbol] = built
        _state["nz"] = CrossSectionalNormalizer([snap for snap, _, _ in prepared.values()])
        prelim = []
        for symbol, (snap, _, _) in prepared.items():
            _, parts = _patched_valuation_score(snap)
            prelim.append({"ticker": symbol, "sector": snap.get("sector"),
                           "categories": parts.get("categories", {})})
        percentiles = bh.sector_percentiles(prelim)
        rows = []
        for symbol, (snap, closes_to_date, volumes_to_date) in prepared.items():
            row = advisor_engine.build_research(
                symbol, snap, closes_to_date, benchmark_closes_to_date, [],
                volumes=volumes_to_date, extended=snap,
                sector_percentile=percentiles.get(symbol), macro_regime=None)
            row["action"] = (row.get("recommendation") or {}).get("action")
            rows.append(row)
        rows.sort(key=lambda r: (-r["score"], r["ticker"]))
        return rows

    scorer.valuation_score = _patched_valuation_score
    advisor_engine.valuation_score = _patched_valuation_score
    bh.valuation_score = _patched_valuation_score
    bh.rank_week = _cs_rank_week
else:
    raise SystemExit(f"unknown variant {variant}")

import backtest_monthly  # noqa: E402

sys.argv = ["backtest_monthly.py", "--cache-only", "--years", "5", "--out", out]
backtest_monthly.main()
