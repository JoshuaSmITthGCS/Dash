"""Fail CI when scoring weights are written as UI literals.

Methodology and glossary scoring definitions must describe the same published snapshot
that produced the scores. A literal component or category weight in either source can
silently drift, so this check permits labels and prose but rejects numeric weight copy.
"""

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FILES = (ROOT / "src/pages/Methodology.jsx", ROOT / "src/pages/Glossary.jsx")
COMPONENTS = (
    "fundamentals", "market behaviour", "market behavior", "news sentiment",
    "valuation", "profitability", "financial health", "accounting quality",
    "growth", "capital allocation",
)
WEIGHT_LITERAL = re.compile(
    rf"(?:\d+(?:\.\d+)?\s*%\s*(?:{'|'.join(COMPONENTS)})|"
    rf"(?:{'|'.join(COMPONENTS)})\s*(?:[·:=]|is|at)?\s*\d+(?:\.\d+)?\s*%|"
    r"\b\d+(?:\.\d+)?/\d+(?:\.\d+)?/\d+(?:\.\d+)?\b)",
    re.IGNORECASE,
)


def main():
    failures = []
    for path in FILES:
        for line_number, line in enumerate(path.read_text().splitlines(), 1):
            if WEIGHT_LITERAL.search(line):
                failures.append(f"{path.relative_to(ROOT)}:{line_number}: {line.strip()}")
    if failures:
        raise SystemExit("Hardcoded UI scoring weight detected:\n" + "\n".join(failures))
    print("UI scoring weights are snapshot-driven")


if __name__ == "__main__":
    main()
