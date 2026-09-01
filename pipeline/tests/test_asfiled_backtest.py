"""Point-in-time purity of the as-filed statement path (Round 5, Task 1).

The visibility rule under test: a fact exists on a date only if its filing date is on or
before that date, and for one (concept, period) the latest visible filing wins. A later
amendment must never rewrite what an earlier date could see.
"""
import edgar_enrichment
from edgar_enrichment import _annual_facts_as_of


def _fake_shard(rows_by_cik):
    def loader(shard):
        return rows_by_cik
    return loader


def test_unfiled_fact_is_invisible(monkeypatch):
    rows = {"0000000001": [
        ("revenue", "2020-12-31", "2021-02-15", 365, 100.0, "USD"),
        ("revenue", "2021-12-31", "2022-02-15", 365, 120.0, "USD"),
    ]}
    monkeypatch.setattr(edgar_enrichment, "_shard_rows", _fake_shard(rows))
    facts = _annual_facts_as_of("0000000001", "2021-06-30")
    assert facts == {("revenue", "2020-12-31"): 100.0}
    facts = _annual_facts_as_of("0000000001", "2022-02-15")
    assert facts[("revenue", "2021-12-31")] == 120.0


def test_amendment_visible_only_from_its_own_filing_date(monkeypatch):
    rows = {"0000000001": [
        ("revenue", "2020-12-31", "2021-02-15", 365, 100.0, "USD"),
        ("revenue", "2020-12-31", "2021-09-01", 365, 90.0, "USD"),  # 10-K/A restates downward
    ]}
    monkeypatch.setattr(edgar_enrichment, "_shard_rows", _fake_shard(rows))
    before_amendment = _annual_facts_as_of("0000000001", "2021-06-30")
    after_amendment = _annual_facts_as_of("0000000001", "2021-09-01")
    assert before_amendment[("revenue", "2020-12-31")] == 100.0
    assert after_amendment[("revenue", "2020-12-31")] == 90.0


def test_quarterly_flow_facts_excluded_from_annual_series(monkeypatch):
    rows = {"0000000001": [
        ("revenue", "2021-03-31", "2021-05-01", 90, 30.0, "USD"),
        ("revenue", "2021-12-31", "2022-02-15", 365, 120.0, "USD"),
    ]}
    monkeypatch.setattr(edgar_enrichment, "_shard_rows", _fake_shard(rows))
    facts = _annual_facts_as_of("0000000001", "2022-06-30")
    assert ("revenue", "2021-03-31") not in facts
    assert facts[("revenue", "2021-12-31")] == 120.0


def test_balance_facts_visible_regardless_of_period_days(monkeypatch):
    rows = {"0000000001": [
        ("assets", "2021-12-31", "2022-02-15", None, 500.0, "USD"),
    ]}
    monkeypatch.setattr(edgar_enrichment, "_shard_rows", _fake_shard(rows))
    facts = _annual_facts_as_of("0000000001", "2022-06-30")
    assert facts[("assets", "2021-12-31")] == 500.0


def test_tag_union_preserves_legacy_history():
    """A filer that switched revenue tags in 2018 must keep its pre-2018 history.

    Round 5 found observations_for_concept returned on the first tag with rows, which
    discarded every legacy-tagged period and produced 1% as-filed revenue coverage in
    2011 against 94% in 2026.
    """
    from edgar_facts import observations_for_concept

    def entry(end, filed, val):
        return {"form": "10-K", "filed": filed, "end": end, "val": val,
                "start": f"{int(end[:4])-1}-12-31", "fy": int(end[:4]), "fp": "FY"}

    companyfacts = {"facts": {"us-gaap": {
        "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": [
            entry("2019-12-31", "2020-02-15", 500)]}},
        "Revenues": {"units": {"USD": [
            entry("2015-12-31", "2016-02-15", 300),
            entry("2019-12-31", "2020-02-15", 500)]}},
    }}}
    observations, tag = observations_for_concept(companyfacts, "revenue")
    ends = sorted({row["period_end"] for row in observations})
    assert ends == ["2015-12-31", "2019-12-31"]
    assert tag == "RevenueFromContractWithCustomerExcludingAssessedTax"
    values = {row["period_end"]: row["value"] for row in observations}
    assert values["2015-12-31"] == 300


def test_ttm_uses_only_visible_quarters(monkeypatch):
    """TTM = FY + YTD_current - YTD_prior, and a 10-Q filed after as_of never enters."""
    rows = {"0000000001": [
        ("revenue", "2021-12-31", "2022-02-15", 365, 100.0, "USD"),   # FY2021, filed Feb 2022
        ("revenue", "2022-06-30", "2022-08-01", 181, 30.0, "USD"),    # H1-2022 YTD, filed Aug
        ("revenue", "2021-06-30", "2021-08-01", 181, 25.0, "USD"),    # H1-2021 YTD
        ("revenue", "2022-09-30", "2022-11-01", 273, 50.0, "USD"),    # 9M-2022, filed Nov (late)
        ("assets", "2022-06-30", "2022-08-01", None, 900.0, "USD"),
        ("assets", "2021-12-31", "2022-02-15", None, 800.0, "USD"),
    ]}
    monkeypatch.setattr(edgar_enrichment, "_shard_rows", _fake_shard(rows))
    ttm, balance = edgar_enrichment._ttm_facts_as_of("0000000001", "2022-09-15")
    # On Sep 15 the 9M filing (Nov) is invisible: TTM = 100 + 30 - 25 = 105.
    assert ttm["revenue"] == 105.0
    assert balance["assets"] == 900.0
    ttm_later, _ = edgar_enrichment._ttm_facts_as_of("0000000001", "2022-11-02")
    # After the 9M filing: no prior-9M exists, so the builder falls back to the H1 pair
    # rather than discarding the quarterly information: TTM = 100 + 30 - 25 = 105.
    assert ttm_later["revenue"] == 105.0


def test_ttm_without_any_quarters_reproduces_annual(monkeypatch):
    rows = {"0000000001": [
        ("revenue", "2021-12-31", "2022-02-15", 365, 100.0, "USD"),
    ]}
    monkeypatch.setattr(edgar_enrichment, "_shard_rows", _fake_shard(rows))
    ttm, _ = edgar_enrichment._ttm_facts_as_of("0000000001", "2022-06-30")
    assert ttm["revenue"] == 100.0
