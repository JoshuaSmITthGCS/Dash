"""Currency-unit safety in the EDGAR enrichment fallback (round-12 valuation audit).

A 20-F filer (or a domestic filer's foreign-segment footnote) can tag an EDGAR company-facts
concept in its own reporting currency rather than USD. edgar_enrichment merges whatever Yahoo
left missing into `derive_extended`'s USD-denominated `enterprise_value = market_cap(USD) +
debt - cash` and every multiple built on it. Confirmed live: Birkenstock Holding plc (BIRK)'s
entire EDGAR company-facts history is tagged EUR, not USD. Without a unit filter, any BIRK
metric Yahoo left None would be silently backfilled with a raw EUR figure sitting next to a
USD market cap -- wrong by roughly the EUR/USD rate, with nothing anywhere flagging it.
"""
import os
import sys
import unittest

PIPELINE_DIR = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, PIPELINE_DIR)

import edgar_enrichment
from edgar_enrichment import _annual_facts_as_of, _unit_acceptable


def _fake_shard(rows_by_cik):
    def loader(shard):
        return rows_by_cik
    return loader


class UnitAcceptableTests(unittest.TestCase):
    def test_monetary_concept_requires_usd(self):
        self.assertTrue(_unit_acceptable("revenue", "USD"))
        self.assertFalse(_unit_acceptable("revenue", "EUR"))
        self.assertFalse(_unit_acceptable("cash", "TWD"))
        self.assertFalse(_unit_acceptable("cash", None))

    def test_share_count_concept_requires_shares(self):
        self.assertTrue(_unit_acceptable("shares_diluted", "shares"))
        self.assertFalse(_unit_acceptable("shares_diluted", "USD"))


def test_non_usd_revenue_is_excluded_not_merged(monkeypatch):
    rows = {"0001977102": [  # BIRK's real CIK
        ("revenue", "2025-09-30", "2025-11-15", 365, 1239706000.0, "EUR"),
        ("assets", "2025-09-30", "2025-11-15", None, 4942120000.0, "EUR"),
    ]}
    monkeypatch.setattr(edgar_enrichment, "_shard_rows", _fake_shard(rows))
    facts = _annual_facts_as_of("0001977102", "2026-01-01")
    assert facts == {}


def test_usd_facts_still_pass_through(monkeypatch):
    rows = {"0000000001": [
        ("revenue", "2024-12-31", "2025-02-15", 365, 500.0, "USD"),
        ("assets", "2024-12-31", "2025-02-15", None, 900.0, "USD"),
    ]}
    monkeypatch.setattr(edgar_enrichment, "_shard_rows", _fake_shard(rows))
    facts = _annual_facts_as_of("0000000001", "2025-06-01")
    assert facts[("revenue", "2024-12-31")] == 500.0
    assert facts[("assets", "2024-12-31")] == 900.0


def test_mixed_currency_statement_only_keeps_the_usd_facts(monkeypatch):
    """A filer that tags most concepts in USD but one footnote fact in another currency must
    not have that one fact silently treated as USD -- it should simply be missing.
    """
    rows = {"0000000002": [
        ("revenue", "2024-12-31", "2025-02-15", 365, 1000.0, "USD"),
        ("cash", "2024-12-31", "2025-02-15", None, 50.0, "GBP"),
    ]}
    monkeypatch.setattr(edgar_enrichment, "_shard_rows", _fake_shard(rows))
    facts = _annual_facts_as_of("0000000002", "2025-06-01")
    assert facts.get(("revenue", "2024-12-31")) == 1000.0
    assert ("cash", "2024-12-31") not in facts


if __name__ == "__main__":
    unittest.main()
