import os
import sys

PIPELINE_DIR = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, PIPELINE_DIR)

from bias_report import build_bias_report


def test_bias_report_contains_pearson_spearman_and_all_requested_exposures():
    rows = []
    for index in range(8):
        rows.append({
            "ticker": f"T{index}",
            "score": 40 + index * 5,
            "confidence": 0.5 + index * 0.05,
            "market_cap": 1_000_000 * (index + 1),
            "analyst_count": index + 2,
            "score_variants": {"challenger": {"score": 50 + index * 0.5}},
        })
    report = build_bias_report(rows)
    assert set(report["correlations"]) == {
        "log_market_cap", "confidence", "analyst_coverage_count",
    }
    for exposure in report["correlations"].values():
        for path in exposure.values():
            assert set(path) == {"count", "pearson", "spearman"}
