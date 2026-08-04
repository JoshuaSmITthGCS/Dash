import os
import tempfile

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


def test_parse_amount_upper_reads_the_range_ceiling():
    assert module.parse_amount_upper("$15,001 - $50,000") == 50000.0
    assert module.parse_amount_upper("Over $50,000,000") == 50000000.0
    assert module.parse_amount_upper(None) is None
    assert module.parse_amount_upper("") is None


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


def test_build_results_excludes_disclosures_outside_the_publish_window(monkeypatch):
    monkeypatch.setattr(module, "PUBLISH_WINDOW_DAYS", 30)
    from datetime import datetime, timezone
    as_of = datetime(2026, 8, 4, tzinfo=timezone.utc)
    rows = [trade(disclosure_date="2026-08-01"), trade(symbol="OLD", disclosure_date="2025-01-01")]

    results, _ = module.build_results(rows, as_of=as_of)

    assert [row["symbol"] for row in results] == ["AAPL"]


def test_build_results_sorts_most_recently_disclosed_first():
    from datetime import datetime, timezone
    as_of = datetime(2026, 8, 4, tzinfo=timezone.utc)
    rows = [trade(symbol="OLDER", disclosure_date="2026-07-01"),
           trade(symbol="NEWER", disclosure_date="2026-08-01")]

    results, _ = module.build_results(rows, as_of=as_of)

    assert [row["symbol"] for row in results] == ["NEWER", "OLDER"]


def test_run_skips_without_configuration(monkeypatch):
    monkeypatch.setattr(module, "CongressTradesClient",
                        lambda: (_ for _ in ()).throw(module.CongressTradesError("no key")))
    assert module.run() is None
