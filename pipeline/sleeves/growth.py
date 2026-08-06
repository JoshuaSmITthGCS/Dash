"""Growth sleeve (docs/RESEARCH-CONTRACT.md, brief section 6.7).

Wraps scorer.py's existing "growth" fundamental category (revenue growth, earnings growth,
FCF growth, operating-margin trend, earnings surprise). The brief also asks for growth
acceleration, growth persistence, and return on incremental invested capital -- none of
those are computed anywhere in this codebase today, so they are correctly absent from
raw_features rather than approximated.
"""

from sleeves._fundamentals import score_fundamentals_family_sleeve

VERSION = "1.0.0"
TARGET_HORIZON_DAYS = 252


def score_growth_sleeve(snapshot, as_of=None):
    return score_fundamentals_family_sleeve(
        "growth", "growth", ("growth",), VERSION, TARGET_HORIZON_DAYS, snapshot, as_of,
    )
