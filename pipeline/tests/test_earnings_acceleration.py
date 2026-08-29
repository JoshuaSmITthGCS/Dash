"""Earnings/revenue acceleration (the second derivative) off the EDGAR PIT store.

Mirrors test_edgar_sue.py's fixture style: point edgar_sue's internals at an in-memory fact
list instead of the sharded store on disk, so nothing here touches disk or the network.
"""

import os
import sys
from datetime import date, timedelta

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import earnings_acceleration
import edgar_sue


def fact(concept, start, end, filed, value, form="10-Q"):
    return {"cik": "0000000001", "concept": concept, "period_start": start, "period_end": end,
            "filed": filed, "value": value, "form": form}


def quarterly_facts(values, concept="net_income", first_year=2022):
    """One fact per calendar quarter, filed 35 days after each period closes."""
    rows, quarters = [], [("01-01", "03-31"), ("04-01", "06-30"), ("07-01", "09-30"),
                          ("10-01", "12-31")]
    for index, value in enumerate(values):
        year = first_year + index // 4
        start, end = quarters[index % 4]
        period_end = f"{year}-{end}"
        filed = (date.fromisoformat(period_end) + timedelta(days=35)).isoformat()
        rows.append(fact(concept, f"{year}-{start}", period_end, filed, value))
    return rows


@pytest.fixture
def store(monkeypatch):
    """Point edgar_sue's internals at an in-memory fact list instead of the sharded store."""
    def install(rows):
        by_cik = {}
        for row in rows:
            periods = by_cik.setdefault(row["cik"], {})
            key = (row["period_start"], row["period_end"])
            prior = periods.get(key)
            if row["concept"] == concept_filter[0] and (prior is None or row["filed"] < prior[0]):
                periods[key] = (row["filed"], float(row["value"]), row["form"])
        return by_cik

    concept_filter = [None]

    def fake_shard_periods(shard, concept):
        concept_filter[0] = concept
        return install(fake_shard_periods.rows)

    fake_shard_periods.rows = []
    monkeypatch.setattr(edgar_sue, "_shard_periods", fake_shard_periods)
    monkeypatch.setattr(edgar_sue, "shard_for", lambda cik: "shard-00")
    monkeypatch.setattr(edgar_sue, "_ticker_to_cik", lambda: {"AAA": "0000000001"})
    return fake_shard_periods


# A perfectly steady seasonal step: every d_t is identical, so the second derivative is
# exactly zero *and*, just as importantly, the firm's history of seasonal differences has no
# variance to standardize against at all.
def steady_series(count, step=10, base=100):
    return [base + (index // 4) * step for index in range(count)]


# The same small, repeating wobble test_edgar_sue.py's own fixtures use, so the seasonal
# differences have a genuine, nonzero scale to standardize against instead of the degenerate
# zero-variance case steady_series produces.
WOBBLE = (0, 3, -2, 1, -1, 2, -3, 1)


def wobbly_series(count, step=10, base=100):
    return [base + (index // 4) * step + WOBBLE[index % len(WOBBLE)] for index in range(count)]


def test_steady_growth_has_no_scale_to_standardize_against_and_scores_nothing(store):
    """Dividing by a zero scale would manufacture the largest reading in the cross-section --
    the same refusal edgar_sue.sue_for makes for the identical reason, applied here to the
    scale of the second derivative rather than the first."""
    store.rows = quarterly_facts(steady_series(24))

    assert earnings_acceleration.acceleration_for("AAA", "2028-12-31") is None


def test_a_step_up_in_growth_is_standardized_by_the_firms_own_history(store):
    # Wobbly growth for six years, then the single most recent quarter jumps well beyond its
    # own wobble pattern -- a genuine acceleration on top of real, nonzero history variance.
    values = wobbly_series(24)
    values[-1] += 200
    store.rows = quarterly_facts(values)

    result = earnings_acceleration.acceleration_for("AAA", "2028-12-31")

    assert result is not None
    assert result["scale"] > 0
    assert result["raw_acceleration"] > 0
    # Self-consistency: the published, standardized figure must equal what it claims to be
    # built from, not some other, undocumented number.
    assert result["acceleration"] == pytest.approx(result["raw_acceleration"] / result["scale"])


def test_a_larger_jump_produces_a_larger_standardized_reading(store):
    """Directional sanity, independent of the exact scale: holding the firm's own history
    fixed, a bigger final-quarter jump must read as more acceleration, not less."""
    small_bump = wobbly_series(24)
    small_bump[-1] += 50
    store.rows = quarterly_facts(small_bump)
    small = earnings_acceleration.acceleration_for("AAA", "2028-12-31")

    large_bump = wobbly_series(24)
    large_bump[-1] += 500
    store.rows = quarterly_facts(large_bump)
    large = earnings_acceleration.acceleration_for("AAA", "2028-12-31")

    assert small is not None and large is not None
    # Both series share the same history window (the wobble pattern is identical everywhere
    # but the final quarter), so their scales match and the comparison isolates the jump.
    assert small["scale"] == pytest.approx(large["scale"])
    assert large["acceleration"] > small["acceleration"]


def test_the_scale_excludes_the_two_most_recent_seasonal_differences(store):
    """If the scale were estimated from history that includes the two differences being
    standardized, a large final jump would inflate its own denominator. Built here as: a
    perfectly steady history (zero variance on its own) plus one large final-quarter jump --
    if the jump had leaked into the scale estimate there would be a nonzero variance to
    standardize against; since it must be excluded, this still correctly refuses to score."""
    values = steady_series(24)
    values[-1] += 500
    store.rows = quarterly_facts(values)

    assert earnings_acceleration.acceleration_for("AAA", "2028-12-31") is None


def test_insufficient_history_to_estimate_a_scale_returns_none(store):
    # Six quarters is enough for exactly one seasonal difference (needs a quarter ~1 year
    # prior) and not the two consecutive ones acceleration needs, let alone the four more of
    # history the scale estimate additionally requires.
    store.rows = quarterly_facts(wobbly_series(6))

    assert earnings_acceleration.acceleration_for("AAA", "2023-06-30") is None


def test_unknown_ticker_returns_none(store):
    store.rows = quarterly_facts(wobbly_series(24))

    assert earnings_acceleration.acceleration_for("ZZZ", "2028-12-31") is None


def test_a_skipped_quarter_between_the_two_differences_is_refused_not_silently_spanned(store):
    """If the quarter feeding d_{t-1} never resolves, the two surviving seasonal differences
    are not consecutive fiscal quarters -- comparing them anyway would silently span the gap
    and fabricate an acceleration reading. The function must refuse instead."""
    facts = quarterly_facts(wobbly_series(24))
    # Drop the second-to-last quarter's fact entirely. Its own seasonal difference can no
    # longer be computed, so the two differences that remain most recent -- the quarter
    # before it and the quarter after it -- are two fiscal quarters apart, not one.
    target_period_end = facts[-2]["period_end"]
    store.rows = [row for row in facts if row["period_end"] != target_period_end]

    assert earnings_acceleration.acceleration_for("AAA", "2028-12-31") is None


def test_acceleration_is_dated_by_the_later_filing_of_its_two_seasonal_differences(store):
    values = wobbly_series(24)
    values[-1] += 200
    facts = quarterly_facts(values)
    store.rows = facts

    result = earnings_acceleration.acceleration_for("AAA", "2028-12-31")

    assert result is not None
    latest_fact = next(row for row in facts if row["period_end"] == result["period_end"])
    assert result["filed"] >= latest_fact["filed"]


def test_as_of_never_sees_a_quarter_filed_after_it(store):
    # A later quarter exists in the store but is filed after the as_of cutoff; the result
    # must be built only from what was knowable on that date, matching quarterly_series' own
    # as_of filter.
    facts = quarterly_facts(wobbly_series(24))
    cutoff = facts[-2]["filed"]  # as_of lands after the third-to-last fact's filing
    store.rows = facts

    result = earnings_acceleration.acceleration_for("AAA", cutoff)

    assert result is not None
    assert all(row["filed"] <= cutoff for row in facts if row["period_end"] == result["period_end"])
    assert result["filed"] <= cutoff


def test_revenue_concept_is_read_independently_of_net_income(store):
    net_income_values = wobbly_series(24)
    net_income_values[-1] += 200
    revenue_values = wobbly_series(24, step=50, base=1000)
    revenue_values[-1] += 900
    store.rows = (quarterly_facts(net_income_values, concept="net_income")
                 + quarterly_facts(revenue_values, concept="revenue"))

    earnings = earnings_acceleration.acceleration_for("AAA", "2028-12-31", concept="net_income")
    revenue = earnings_acceleration.acceleration_for("AAA", "2028-12-31", concept="revenue")

    assert earnings is not None and revenue is not None
    assert earnings["concept"] == "net_income"
    assert revenue["concept"] == "revenue"
    # Independently computed series (different base/step/jump), so their raw figures must
    # differ even though both resolve to a real, standardized number.
    assert earnings["raw_acceleration"] != revenue["raw_acceleration"]
