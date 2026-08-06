"""Quality sleeve (docs/RESEARCH-CONTRACT.md, brief section 6.2).

Wraps scorer.py's "profitability", "financial_health", "capital_allocation", and
"accounting_quality" fundamental categories -- kept separate from the value sleeve so
ValueSignal can distinguish cheap-and-high-quality from cheap-and-low-quality, per the
brief. Quality-family metric membership comes from pipeline/config/feature_registry.json.
"""

from sleeves._fundamentals import score_fundamentals_family_sleeve

VERSION = "1.0.0"
TARGET_HORIZON_DAYS = 126


def score_quality_sleeve(snapshot, as_of=None):
    return score_fundamentals_family_sleeve(
        "quality", "quality",
        ("profitability", "financial_health", "capital_allocation", "accounting_quality"),
        VERSION, TARGET_HORIZON_DAYS, snapshot, as_of,
    )
