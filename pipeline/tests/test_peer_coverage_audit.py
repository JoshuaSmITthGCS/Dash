"""Peer-group coverage: measuring a gap that must not be patched away.

Phase 1 set MINIMUM_VALID_PEERS to 30 after the published dataset claimed THG was cheaper than
85% of P&C insurers on the strength of 14. The gate is right, and the grouping underneath it
strands the companies the registry classifies most precisely. The temptation is to widen an
undersized profile group to its sector, which restores a claim and makes it wrong. These tests
hold the audit to reporting the gap rather than closing it.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "research"))

from audit_peer_coverage import coverage  # noqa: E402


def rows(count, sector, profile_hint=None):
    out = []
    for index in range(count):
        row = {"ticker": f"{sector[:2].upper()}{index}", "sector": sector}
        if profile_hint:
            row.update(profile_hint)
        out.append(row)
    return out


def test_a_broad_sector_group_can_publish():
    report = coverage(rows(40, "Technology"))
    assert report["groups_that_can_publish"] == 1
    assert report["companies_permanently_unrankable"] == 0


def test_a_group_below_the_minimum_is_reported_with_the_shortfall():
    report = coverage(rows(6, "Technology"))
    assert report["groups_that_cannot"] == 1
    assert report["unreachable"][0]["members"] == 6
    assert report["unreachable"][0]["short_by"] == 24


def test_the_stranded_companies_are_counted_not_reassigned():
    """The audit must never quietly widen a group to make the number look better."""
    report = coverage(rows(6, "Technology") + rows(40, "Industrials"))
    assert report["companies_permanently_unrankable"] == 6
    assert report["groups_that_can_publish"] == 1
    assert report["groups_that_cannot"] == 1


def test_the_note_records_why_the_obvious_fix_is_refused():
    report = coverage(rows(6, "Technology"))
    assert "universal-multiple error" in report["note"]
    assert "regression tests reject" in report["note"]


def test_an_empty_universe_does_not_divide_by_zero():
    report = coverage([])
    assert report["companies_permanently_unrankable"] == 0
    assert report["share_permanently_unrankable"] is None
