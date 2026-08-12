"""rescore_row must stay in lockstep with build_research's champion formula.

Round 5 Task 2 (promoted to champion 2026-08-12) dropped the coverage multiplier from
both stages of the blend. build_research and rescore_row each recompute the same
formula independently - one from a fresh fetch, one from a published row's own stored
fields - and a rescore-only refresh (pipeline/rescore.py) must not silently regress a
row back onto the retired formula.
"""
import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from advisor_engine import build_research
from migrate_advisor_v2 import rescore_row


def _row():
    snap = {"ticker": "TEST", "name": "Test Co", "sector": "Technology", "is_etf": False,
            "peg": 1.1, "forward_pe": 22, "price_to_sales": 5, "return_on_equity": 0.18,
            "free_cash_flow_yield": 0.05, "debt_to_equity": 0.6, "current_ratio": 1.5}
    closes = [100 + index * 0.2 for index in range(300)]
    return build_research("TEST", snap, closes, closes, [])


def test_rescore_row_reproduces_build_research_exactly():
    original = _row()
    rescored = rescore_row(copy.deepcopy(original), peer_context=None)
    assert rescored["rescored"] is not False
    assert rescored["raw_score"] == original["raw_score"]
    assert rescored["base_score"] == original["base_score"]
    assert rescored["components"]["fundamentals"] == original["components"]["fundamentals"]


def test_rescore_row_carries_no_completeness_multiplier():
    original = _row()
    rescored = rescore_row(copy.deepcopy(original), peer_context=None)
    assert rescored["components"]["fundamentals"] == rescored["fundamental_detail"]["raw_score"]
    assert rescored["base_score"] == rescored["raw_score"]
