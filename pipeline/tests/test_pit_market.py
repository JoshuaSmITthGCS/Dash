"""Price series and universe membership, tested against what the series actually contains.

The cache holds two series and neither is a traded price level. ``closes`` is adjusted for
splits and dividends; ``raw_closes`` is adjusted for splits and not dividends. Two mistakes
follow from misreading that, and both are guarded here: applying a level threshold to a
split-adjusted price, and treating a return as contaminated when it is not.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pit_market import (PriceHistory, last_filing_dates, load_universe_prices,  # noqa: E402
                        rebalance_dates, universe_as_of)


def history(ticker="TEST", *, sessions=400, price=50.0, volume=1_000_000.0):
    """A flat series of ``sessions`` sessions running from the start of 2018."""
    dates = [f"{2018 + index // 250}-{1 + (index // 21) % 12:02d}-{1 + index % 21:02d}"
             for index in range(sessions)]
    return PriceHistory(ticker, dates, [price] * sessions, [price] * sessions,
                        [volume] * sessions)


# ------------------------------------------------------------------- reading only the past

def test_nothing_after_the_as_of_date_is_readable():
    prices = PriceHistory("T", ["2020-01-01", "2020-02-01", "2020-03-01"],
                          [10.0, 20.0, 30.0], [10.0, 20.0, 30.0])
    assert prices.price("2020-02-15") == 20.0
    assert prices.adjusted_price("2020-02-01") == 20.0
    assert prices.price("2019-12-31") is None


def test_a_return_spans_only_the_window_asked_for():
    prices = PriceHistory("T", ["2020-01-01", "2020-02-01", "2020-03-01"],
                          [10.0, 20.0, 40.0], [10.0, 20.0, 40.0])
    assert prices.total_return("2020-01-01", "2020-02-01") == pytest.approx(1.0)
    assert prices.total_return("2020-01-01", "2020-03-01") == pytest.approx(3.0)


def test_a_return_across_a_split_is_not_contaminated_by_it():
    """Adjusted closes are safe for returns: the factor cancels out of the ratio.

    A 4:1 split halfway through leaves the adjusted series continuous, so the measured
    return is the return an investor earned, not the price series' discontinuity.
    """
    dates = ["2020-08-28", "2020-08-31", "2020-09-30"]
    adjusted = [100.0, 100.0, 110.0]      # continuous through the split
    split_adjusted = [100.0, 100.0, 110.0]  # already restated to today's basis
    prices = PriceHistory("AAPL", dates, adjusted, split_adjusted)
    assert prices.total_return("2020-08-28", "2020-09-30") == pytest.approx(0.10)


# --------------------------------------------------------------- the level/return distinction

def test_dollar_volume_is_split_proof_without_correction():
    """A split divides the price and multiplies the volume, so the product is unchanged."""
    dates = ["2020-08-27", "2020-08-28", "2020-08-31", "2020-09-01"]
    pre, post = 400.0, 100.0
    prices = PriceHistory("AAPL", dates, [pre, pre, post, post],
                          [pre, pre, post, post], [1e6, 1e6, 4e6, 4e6])
    # Sessions on both sides of the split trade the same dollars; the median is that figure.
    assert prices.dollar_volume("2020-09-01", sessions=4) == pytest.approx(4e8)


def test_a_price_floor_is_off_by_default():
    """Levels here are split-adjusted to today, so a floor excludes the wrong names.

    Apple's 2016 close reads $27 in this cache against roughly $108 as it traded. A $50
    floor would read it out of the universe for a split four years in its future.
    """
    prices = {"AAPL": history("AAPL", price=27.0)}
    members, diagnostics = universe_as_of("2019-06-30", prices=prices)
    assert members == ["AAPL"]
    assert diagnostics["excluded"]["below_minimum_price"] == 0
    assert diagnostics["rules"]["minimum_price"] is None
    assert "split-adjusted" in diagnostics["price_level_note"]


def test_a_price_floor_still_applies_when_a_caller_asks_for_one():
    prices = {"AAPL": history("AAPL", price=27.0)}
    members, diagnostics = universe_as_of("2019-06-30", prices=prices, minimum_price=50.0)
    assert members == []
    assert diagnostics["excluded"]["below_minimum_price"] == 1


# ------------------------------------------------------------------- universe reconstruction

def test_illiquidity_is_what_actually_excludes_a_name():
    prices = {"THIN": history("THIN", price=20.0, volume=100.0),
              "LIQUID": history("LIQUID", price=20.0, volume=1_000_000.0)}
    members, diagnostics = universe_as_of("2019-06-30", prices=prices)
    assert members == ["LIQUID"]
    assert diagnostics["excluded"]["below_minimum_dollar_volume"] == 1


def test_a_company_without_enough_history_is_not_a_member():
    prices = {"NEW": history("NEW", sessions=100)}
    members, diagnostics = universe_as_of("2019-06-30", prices=prices)
    assert members == []
    assert diagnostics["excluded"]["insufficient_history"] == 1


def test_a_filer_gone_silent_leaves_the_universe():
    prices = {"GONE": history("GONE"), "FILING": history("FILING")}
    members, diagnostics = universe_as_of(
        "2019-06-30", prices=prices,
        cik_by_ticker={"GONE": "1", "FILING": "2"},
        last_filings={"1": "2018-01-01", "2": "2019-05-01"})
    assert members == ["FILING"]
    assert diagnostics["excluded"]["filer_gone_silent"] == 1


def test_membership_before_a_company_was_priced_is_empty_not_assumed():
    prices = {"LATER": history("LATER")}
    members, _ = universe_as_of("2010-01-01", prices=prices)
    assert members == []


def test_the_survivorship_residual_is_stated_in_every_result():
    """Reconstruction narrows a survivor-biased candidate set; it does not cure it."""
    _, diagnostics = universe_as_of("2019-06-30", prices={"A": history("A")})
    assert "delisted" in diagnostics["survivorship_note"]
    assert "biased upward" in diagnostics["survivorship_note"]


# ------------------------------------------------------------------------------- plumbing

def test_last_filing_dates_keeps_the_newest_per_company():
    observations = [{"cik": "1", "filed": "2020-01-01"}, {"cik": "1", "filed": "2021-01-01"},
                    {"cik": "2", "filed": "2019-01-01"}, {"cik": "2", "filed": None}]
    assert last_filing_dates(observations) == {"1": "2021-01-01", "2": "2019-01-01"}


def test_rebalance_dates_are_evenly_spaced_and_bounded():
    dates = rebalance_dates("2020-01-01", "2020-03-01", every_days=21)
    assert dates == ["2020-01-01", "2020-01-22", "2020-02-12"]
    assert rebalance_dates("not a date", "2020-01-01") == []


def test_loading_skips_a_ticker_with_no_cached_series(tmp_path):
    with open(tmp_path / "REAL.json", "w", encoding="utf-8") as handle:
        json.dump({"dates": ["2020-01-01"], "closes": [10.0], "raw_closes": [10.0],
                   "volumes": [1.0]}, handle)
    with open(tmp_path / "EMPTY.json", "w", encoding="utf-8") as handle:
        json.dump({"dates": [], "closes": []}, handle)
    loaded = load_universe_prices(["REAL", "EMPTY", "ABSENT"], str(tmp_path))
    assert set(loaded) == {"REAL"}


def test_a_cache_without_raw_closes_falls_back_rather_than_failing(tmp_path):
    with open(tmp_path / "OLD.json", "w", encoding="utf-8") as handle:
        json.dump({"dates": ["2020-01-01"], "closes": [10.0]}, handle)
    loaded = PriceHistory.load("OLD", str(tmp_path))
    assert loaded.price("2020-01-01") == 10.0
