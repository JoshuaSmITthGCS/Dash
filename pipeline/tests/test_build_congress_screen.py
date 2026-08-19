import os
import pytest
import tempfile
from datetime import datetime, timezone
from unittest.mock import Mock

import build_congress_screen as module


def trade(**overrides):
    base = {
        "chamber": "senate", "representative": "Jane Doe", "district": None,
        "symbol": "AAPL", "asset_type": "Stock", "asset_description": "Apple Inc",
        "owner": "Self", "transaction_type": "Purchase", "amount": "$15,001 - $50,000",
        "transaction_date": "2026-06-01", "disclosure_date": "2026-06-20",
        "comment": None, "link": "https://example.com",
    }
    base.update(overrides)
    return base


class TempStore:
    def __enter__(self):
        self.tmp = tempfile.mkdtemp()
        self._orig = module.CONGRESS_DIR
        module.CONGRESS_DIR = os.path.join(self.tmp, "congress")
        return self

    def __exit__(self, *exc):
        module.CONGRESS_DIR = self._orig


def test_parse_amount_bounds_reads_the_range_floor_and_ceiling():
    assert module.parse_amount_bounds("$15,001 - $50,000") == (15001.0, 50000.0)
    assert module.parse_amount_bounds("Over $50,000,000") == (50000000.0, 50000000.0)
    assert module.parse_amount_bounds(None) == (None, None)
    assert module.parse_amount_bounds("") == (None, None)


def test_append_new_trades_dedupes_on_the_disclosure_identity():
    with TempStore():
        first = module.append_new_trades([trade()])
        second = module.append_new_trades([trade()])
        different = module.append_new_trades([trade(symbol="MSFT")])

        assert first == 1
        assert second == 0
        assert different == 1
        assert len(module._read_all()) == 2


def test_classify_flags_a_late_filing_past_the_stock_act_window():
    row = module.classify(
        trade(transaction_date="2026-01-01", disclosure_date="2026-03-01"),
        trade_counts={"Jane Doe": 5}, history_days=200,
    )
    assert "LATE_FILING" in row["flags"]
    assert row["filing_delay_days"] == 59


def test_classify_does_not_flag_a_filing_inside_the_window():
    row = module.classify(
        trade(transaction_date="2026-06-01", disclosure_date="2026-06-20"),
        trade_counts={"Jane Doe": 5}, history_days=200,
    )
    assert "LATE_FILING" not in row["flags"]
    assert row["filing_delay_days"] == 19


def test_classify_flags_options_trades():
    row = module.classify(
        trade(asset_type="Stock Option"), trade_counts={"Jane Doe": 1}, history_days=200,
    )
    assert "OPTIONS_TRADE" in row["flags"]


def test_classify_flags_a_rare_trader_only_once_enough_history_exists():
    gated = module.classify(trade(), trade_counts={"Jane Doe": 1}, history_days=10)
    evaluated = module.classify(trade(), trade_counts={"Jane Doe": 1}, history_days=200)

    assert "RARE_TRADER" not in gated["flags"]
    assert gated["rare_trader_evaluated"] is False
    assert "RARE_TRADER" in evaluated["flags"]
    assert evaluated["rare_trader_evaluated"] is True


def test_classify_does_not_flag_a_frequent_trader_as_rare():
    row = module.classify(trade(), trade_counts={"Jane Doe": 6}, history_days=200)
    assert "RARE_TRADER" not in row["flags"]


def test_classify_flags_concentrated_size_by_the_range_floor():
    big = module.classify(trade(amount="$50,001 - $100,000"), trade_counts={"Jane Doe": 5}, history_days=200)
    small = module.classify(trade(amount="$1,001 - $15,000"), trade_counts={"Jane Doe": 5}, history_days=200)
    assert "CONCENTRATED_SIZE" in big["flags"]
    assert "CONCENTRATED_SIZE" not in small["flags"]


def test_classify_flags_extraordinary_buy_for_a_novel_sub_ceiling_purchase():
    relational = {module._trade_key(trade()): ["NOVEL_TICKER"]}
    row = module.classify(
        trade(), trade_counts={"Jane Doe": 5}, history_days=200, relational=relational,
        market_cap_lookup={"AAPL": 500_000_000},
    )
    assert "EXTRAORDINARY_BUY" in row["flags"]


def test_classify_does_not_flag_extraordinary_buy_above_the_market_cap_ceiling():
    relational = {module._trade_key(trade()): ["NOVEL_TICKER"]}
    row = module.classify(
        trade(), trade_counts={"Jane Doe": 5}, history_days=200, relational=relational,
        market_cap_lookup={"AAPL": 3_000_000_000_000},
    )
    assert "EXTRAORDINARY_BUY" not in row["flags"]


def test_classify_does_not_flag_extraordinary_buy_without_novelty():
    row = module.classify(
        trade(), trade_counts={"Jane Doe": 5}, history_days=200,
        market_cap_lookup={"AAPL": 500_000_000},
    )
    assert "EXTRAORDINARY_BUY" not in row["flags"]


def test_classify_does_not_flag_a_sale_as_extraordinary_buy_even_if_novel_and_small():
    relational = {module._trade_key(trade(transaction_type="Sale")): ["NOVEL_TICKER"]}
    row = module.classify(
        trade(transaction_type="Sale"), trade_counts={"Jane Doe": 5}, history_days=200,
        relational=relational, market_cap_lookup={"AAPL": 500_000_000},
    )
    assert "EXTRAORDINARY_BUY" not in row["flags"]


def test_classify_without_a_market_cap_lookup_never_flags_extraordinary_buy():
    relational = {module._trade_key(trade()): ["NOVEL_TICKER"]}
    row = module.classify(
        trade(), trade_counts={"Jane Doe": 5}, history_days=200, relational=relational,
    )
    assert "EXTRAORDINARY_BUY" not in row["flags"]


def test_cluster_trade_keys_requires_three_distinct_representatives_within_the_window():
    rows = [
        trade(representative="A", transaction_date="2026-06-01"),
        trade(representative="B", transaction_date="2026-06-05"),
        trade(representative="C", transaction_date="2026-06-10"),
    ]
    keys = module.cluster_trade_keys(rows)
    assert len(keys) == 3

    only_two = rows[:2]
    assert module.cluster_trade_keys(only_two) == set()


def test_cluster_trade_keys_excludes_trades_outside_the_window():
    rows = [
        trade(representative="A", transaction_date="2026-06-01"),
        trade(representative="B", transaction_date="2026-06-05"),
        trade(representative="C", transaction_date="2026-07-01"),  # 30 days later
    ]
    keys = module.cluster_trade_keys(rows)
    assert module._trade_key(rows[2]) not in keys


def test_same_sector_repeat_requires_a_known_sector():
    lookup = {"AAPL": "Technology"}
    rows = [trade(symbol="AAPL", transaction_date=f"2026-06-{day:02d}") for day in (1, 5, 10)]
    assert len(module.same_sector_repeat_keys(rows, lookup)) == 3
    assert module.same_sector_repeat_keys(rows, {}) == set()


def test_same_sector_repeat_never_flags_an_unmatched_ticker():
    rows = [trade(symbol="MUNI-BOND", transaction_date=f"2026-06-{day:02d}") for day in (1, 5, 10)]
    assert module.same_sector_repeat_keys(rows, {"AAPL": "Technology"}) == set()


def test_buy_sell_flip_requires_opposite_direction_within_the_window():
    buy = trade(transaction_type="Purchase", transaction_date="2026-06-01")
    sell_soon = trade(transaction_type="Sale (Full)", transaction_date="2026-06-30")
    sell_late = trade(transaction_type="Sale (Full)", transaction_date="2026-09-01")

    flipped = module.buy_sell_flip_keys([buy, sell_soon])
    assert module._trade_key(buy) in flipped
    assert module._trade_key(sell_soon) in flipped

    not_flipped = module.buy_sell_flip_keys([buy, sell_late])
    assert not_flipped == set()


def test_buy_sell_flip_does_not_flag_two_purchases():
    first = trade(transaction_type="Purchase", transaction_date="2026-06-01")
    second = trade(transaction_type="Purchase", transaction_date="2026-06-10")
    assert module.buy_sell_flip_keys([first, second]) == set()


def test_novel_ticker_flags_only_the_earliest_trade_in_that_symbol():
    first = trade(transaction_date="2026-01-01")
    second = trade(transaction_date="2026-06-01")
    keys = module.novel_ticker_keys([second, first])
    assert module._trade_key(first) in keys
    assert module._trade_key(second) not in keys


def test_relational_flags_merge_into_classify_output():
    rows = [
        trade(representative="A", transaction_date="2026-06-01"),
        trade(representative="B", transaction_date="2026-06-05"),
        trade(representative="C", transaction_date="2026-06-10"),
    ]
    relational = module.relational_flags(rows)
    classified = module.classify(rows[0], trade_counts={"A": 1}, history_days=200, relational=relational)
    assert "CLUSTER_TRADE" in classified["flags"]


def test_is_equity_purchase_excludes_options_and_non_stock_assets():
    assert module.is_equity_purchase(trade(asset_type="Stock", transaction_type="Purchase")) is True
    assert module.is_equity_purchase(trade(asset_type="Stock Option", transaction_type="Purchase")) is False
    assert module.is_equity_purchase(trade(asset_type="Municipal Security", transaction_type="Purchase")) is False
    assert module.is_equity_purchase(trade(asset_type="Stock", transaction_type="Sale (Full)")) is False


def test_compute_price_performance_uses_one_call_per_distinct_symbol():
    rows = [
        trade(symbol="AAPL", transaction_date="2026-06-01"),
        trade(symbol="AAPL", transaction_date="2026-06-10"),
    ]
    client = Mock()
    client.price_history.return_value = [
        {"date": "2026-06-01", "close": 100.0},
        {"date": "2026-06-10", "close": 105.0},
        {"date": "2026-07-01", "close": 120.0},
    ]

    performance = module.compute_price_performance(rows, client)

    assert client.price_history.call_count == 1
    first_key, second_key = module._trade_key(rows[0]), module._trade_key(rows[1])
    assert performance[first_key]["price_at_purchase"] == 100.0
    assert performance[first_key]["price_latest"] == 120.0
    assert performance[first_key]["return_since_purchase_pct"] == 20.0
    assert performance[second_key]["price_at_purchase"] == 105.0
    assert performance[second_key]["return_since_purchase_pct"] == round((120 / 105 - 1) * 100, 2)


def test_compute_price_performance_skips_non_equity_and_sale_rows():
    rows = [trade(transaction_type="Sale (Full)"), trade(asset_type="Stock Option")]
    client = Mock()
    performance = module.compute_price_performance(rows, client)
    assert performance == {}
    client.price_history.assert_not_called()


def test_compute_price_performance_tolerates_a_failed_lookup():
    client = Mock()
    client.price_history.side_effect = module.CongressTradesError("rate limited")
    performance = module.compute_price_performance([trade()], client)
    assert performance == {}


def test_compute_price_performance_falls_back_to_yahoo_when_fmp_has_no_client(monkeypatch):
    monkeypatch.setattr("fetch_advisor.yahoo_history", lambda symbol, yf: {
        "dates": ["2026-06-01", "2026-06-10", "2026-07-01"],
        "closes": [100.0, 105.0, 120.0],
    })
    performance = module.compute_price_performance([trade()], client=None, yf=Mock())
    key = module._trade_key(trade())
    assert performance[key]["price_at_purchase"] == 100.0
    assert performance[key]["price_latest"] == 120.0
    assert performance[key]["return_since_purchase_pct"] == 20.0
    assert performance[key]["price_source"] == "yahoo"


def test_compute_price_performance_falls_back_to_yahoo_when_fmp_misses_the_symbol(monkeypatch):
    client = Mock()
    client.price_history.side_effect = module.CongressTradesError("HTTP 402")
    monkeypatch.setattr("fetch_advisor.yahoo_history", lambda symbol, yf: {
        "dates": ["2026-06-01", "2026-07-01"],
        "closes": [50.0, 60.0],
    })
    performance = module.compute_price_performance([trade()], client, yf=Mock())
    key = module._trade_key(trade())
    assert performance[key]["price_source"] == "yahoo"
    assert performance[key]["return_since_purchase_pct"] == 20.0


def test_compute_price_performance_prefers_fmp_over_yahoo_when_both_answer(monkeypatch):
    client = Mock()
    client.price_history.return_value = [
        {"date": "2026-06-01", "close": 100.0}, {"date": "2026-07-01", "close": 110.0}]
    yahoo_calls = []
    monkeypatch.setattr("fetch_advisor.yahoo_history",
                        lambda symbol, yf: yahoo_calls.append(symbol) or {"dates": [], "closes": []})
    performance = module.compute_price_performance([trade()], client, yf=Mock())
    key = module._trade_key(trade())
    assert performance[key]["price_source"] == "fmp"
    assert not yahoo_calls


def test_summary_stats_estimates_filings_and_sums_upper_bound_volume():
    rows = [
        module.classify(trade(representative="A", disclosure_date="2026-06-20", amount="$1,001 - $15,000"),
                        trade_counts={}, history_days=200),
        module.classify(trade(representative="A", disclosure_date="2026-06-20", symbol="MSFT", amount="$15,001 - $50,000"),
                        trade_counts={}, history_days=200),
        module.classify(trade(representative="B", disclosure_date="2026-06-21", symbol="TSLA", amount="$50,001 - $100,000"),
                        trade_counts={}, history_days=200),
    ]
    stats = module.summary_stats(rows)
    assert stats["trades"] == 3
    assert stats["filings_estimated"] == 2  # A's two same-day trades count as one filing
    assert stats["politicians"] == 2
    assert stats["issuers"] == 3
    assert stats["volume_upper"] == 15000 + 50000 + 100000


def test_build_results_excludes_disclosures_outside_the_publish_window(monkeypatch):
    monkeypatch.setattr(module, "PUBLISH_WINDOW_DAYS", 30)
    as_of = datetime(2026, 8, 4, tzinfo=timezone.utc)
    rows = [trade(disclosure_date="2026-08-01"), trade(symbol="OLD", disclosure_date="2025-01-01")]

    results, _ = module.build_results(rows, as_of=as_of)

    assert [row["symbol"] for row in results] == ["AAPL"]


def test_build_results_sorts_most_recently_disclosed_first():
    as_of = datetime(2026, 8, 4, tzinfo=timezone.utc)
    rows = [trade(symbol="OLDER", disclosure_date="2026-07-01"),
           trade(symbol="NEWER", disclosure_date="2026-08-01")]

    results, _ = module.build_results(rows, as_of=as_of)

    assert [row["symbol"] for row in results] == ["NEWER", "OLDER"]


def _fmp_rejecting_every_fetch(status=402):
    """A configured client whose key the provider refuses - the shape of a plan that does
    not cover these endpoints, as opposed to a week in which nobody disclosed a trade."""
    def refuse(*args, **kwargs):
        raise module.CongressTradesError(f"FMP senate-latest request failed with HTTP {status}")

    client = Mock()
    client.senate_latest.side_effect = refuse
    client.house_latest.side_effect = refuse
    client.price_history.side_effect = refuse
    return client


def _mirror_returning(rows, seen=None):
    client = Mock()
    client.senate_latest.return_value = (rows, len(rows) if seen is None else seen)
    client.house_latest.return_value = ([], 0)
    return client


def _mirror_rejecting_every_fetch():
    def refuse(*args, **kwargs):
        raise module.CongressTradesError("senate disclosure dataset request failed (URLError)")

    client = Mock()
    client.senate_latest.side_effect = refuse
    client.house_latest.side_effect = refuse
    return client


def _efd_returning(rows, seen=None):
    client = Mock()
    client.fetch.return_value = (rows, len(rows) if seen is None else seen)
    return client


@pytest.fixture(autouse=True)
def _no_live_efd(monkeypatch):
    """Senate eFD is a live HTTP source; no test may reach it.

    Defaults to "reachable, nothing filed in the window" so every existing assertion about
    which sources failed keeps meaning what it did. A test that wants eFD rows overrides it.
    """
    monkeypatch.setattr(module, "SenateEfdClient", lambda: _efd_returning([]))


def test_senate_efd_carries_the_screen_when_both_mirrors_are_withdrawn(monkeypatch):
    # The production state this source was added for: both stock-watcher buckets answer 403
    # AccessDenied, and FMP's key is not entitled to the Congressional endpoints. Without a
    # source that is not somebody else's mirror, the screen publishes nothing at all.
    saved = {}
    today = datetime.now(timezone.utc).date().isoformat()
    with TempStore():
        monkeypatch.setattr(module, "CongressTradesClient", _fmp_rejecting_every_fetch)
        monkeypatch.setattr(module, "StockWatcherClient", _mirror_rejecting_every_fetch)
        monkeypatch.setattr(module, "SenateEfdClient",
                            lambda: _efd_returning([trade(disclosure_date=today)]))
        monkeypatch.setattr(module, "save_json", lambda name, payload: saved.update(payload))
        monkeypatch.setattr(module, "market_cap_by_ticker", lambda: {})
        monkeypatch.setattr("fetch_advisor.yahoo_history", lambda symbol, yf: {"dates": [], "closes": []})
        payload = module.run()

    assert payload["results"]
    assert payload["collection"]["source_counts"]["senate-efd"] == 1
    assert payload["status"] == "partial"  # the House half really is missing; say so


def test_an_unconfigured_fmp_key_no_longer_aborts_the_run(monkeypatch):
    # The keyless mirrors are a complete source on their own, so a missing or unentitled FMP
    # key must cost the price-performance column, not the entire screen. Yahoo is the real,
    # unmocked fallback here (run() imports the real yfinance), so it must be pinned to "no
    # data" - otherwise this depends on live network and on real AAPL price history existing
    # for the fixture's hardcoded purchase date, which is exactly what made this test flaky.
    saved = {}
    with TempStore():
        monkeypatch.setattr(module, "CongressTradesClient",
                            lambda: (_ for _ in ()).throw(module.CongressTradesError("no key")))
        monkeypatch.setattr(module, "StockWatcherClient",
                            lambda: _mirror_returning([trade(
                                disclosure_date=datetime.now(timezone.utc).date().isoformat())]))
        monkeypatch.setattr(module, "save_json", lambda name, payload: saved.update(payload))
        monkeypatch.setattr(module, "market_cap_by_ticker", lambda: {})
        monkeypatch.setattr("fetch_advisor.yahoo_history", lambda symbol, yf: {"dates": [], "closes": []})
        payload = module.run()

    # The keyless mirror carried the run; only the FMP-only performance column is missing.
    assert payload["status"] == "partial"
    assert payload["reason_code"] == "SOME_SOURCES_UNAVAILABLE"
    assert payload["results"]
    assert "return_since_purchase_pct" not in payload["results"][0]


def test_one_source_failing_still_publishes_what_the_other_returned(monkeypatch):
    saved = {}
    with TempStore():
        monkeypatch.setattr(module, "CongressTradesClient", _fmp_rejecting_every_fetch)
        monkeypatch.setattr(module, "StockWatcherClient",
                            lambda: _mirror_returning([trade(
                                disclosure_date=datetime.now(timezone.utc).date().isoformat())]))
        monkeypatch.setattr(module, "save_json", lambda name, payload: saved.update(payload))
        monkeypatch.setattr(module, "market_cap_by_ticker", lambda: {})
        # Not asserted on here, but left unmocked this run() call still hits the real,
        # unmocked yfinance fallback over live network - pin it so the test stays fast and
        # deterministic regardless of network access or real market data.
        monkeypatch.setattr("fetch_advisor.yahoo_history", lambda symbol, yf: {"dates": [], "closes": []})
        payload = module.run()

    # Running more than one source is only worth it if one failing costs its own coverage
    # and nothing else.
    assert payload["status"] == "partial"
    assert payload["reason_code"] == "SOME_SOURCES_UNAVAILABLE"
    assert payload["results"]
    assert payload["collection"]["source_counts"]["mirror-senate"] == 1


def test_run_that_collects_nothing_because_every_source_refused_is_unavailable(monkeypatch):
    saved = {}
    with TempStore():
        # History already exists, so this is a real feed outage rather than an environment
        # that has never collected anything - and it has to publish, saying so.
        module.append_new_trades([trade(disclosure_date="2020-01-02", transaction_date="2020-01-01")])
        monkeypatch.setattr(module, "CongressTradesClient", _fmp_rejecting_every_fetch)
        monkeypatch.setattr(module, "StockWatcherClient", _mirror_rejecting_every_fetch)
        monkeypatch.setattr(module, "save_json", lambda name, payload: saved.update(payload))
        monkeypatch.setattr(module, "market_cap_by_ticker", lambda: {})
        payload = module.run()

    # Publishing this as "success" is what left the page saying "no disclosures collected
    # yet" - a claim about Congress - when the truth was that every request was rejected.
    assert payload["status"] == "unavailable"
    assert payload["reason_code"] == "CONGRESS_DISCLOSURE_FEED_UNAVAILABLE"
    assert payload["results"] == []
    assert any("402" in failure for failure in payload["collection"]["failures"])
    assert len(payload["collection"]["failures"]) == 4
    assert saved["status"] == "unavailable"


def test_a_run_with_nothing_reachable_and_nothing_stored_publishes_nothing(monkeypatch):
    # An offline or local environment must not overwrite a good published screen with an
    # empty one. Once any history exists, the test above shows an outage does publish.
    with TempStore():
        monkeypatch.setattr(module, "CongressTradesClient", _fmp_rejecting_every_fetch)
        monkeypatch.setattr(module, "StockWatcherClient", _mirror_rejecting_every_fetch)
        monkeypatch.setattr(module, "save_json",
                            lambda name, payload: pytest.fail("must not publish"))
        assert module.run() is None


def test_a_mirror_that_returns_rows_none_of_which_parse_says_so(monkeypatch):
    # Reachable but no longer shaped the way this reads it - a different failure from an
    # unreachable source, and one that would otherwise publish as a quiet Congress.
    saved = {}
    with TempStore():
        monkeypatch.setattr(module, "CongressTradesClient", _fmp_rejecting_every_fetch)
        module.append_new_trades([trade(disclosure_date="2020-01-02", transaction_date="2020-01-01")])
        monkeypatch.setattr(module, "StockWatcherClient", lambda: _mirror_returning([], seen=8_000))
        monkeypatch.setattr(module, "save_json", lambda name, payload: saved.update(payload))
        monkeypatch.setattr(module, "market_cap_by_ticker", lambda: {})
        payload = module.run()

    assert payload["status"] == "unavailable"
    assert any("columns may have changed" in failure
               for failure in payload["collection"]["failures"])


def test_run_with_previously_stored_disclosures_reports_partial_not_degraded(monkeypatch):
    saved = {}
    with TempStore():
        module.append_new_trades([trade(disclosure_date=datetime.now(timezone.utc).date().isoformat())])
        monkeypatch.setattr(module, "CongressTradesClient", _fmp_rejecting_every_fetch)
        monkeypatch.setattr(module, "StockWatcherClient", _mirror_rejecting_every_fetch)
        monkeypatch.setattr(module, "save_json", lambda name, payload: saved.update(payload))
        monkeypatch.setattr(module, "market_cap_by_ticker", lambda: {})
        monkeypatch.setattr("fetch_advisor.yahoo_history", lambda symbol, yf: {"dates": [], "closes": []})
        payload = module.run()

    assert payload["status"] == "partial"
    assert payload["results"]
