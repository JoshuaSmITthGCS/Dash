"""Standardized unexpected earnings off the EDGAR point-in-time store.

Five properties matter here and nothing else in the swing screen checks them:

* the surprise is the *most recent* standardized seasonal difference, not an average of
  several quarters of percent surprise (the construct the field it replaces carried),
* the expectation model is the seasonal random walk **with drift**, so a firm growing
  earnings steadily does not register a surprise every quarter,
* a quarter nobody tags discretely - Q4 above all - is recovered by differencing the
  year-to-date chain rather than silently leaving a hole in the seasonal series,
* the fundamental is dated by the *first* filing of the number, because a restatement two
  years later does not reopen a drift window, and
* the drift window is anchored on the earnings *release* datetime from Form 8-K Item 2.02,
  never on the periodic filing date, and a period with no release resolves to nothing.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import collect_earnings_releases
import earnings_release
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
    # A release the cached calendar has not reached yet is not negative-aged.
    assert edgar_sue.announcement_age_trading_days("2026-09-01", sessions) == 0
    assert edgar_sue.announcement_age_trading_days(None, sessions) is None


def test_window_age_reads_a_full_release_timestamp_by_its_calendar_date():
    """The anchor is a datetime now. A 16:05 Eastern release still ages from that session."""
    sessions = ["2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06", "2026-08-07"]

    assert edgar_sue.announcement_age_trading_days("2026-08-04T16:05:00-04:00", sessions) == 3


# ---------------------------------------------------------------------------
# The expectation model (spec amendment SA-2026-08-12-03)
# ---------------------------------------------------------------------------

def test_the_expectation_model_is_the_seasonal_random_walk_with_drift(store):
    """SUE = (d_t - delta) / sd(history), delta estimated from the firm's own history.

    Foster (The Accounting Review 1977); Foster, Olsen & Shevlin (The Accounting Review
    1984). The drift term is published on the row so the with-drift form is verifiable from
    the output rather than asserted in a comment, and the arithmetic is reproduced here from
    the same inputs.
    """
    values = seasonal_series(52)
    store.rows = quarterly_facts(values)

    result = edgar_sue.sue_for("AAA", "2035-12-31")

    assert result["expectation_model"] == "seasonal_random_walk_with_drift"
    differences = [values[index] - values[index - 4] for index in range(4, len(values))]
    history = differences[-(edgar_sue.SUE_TARGET_HISTORY + 1):-1]
    expected_drift = sum(history) / len(history)
    assert result["drift"] == pytest.approx(expected_drift)
    assert result["seasonal_difference"] == pytest.approx(differences[-1])
    assert result["sue"] == pytest.approx(
        (differences[-1] - result["drift"]) / result["scale"])


def test_a_steady_earnings_trend_is_not_a_surprise_every_quarter(store):
    """The failure mode dropping the drift term would create.

    A firm growing earnings by the same amount every year has a large positive seasonal
    difference in every single quarter. Without the drift term that reads as a large positive
    surprise every quarter, which is a growth signal wearing a surprise's name and would put
    steady compounders permanently at the top of a 30%-weight leg. With the drift term it is
    what it actually is: the firm doing exactly what it always does.
    """
    # Growth of 40 a year, with a small wobble so the standard deviation is not zero.
    values = [100 + (index // 4) * 40 + WOBBLE[index % len(WOBBLE)] for index in range(52)]
    store.rows = quarterly_facts(values)

    scores = []
    for as_of in ("2033-12-31", "2034-06-30", "2034-12-31", "2035-06-30", "2035-12-31"):
        result = edgar_sue.sue_for("AAA", as_of)
        if result:
            scores.append(result["sue"])

    assert len(scores) >= 4
    # Every quarter's seasonal difference is around +40, and the drift term is around +40 too.
    assert all(abs(score) < 2 for score in scores), scores
    # And the trend itself is what the drift term absorbed, not something left in the surprise.
    assert edgar_sue.sue_for("AAA", "2035-12-31")["drift"] == pytest.approx(40, abs=3)


def test_a_bare_year_over_year_difference_would_have_flagged_the_same_firm(store):
    """The counterfactual, so the test above is measuring the drift term and not luck."""
    values = [100 + (index // 4) * 40 + WOBBLE[index % len(WOBBLE)] for index in range(52)]
    store.rows = quarterly_facts(values)

    result = edgar_sue.sue_for("AAA", "2035-12-31")
    without_drift = result["seasonal_difference"] / result["scale"]

    assert without_drift > 10        # a bare difference calls this a huge surprise
    assert abs(result["sue"]) < 2    # the with-drift construct does not


# ---------------------------------------------------------------------------
# The release anchor (spec amendment SA-2026-08-12-02)
# ---------------------------------------------------------------------------

def test_a_period_with_no_release_datetime_is_marked_unresolved(store, tmp_path):
    store.rows = quarterly_facts(seasonal_series(52))
    empty = tmp_path / "earnings_releases.jsonl"
    empty.write_text("", encoding="utf-8")
    earnings_release.reset_cache()

    result = edgar_sue.sue_for("AAA", "2035-12-31", releases_path=str(empty))

    assert result["release_datetime"] is None
    assert result["anchor_status"] == edgar_sue.RELEASE_UNRESOLVED_STATUS
    # The filing date survives as provenance and is never promoted into the anchor.
    assert result["filed"]
    assert result["announcement_anchor"] == "earnings_release_datetime_8k_item_202"


def test_a_resolved_release_anchors_the_window_earlier_than_the_filing(store, tmp_path):
    """The whole point of the amendment: the release precedes the periodic filing."""
    store.rows = quarterly_facts(seasonal_series(52))
    releases = tmp_path / "earnings_releases.jsonl"
    releases.write_text(json.dumps({
        "cik": "0000000001", "release_datetime": "2035-01-20T16:05:00-05:00",
        "period_end": None, "accession": "0000000001-35-000001", "form": "8-K",
        "items": "2.02", "source": "earnings_release_datetime_8k_item_202",
    }) + "\n", encoding="utf-8")
    earnings_release.reset_cache()

    result = edgar_sue.sue_for("AAA", "2035-12-31", releases_path=str(releases))

    assert result["anchor_status"] == "RELEASE_DATE_RESOLVED"
    assert result["release_date"] == "2035-01-20"
    # 2034-12-31 quarter: released 2035-01-20, filed 2035-02-04. Fifteen days of drift the
    # filing-date anchor used to discard.
    assert result["release_date"] < result["filed"]


def test_a_release_after_the_as_of_date_is_invisible(store, tmp_path):
    """Point-in-time discipline: a rerun of an old date cannot see a future announcement."""
    store.rows = quarterly_facts(seasonal_series(52))
    releases = tmp_path / "earnings_releases.jsonl"
    releases.write_text(json.dumps({
        "cik": "0000000001", "release_datetime": "2035-01-20T16:05:00-05:00",
        "period_end": None, "accession": "0000000001-35-000001", "form": "8-K",
        "items": "2.02",
    }) + "\n", encoding="utf-8")
    earnings_release.reset_cache()

    assert earnings_release.release_for_period("0000000001", "2034-12-31", "2035-01-19",
                                               path=str(releases)) is None
    assert earnings_release.release_for_period("0000000001", "2034-12-31", "2035-01-20",
                                               path=str(releases))


def test_a_release_naming_a_different_period_never_dates_this_one(tmp_path):
    releases = tmp_path / "earnings_releases.jsonl"
    releases.write_text(json.dumps({
        "cik": "0000000001", "release_datetime": "2035-01-20T16:05:00-05:00",
        "period_end": "2034-09-30", "accession": "A", "form": "8-K", "items": "2.02",
    }) + "\n", encoding="utf-8")
    earnings_release.reset_cache()

    assert earnings_release.release_for_period("0000000001", "2034-12-31", "2035-12-31",
                                               path=str(releases)) is None
    assert earnings_release.release_for_period("0000000001", "2034-09-30", "2035-12-31",
                                               path=str(releases))


def test_a_release_far_past_the_period_end_is_reporting_something_else(tmp_path):
    releases = tmp_path / "earnings_releases.jsonl"
    releases.write_text(json.dumps({
        "cik": "0000000001", "release_datetime": "2035-09-20T16:05:00-05:00",
        "period_end": None, "accession": "A", "form": "8-K", "items": "2.02",
    }) + "\n", encoding="utf-8")
    earnings_release.reset_cache()

    # 263 days past the period end, well outside the lag band.
    assert earnings_release.release_for_period("0000000001", "2034-12-31", "2035-12-31",
                                               path=str(releases)) is None


def test_a_naive_acceptance_timestamp_is_read_as_eastern_not_utc():
    """A 16:05 after-close release read as UTC would move to the morning of the same session."""
    parsed = earnings_release.parse_release_datetime("2036-01-20T16:05:00")

    assert parsed.utcoffset().total_seconds() == -5 * 3600
    assert earnings_release.release_date("2036-01-20T16:05:00") == "2036-01-20"


def test_the_collector_only_takes_the_results_of_operations_item():
    assert collect_earnings_releases.has_results_item("2.02,9.01") is True
    assert collect_earnings_releases.has_results_item("2.02") is True
    assert collect_earnings_releases.has_results_item("1.03,5.02") is False
    assert collect_earnings_releases.has_results_item(None) is False


def test_the_collector_prefers_the_acceptance_timestamp_over_the_event_date():
    submissions = {"filings": {"recent": {
        "accessionNumber": ["0000000001-36-000001", "0000000001-36-000002"],
        "form": ["8-K", "8-K"],
        "items": ["2.02,9.01", "5.02"],
        "filingDate": ["2036-01-20", "2036-02-01"],
        "reportDate": ["2036-01-20", "2036-02-01"],
        "acceptanceDateTime": ["2036-01-20T16:05:31.000Z", ""],
    }}}

    records = collect_earnings_releases.release_records("0000000001", submissions)

    assert len(records) == 1
    assert records[0]["precision"] == "acceptance_timestamp"
    assert records[0]["release_datetime"].startswith("2036-01-20T16:05:31")
    # The period end is left None rather than guessed from the event date.
    assert records[0]["period_end"] is None
