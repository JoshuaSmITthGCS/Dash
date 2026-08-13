"""Survivorship round: the PIT visibility rules hold for dead-cohort CIKs exactly as
for survivors, because ingest_dead_cohort.py writes through the identical store and
read path. This test proves the property end to end: rows written via ShardedStore for
a deregistered CIK obey filed-date visibility and amendment ordering when read back
through edgar_enrichment._annual_facts_as_of.
"""
import edgar_enrichment
from edgar_enrichment import _annual_facts_as_of
from pit_fundamentals_store import ShardedStore, shard_for


def test_dead_cik_rows_respect_visibility(tmp_path, monkeypatch):
    dead_cik = "0001234567"
    store = ShardedStore(str(tmp_path))
    store.write([
        {"cik": dead_cik, "concept": "revenue", "unit": "USD",
         "period_start": "2020-01-01", "period_end": "2020-12-31",
         "filed": "2021-02-20", "value": 500.0, "accession": "a1",
         "form": "10-K", "fiscal_year": 2020, "fiscal_period": "FY"},
        # The issuer's final 10-K/A, filed shortly before deregistration, restates down.
        {"cik": dead_cik, "concept": "revenue", "unit": "USD",
         "period_start": "2020-01-01", "period_end": "2020-12-31",
         "filed": "2021-11-05", "value": 450.0, "accession": "a2",
         "form": "10-K/A", "fiscal_year": 2020, "fiscal_period": "FY"},
    ])
    monkeypatch.setattr(edgar_enrichment, "FUNDAMENTALS_DIR", str(tmp_path))
    edgar_enrichment._shard_rows.cache_clear()

    before_amendment = _annual_facts_as_of(dead_cik, "2021-06-30")
    after_amendment = _annual_facts_as_of(dead_cik, "2021-12-31")
    after_death = _annual_facts_as_of(dead_cik, "2026-01-01")
    edgar_enrichment._shard_rows.cache_clear()

    assert before_amendment[("revenue", "2020-12-31")] == 500.0
    assert after_amendment[("revenue", "2020-12-31")] == 450.0
    # Facts never disappear after deregistration: the last visible state persists.
    assert after_death[("revenue", "2020-12-31")] == 450.0
    # And nothing is visible before the first filing.
    monkeypatch.setattr(edgar_enrichment, "FUNDAMENTALS_DIR", str(tmp_path))
    nothing_yet = _annual_facts_as_of(dead_cik, "2021-01-01")
    edgar_enrichment._shard_rows.cache_clear()
    assert nothing_yet == {}
