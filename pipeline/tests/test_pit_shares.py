"""Share counts must reach the price series on the same split basis, or say nothing.

The failure this guards against is silent and four-figure: an as-filed share count times a
split-adjusted price gave Apple a $459bn market cap in July 2020 against the $1.84tn it
carried, and an earnings yield four times too high -- which is enough to put a stock at the
top of every value ranking in the universe. Each test below is a case that actually occurs in
``pipeline/data/pit/fundamentals``.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pit_shares import (canonical_split_ratio, basis_events,  # noqa: E402
                        current_basis_shares, repair_units, shares_as_of,
                        unadjusted_tail_days)


def observation(period_end, filed, value, *, period_start=None, period_type="quarter",
                concept="shares_diluted", available_at=None):
    return {"concept": concept, "period_start": period_start or period_end,
            "period_end": period_end, "period_type": period_type, "filed": filed,
            "available_at": available_at or filed, "value": value}


# --------------------------------------------------------------------------- ratio matching

@pytest.mark.parametrize("ratio, expected", [
    (4.0, 4.0),               # Apple, 2020
    (7.0, 7.0),               # Apple, 2014
    (20.0117, 20.0),          # Amazon, 2022 -- reported precision, not a different split
    (10.0016, 10.0),          # Nvidia, 2024
    (1.5, 1.5),               # Odfl, 3:2
    (0.25, 0.25),             # a 1:4 reverse split
])
def test_recognises_real_splits(ratio, expected):
    assert canonical_split_ratio(ratio) == pytest.approx(expected)


@pytest.mark.parametrize("ratio", [
    1.0,      # nothing happened
    1.08,     # a quarter of buybacks
    1.35,     # a secondary offering: real dilution, not a basis change
    2.6,      # a stock-funded acquisition that is no simple ratio
    1000.0,   # a units mis-tag, which must never be treated as a corporate action
])
def test_refuses_what_is_not_a_split(ratio):
    assert canonical_split_ratio(ratio) is None


# ----------------------------------------------------------------------------- the core fix

def test_apple_2020_split_is_read_off_its_own_restatement():
    """The signal is one period filed twice: 4,354,788,000 then 17,419,154,000."""
    rows = [
        observation("2020-06-27", "2020-07-31", 4_354_788_000, period_start="2020-03-29"),
        observation("2020-06-27", "2021-07-28", 17_419_154_000, period_start="2020-03-29"),
        observation("2019-06-29", "2019-07-31", 4_547_800_000, period_start="2019-03-30"),
    ]
    events = basis_events(rows)
    assert [event["factor"] for event in events] == [4.0]
    assert events[0]["known_from"] == "2021-07-28"

    series, _ = current_basis_shares(rows)
    by_period = {row["period_end"]: row for row in series}
    # The 2019 quarter was last filed before the split, so it needs carrying forward.
    assert by_period["2019-06-29"]["shares"] == pytest.approx(4_547_800_000 * 4)
    # The 2020 quarter's newest vintage is already post-split; multiplying again would be
    # the same error in the other direction.
    assert by_period["2020-06-27"]["shares"] == pytest.approx(17_419_154_000)


def test_consecutive_periods_are_not_used_to_date_a_split():
    """Buybacks between two quarters put their ratio at 3.79 across a 4:1 split.

    No tolerance loose enough to accept 3.79 as a 4:1 is tight enough to reject a secondary
    offering, which is why the comparison is a period against itself.
    """
    assert canonical_split_ratio(3.79) is None


def test_one_split_seen_through_six_periods_is_counted_once():
    rows = []
    for index, period in enumerate(("2019-09-28", "2019-12-28", "2020-03-28", "2020-06-27")):
        rows.append(observation(period, "2020-07-31", 4_000_000_000 + index))
        rows.append(observation(period, "2021-01-27", 16_000_000_004 + index * 4))
    events = basis_events(rows)
    assert len(events) == 1
    assert events[0]["factor"] == pytest.approx(4.0)
    assert len(events[0]["periods"]) == 4


def test_two_splits_compound():
    """Nvidia: 4:1 in 2021 and 10:1 in 2024. A 2019 period is forty times its filed count."""
    rows = [
        observation("2019-04-28", "2019-05-16", 620_000_000),
        observation("2020-04-26", "2020-05-21", 615_000_000),
        observation("2020-04-26", "2021-08-20", 2_460_000_000),
        observation("2023-04-30", "2023-05-26", 2_490_000_000),
        observation("2023-04-30", "2024-08-28", 24_900_000_000),
    ]
    series, events = current_basis_shares(rows)
    assert sorted(event["factor"] for event in events) == [4.0, 10.0]
    by_period = {row["period_end"]: row for row in series}
    assert by_period["2019-04-28"]["basis_factor"] == pytest.approx(40.0)
    assert by_period["2019-04-28"]["shares"] == pytest.approx(620_000_000 * 40)


# -------------------------------------------------------------------- refusing to guess

def test_an_unexplained_restatement_publishes_nothing():
    """A 2.6x change matching no split disqualifies everything filed before it."""
    rows = [
        observation("2018-03-31", "2018-05-01", 100_000_000),
        observation("2019-03-31", "2019-05-01", 100_000_000),
        observation("2019-03-31", "2020-05-01", 260_000_000),
        observation("2020-03-31", "2020-05-01", 260_000_000),
    ]
    series, events = current_basis_shares(rows)
    assert any(event["factor"] is None for event in events)
    by_period = {row["period_end"]: row for row in series}
    assert by_period["2018-03-31"]["shares"] is None
    assert by_period["2018-03-31"]["basis_uncertain"] is True
    # The periods filed after it are still sound; uncertainty does not spread forwards.
    assert by_period["2020-03-31"]["shares"] == pytest.approx(260_000_000)
    assert shares_as_of(series, "2018-06-01") is None


def test_ordinary_share_count_drift_changes_nothing():
    rows = [observation(f"20{year}-03-31", f"20{year}-05-01", 1_000_000_000 - year * 10_000_000)
            for year in range(18, 24)]
    series, events = current_basis_shares(rows)
    assert events == []
    assert all(row["basis_factor"] == 1.0 for row in series)


# ------------------------------------------------------------------------ units mis-tags

def test_a_units_mis_tag_is_repaired_and_never_propagated():
    """CenterPoint reported 402 diluted shares in 2010, meaning 401,993,000.

    Treated as a basis change it would multiply every earlier period by a million. It is a
    per-period tagging error and is repaired as one.
    """
    rows = [observation(f"20{year}-06-30", f"20{year}-08-04", 400_000_000 + year * 1_000_000)
            for year in range(11, 20)]
    rows.append(observation("2010-06-30", "2010-08-04", 402))
    repaired, corrections = repair_units(rows)
    assert [fix["decades"] for fix in corrections] == [-6]
    mis_tagged = next(row for row in repaired if row["period_end"] == "2010-06-30")
    assert mis_tagged["value"] == pytest.approx(402_000_000)

    _, events = current_basis_shares(rows)
    assert all(event.get("factor") != 1e6 for event in events)


def test_units_repair_leaves_a_company_whose_count_genuinely_moved():
    """Alaska Air ran from 36m shares to 123m across a 2:1 split. None of it is a mis-tag."""
    rows = ([observation(f"20{year}-06-30", f"20{year}-08-04", 36_000_000)
             for year in range(10, 13)]
            + [observation(f"20{year}-06-30", f"20{year}-08-04", 123_000_000)
               for year in range(13, 20)])
    _, corrections = repair_units(rows)
    assert corrections == []


# ------------------------------------------------------------------- point-in-time selection

def test_selection_uses_first_disclosure_not_the_restating_filing():
    """A restatement changes what a number is denominated in, not when it was disclosed."""
    rows = [
        observation("2020-06-27", "2020-07-31", 4_354_788_000, available_at="2020-07-31"),
        observation("2020-06-27", "2021-07-28", 17_419_154_000, available_at="2021-07-28"),
        observation("2019-06-29", "2019-07-31", 4_500_000_000, available_at="2019-07-31"),
    ]
    series, _ = current_basis_shares(rows)
    # Readable the day after the original filing, on today's basis.
    assert shares_as_of(series, "2020-08-01") == pytest.approx(17_419_154_000)
    # And not before it, even though a later filing restated the same period.
    assert shares_as_of(series, "2020-07-30") == pytest.approx(4_500_000_000 * 4)


def test_nothing_filed_yet_is_none_not_zero():
    rows = [observation("2020-06-27", "2020-07-31", 4_354_788_000)]
    series, _ = current_basis_shares(rows)
    assert shares_as_of(series, "2019-01-01") is None


def test_the_unadjusted_tail_is_reported_rather_than_corrected():
    """A split newer than every filing is in the price series and in no share count."""
    rows = [observation("2024-03-31", "2024-05-01", 100_000_000)]
    series, _ = current_basis_shares(rows)
    assert unadjusted_tail_days(series, "2024-06-30") == 60
    assert unadjusted_tail_days(series, "2023-01-01") is None
