"""Fail the build when a document claims validation this repository cannot support.

The current state of the swing model, stated plainly:

  * it has no out-of-sample record of any kind,
  * its prospective clock starts 2026-09-01 and has not started,
  * every effect size it quotes is a published gross figure, before costs and before decay.

An artifact that says otherwise is a bug, not a wording choice. Documentation drifts toward
confidence on its own: a caveat gets trimmed for length, a hedge gets dropped in a summary, and
three edits later the page asserts a backtest nobody ran. The only reliable defence is a check
that runs in CI and fails.

What this checks. Every generated report, README and published artifact is scanned for
assertions of a class this repository cannot back: confirmed replication, survival of a
data-snooping correction, matching published returns, or a validated out-of-sample record. A
match fails the build unless a registered result file exists that supports it.

    python pipeline/validate_documentation_claims.py
    python pipeline/validate_documentation_claims.py --list-scanned

Exit code 1 means a document is claiming more than the evidence carries. The fix is to correct
the document, or to register the result that supports it. Loosening the pattern is not a fix.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
FREEZE_PATH = os.path.join(HERE, "validation", "harness_freeze.json")
RESULTS_DIR = os.path.join(HERE, "validation", "results")

# Where generated documentation and published artifacts live.
SCANNED_PATHS = (
    "README.md",
    "MIGRATION.md",
    "APP-COMPLETE-BREAKDOWN.md",
    "docs",
    "public/data/screens",
    "pipeline/validation",
)
SCANNED_EXTENSIONS = (".md", ".json", ".txt")
SKIP_DIRECTORIES = {"node_modules", ".git", "__pycache__"}

# Claims this repository cannot support without a registered result file behind them. Each
# entry is (claim id, pattern, what would have to exist for the claim to be true).
CLAIM_PATTERNS = (
    ("CONFIRMED_REPLICATION",
     r"(?i)\b(?:successfully\s+)?(?:replicat(?:ed|es|ion)\s+(?:is\s+)?confirmed"
     r"|confirmed\s+(?:the\s+)?replication"
     r"|we\s+replicated\s+the\s+published)",
     "a registered replication result comparing this implementation against the published "
     "sample"),
    ("SURVIVED_DATA_SNOOPING",
     r"(?i)\bsurviv\w*\s+(?:the\s+)?(?:data[- ]snooping|multiple[- ]testing|snooping)"
     r"\s*(?:correction|adjustment|bias)?",
     "a registered result carrying a deflated Sharpe ratio at the enumerated trial count and "
     "a t statistic above the Harvey-Liu-Zhu hurdle"),
    ("MATCHED_PUBLISHED_RETURNS",
     r"(?i)\b(?:match(?:es|ed)|reproduc(?:es|ed)|deliver(?:s|ed))\s+"
     r"(?:the\s+)?published\s+(?:returns?|effect|spread|alpha)",
     "a registered result comparing realized returns against the published figures"),
    ("VALIDATED_OUT_OF_SAMPLE",
     r"(?i)\b(?:validated|verified|confirmed|proven)\s+out[- ]of[- ]sample\b",
     "at least one completed period on the prospective clock, which starts 2026-09-01"),
    ("BACKTEST_PROVES",
     r"(?i)\bbacktest\w*\s+(?:prov(?:es|en)|confirm(?:s|ed)|validat(?:es|ed))\b",
     "a registered backtest result file"),
    ("HAS_A_TRACK_RECORD",
     r"(?i)\b(?:has|carries)\s+(?:a\s+)?(?:proven|established|verified)\s+track\s+record",
     "a completed prospective record"),
)

# A line that is quoting the claim in order to deny it is not making the claim. These are the
# denial markers checked in the matched line and the two lines around it.
NEGATION_MARKERS = (
    "no ", "not ", "never", "cannot", "can not", "has yet", "not yet", "without",
    "unless", "fails", "does not", "must not", "would be a bug", "is a bug",
    "claiming otherwise", "rather than", "nobody", "none of",
)


def registered_results(path=RESULTS_DIR):
    """Result files a claim can point at, and which claims each one supports.

    A result file declares what it backs, in a ``supports_claims`` list naming claim ids from
    CLAIM_PATTERNS. Support is per claim rather than per file: one registered replication
    result does not license a sentence about surviving a data-snooping correction, and a
    blanket "some results exist" check would let it.

    None exist yet, which is the correct state today.
    """
    if not os.path.isdir(path):
        return {}
    supported = {}
    for name in sorted(os.listdir(path)):
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(path, name), encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, json.JSONDecodeError):
            continue
        for claim in payload.get("supports_claims") or []:
            supported.setdefault(claim, []).append(name)
    return supported


def _scanned_files(repo=REPO, paths=SCANNED_PATHS):
    for entry in paths:
        target = os.path.join(repo, entry)
        if os.path.isfile(target):
            yield target
            continue
        for dirpath, dirnames, filenames in os.walk(target):
            dirnames[:] = [name for name in dirnames if name not in SKIP_DIRECTORIES]
            for name in sorted(filenames):
                if name.endswith(SCANNED_EXTENSIONS):
                    yield os.path.join(dirpath, name)


def _is_denial(lines, index):
    """Whether the matched text is quoting the claim in order to refuse it."""
    window = " ".join(lines[max(0, index - 2):index + 3]).lower()
    return any(marker in window for marker in NEGATION_MARKERS)


def scan_text(text, *, source="<text>"):
    """Every unsupported claim in one document, with its line number and what it would need."""
    lines = text.splitlines()
    findings = []
    for index, line in enumerate(lines):
        for claim_id, pattern, requirement in CLAIM_PATTERNS:
            if not re.search(pattern, line):
                continue
            if _is_denial(lines, index):
                continue
            findings.append({
                "source": source,
                "line": index + 1,
                "claim": claim_id,
                "text": line.strip()[:200],
                "would_require": requirement,
            })
    return findings


def scan(repo=REPO, *, paths=SCANNED_PATHS, results_dir=RESULTS_DIR):
    """Scan the repository and report every claim with no registered result behind it."""
    available = registered_results(results_dir)
    findings, scanned = [], []
    for path in _scanned_files(repo, paths):
        relative = os.path.relpath(path, repo)
        scanned.append(relative)
        try:
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
        except (OSError, UnicodeDecodeError):
            continue
        findings.extend(scan_text(text, source=relative))

    unsupported = []
    for finding in findings:
        backing = available.get(finding["claim"])
        if backing:
            finding["supported_by"] = backing
        else:
            unsupported.append(finding)
    return {
        "files_scanned": len(scanned),
        "scanned": scanned,
        "registered_results": available,
        "claims_found": findings,
        "unsupported_claims": unsupported,
        "state_of_the_evidence": {
            "out_of_sample_record": "none",
            "prospective_clock_start": "2026-09-01",
            "prospective_clock_started": False,
            "effect_sizes": "published gross figures, before costs and before decay",
        },
        "ok": not unsupported,
    }


def state_of_the_evidence_text():
    """The disclosure every generated artifact has to carry, in one place.

    Kept here rather than copied into each generator, so there is one wording to correct if the
    state of the evidence ever changes and no chance of one artifact drifting away from the
    others.
    """
    return ("This model has no out-of-sample record. Its prospective clock starts 2026-09-01 "
            "and has not started. Every effect size quoted is a published gross figure, "
            "before costs and before decay.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list-scanned", action="store_true",
                        help="print every file the scan covers and exit")
    parser.add_argument("--json", action="store_true", help="print the full report as JSON")
    args = parser.parse_args(argv)

    report = scan()
    if args.list_scanned:
        print("\n".join(report["scanned"]))
        return 0
    if args.json:
        print(json.dumps(report, indent=2))
        return 0 if report["ok"] else 1

    if report["ok"]:
        print(f"Documentation claims: {report['files_scanned']} files scanned, nothing claims "
              "validation this repository cannot support.")
        return 0

    print("Documentation claims validation this repository cannot support:\n")
    for finding in report["unsupported_claims"]:
        print(f"  {finding['source']}:{finding['line']}  [{finding['claim']}]")
        print(f"    {finding['text']}")
        print(f"    would require: {finding['would_require']}\n")
    print(state_of_the_evidence_text())
    print("\nCorrect the document, or register the result that supports it. Loosening the "
          "pattern is not a fix.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
