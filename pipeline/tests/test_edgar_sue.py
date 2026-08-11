"""Standardized unexpected earnings off the EDGAR point-in-time store.

Three properties matter here and nothing else in the swing screen checks them:

* the surprise is the *most recent* standardized seasonal difference, not an average of
  several quarters of percent surprise (the construct the field it replaces carried),
* a quarter nobody tags discretely - Q4 above all - is recovered by differencing the
  year-to-date chain rather than silently leaving a hole in the seasonal series, and
* the announcement date is the date the number was *first* filed, because that is when the
  market learned it; a restatement two years later does not reopen a drift window.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import edgar_sue


def fact(concept, start, end, filed, value, form="10-Q"):
    return {"cik": "0000000001", "concept": concept, "period_start": start, "period_end": end,
            "filed": filed, "value": value, "form": form}


def quarterly_facts(values, concept="net_income", first_year=2022):
    """One fact per calendar quarter, filed 35 days after each period closes."""
    from datetime import date, timedelta

    rows, quarters = [], [("01-01", "03-31"), ("04-01", "06-30"), ("07-01", "09-30"),
                          ("10-01", "12-31")]
    for index, value in enumerate(values):
        year = first_year + index // 4
        start, end = quarters[index % 4]
        period_end = f"{year}-{end}"
        filed = (date.fromisoformat(period_end) + timedelta(days=35)).isoformat()
        rows.append(fact(concept, f"{year}-{start}", period_end, filed, value))
    return rows


# A seasonal series with a steady step and a small repeating wobble, so the eight prior
# seasonal differences have a scale to standardize against. A perfectly constant step has
# none, and the module correctly refuses to score it - see the zero-scale test below.
WOBBLE = (0, 3, -2, 1, -1, 2, -3, 1)


def seasonal_series(count, step=10, base=100):
    return [base + (index // 4) * step + WOBBLE[index % len(WOBBLE)] for index in range(count)]


@pytest.fixture
def store(monkeypatch):
    """Point the module at an in-memory fact list instead of the sharded store on disk."""
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


def test_sue_measures_the_latest_seasonal_surprise_against_the_firms_own_history(store):
    # Thirteen years of a steady seasonal step, then one quarter that breaks far above it.
    values = seasonal_series(52)
    values[-1] += 50
    store.rows = quarterly_facts(values)

    result = edgar_sue.sue_for("AAA", "2035-12-31")

    assert result["basis"] == "net_income"
    assert result["history_quarters"] == edgar_sue.SUE_TARGET_HISTORY
    # A 50-unit break in a series whose seasonal differences wobble by ~3 is a large surprise.
    assert result["sue"] > 5


def test_a_quiet_quarter_is_not_a_surprise(store):
    store.rows = quarterly_facts(seasonal_series(52))

    result = edgar_sue.sue_for("AAA", "2035-12-31")

    assert abs(result["sue"]) < 1


def test_a_firm_whose_seasonal_differences_never_move_scores_nothing(store):
    """Dividing by a zero scale would manufacture the largest surprise in the cross-section."""
    store.rows = quarterly_facts([100] * 52)

    assert edgar_sue.sue_for("AAA", "2035-12-31") is None


def test_untagged_quarters_are_recovered_by_differencing_the_year_to_date_chain(store):
    """Filers report Q4 only inside the fiscal year, so a naive read loses one season in four."""
    rows = []
    for year in (2024, 2025):
        rows.append(fact("net_income", f"{year}-01-01", f"{year}-03-31", f"{year}-05-05", 100))
        rows.append(fact("net_income", f"{year}-01-01", f"{year}-06-30", f"{year}-08-05", 210))
        rows.append(fact("net_income", f"{year}-01-01", f"{year}-09-30", f"{year}-11-05", 330))
        rows.append(fact("net_income", f"{year}-01-01", f"{year}-12-31", f"{year + 1}-02-20",
                         460, form="10-K"))
    store.rows = rows

    series = edgar_sue.quarterly_series("0000000001", "net_income", "2026-12-31")
    by_end = {row["period_end"]: row for row in series}

    assert by_end["2025-06-30"]["value"] == 110    # 210 year-to-date less a 100 first quarter
    assert by_end["2025-09-30"]["value"] == 120
    assert by_end["2025-12-31"]["value"] == 130    # the quarter nobody tags
    assert by_end["2025-12-31"]["derived"] is True
    assert by_end["2025-03-31"]["derived"] is False
    # A derived quarter is dated by the later of its two components: both had to be public.
    assert by_end["2025-12-31"]["filed"] == "2026-02-20"


def test_a_quarter_is_dated_by_its_first_filing_not_its_restatement(store):
    """The market reacted to the number as announced. A restatement does not reopen a window."""
    store.rows = quarterly_facts(seasonal_series(52)) + [
        fact("net_income", "2034-10-01", "2034-12-31", "2036-06-30", 999, form="10-K/A")]

    series = edgar_sue.quarterly_series("0000000001", "net_income", "2036-12-31")
    restated = next(row for row in series if row["period_end"] == "2034-12-31")

    assert restated["filed"] == "2035-02-04"
    assert restated["value"] == seasonal_series(52)[48 + 3]


def test_nothing_filed_after_the_as_of_date_is_visible(store):
    store.rows = quarterly_facts(seasonal_series(52))

    everything = edgar_sue.quarterly_series("0000000001", "net_income", "2035-12-31")
    truncated = edgar_sue.quarterly_series("0000000001", "net_income", "2030-01-01")

    assert len(truncated) < len(everything)
    assert all(row["filed"] <= "2030-01-01" for row in truncated)


def test_too_little_history_scores_nothing_rather_than_guessing_a_scale(store):
    store.rows = quarterly_facts([100, 110, 120, 130, 140, 150])

    assert edgar_sue.sue_for("AAA", "2035-12-31") is None


def test_eps_is_only_a_fallback_because_as_filed_eps_is_not_split_adjusted(store):
    """A split makes x_t and x_{t-4} incomparable, so net income answers first."""
    store.rows = (quarterly_facts(seasonal_series(52))
                  + quarterly_facts([1.0] * 52, concept="eps_diluted"))

    assert edgar_sue.sue_for("AAA", "2035-12-31")["basis"] == "net_income"

    store.rows = quarterly_facts(seasonal_series(52, step=2, base=5), concept="eps_diluted")
    assert edgar_sue.sue_for("AAA", "2035-12-31")["basis"] == "eps_diluted"


def test_an_unknown_ticker_resolves_to_nothing(store):
    store.rows = quarterly_facts(seasonal_series(52))

    assert edgar_sue.sue_for("NOTLISTED", "2035-12-31") is None


def test_window_age_is_counted_on_the_names_own_trading_calendar():
    sessions = ["2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06", "2026-08-07"]

    assert edgar_sue.announcement_age_trading_days("2026-08-04", sessions) == 3
    assert edgar_sue.announcement_age_trading_days("2026-08-07", sessions) == 0
    # A filing the cached calendar has not reached yet is not negative-aged.
    assert edgar_sue.announcement_age_trading_days("2026-09-01", sessions) == 0
    assert edgar_sue.announcement_age_trading_days(None, sessions) is None
