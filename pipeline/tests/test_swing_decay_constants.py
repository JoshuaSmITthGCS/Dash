"""The McLean-Pontiff decay constants, guarded as a contract rather than a comment.

McLean & Pontiff (Journal of Finance 2016) measure 97 published predictors and report returns
26% lower out of sample and 58% lower after publication, with decay worst in
high-idiosyncratic-risk, low-liquidity names. Those two numbers appear in the published screen
file, in the UI, and in the methodology document. A drift in any one of them is a silent change
to how every effect size on the page should be read, so they are pinned here and the whole
repository is swept for a competing figure.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import swing_signals

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_the_two_constants_are_twenty_six_and_fifty_eight_percent():
    assert swing_signals.DECAY_HAIRCUT["out_of_sample"] == .26
    assert swing_signals.DECAY_HAIRCUT["post_publication"] == .58
    assert swing_signals.DECAY_HAIRCUT["source"] == "McLean & Pontiff, Journal of Finance 2016"


def test_the_note_records_where_decay_is_worst():
    """The conditional result matters as much as the headline: decay concentrates in exactly
    the high-idiosyncratic-risk, low-liquidity names where the paper alpha is largest."""
    note = swing_signals.DECAY_HAIRCUT["note"]

    assert "high-idiosyncratic-risk" in note
    assert "low-liquidity" in note


def test_every_leg_takes_the_post_publication_haircut():
    """All five legs rest on published results, so none of them escapes the larger figure.

    Enumerated rather than implied, so a leg added later fails this test instead of quietly
    inheriting no haircut at all.
    """
    assert swing_signals.DECAY_HAIRCUT["all_legs_are_published"] is True
    assert set(swing_signals.DECAY_HAIRCUT["applies_to_legs"]) == set(swing_signals.SWING_WEIGHTS)


def test_every_registered_variant_is_covered_by_the_haircut():
    for variant in swing_signals.SWING_VARIANTS:
        legs = set(swing_signals.variant_weights(variant))
        assert legs <= set(swing_signals.DECAY_HAIRCUT["applies_to_legs"]), variant


# Files that legitimately carry other percentages next to the words "McLean" or "Pontiff" do
# not exist today. If one ever does, add it here with a reason rather than loosening the sweep.
SWEEP_EXTENSIONS = (".py", ".md", ".jsx", ".js")
SWEEP_ROOTS = ("pipeline", "src", "docs", "research", "scripts")
SKIP_DIRECTORIES = {"node_modules", ".git", "__pycache__", "data"}
DECAY_CLAIM = re.compile(
    r"(?i)(mclean|pontiff)[^\n]{0,400}?(\d{1,3})\s?%\s?(lower|decay|decline|haircut)")


def _sweep_files():
    for root_name in SWEEP_ROOTS:
        root = os.path.join(REPO, root_name)
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [name for name in dirnames if name not in SKIP_DIRECTORIES]
            for name in filenames:
                if name.endswith(SWEEP_EXTENSIONS):
                    yield os.path.join(dirpath, name)


def test_no_file_in_the_repository_quotes_a_competing_decay_figure():
    """A second set of decay numbers anywhere is a reader being told two different things."""
    offenders = []
    for path in _sweep_files():
        try:
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
        except (OSError, UnicodeDecodeError):
            continue
        for match in DECAY_CLAIM.finditer(text):
            if match.group(2) not in {"26", "58"}:
                offenders.append(f"{os.path.relpath(path, REPO)}: {match.group(0)[:120]}")
    assert not offenders, ("decay figures other than 26% out-of-sample and 58% "
                           f"post-publication: {offenders}")
