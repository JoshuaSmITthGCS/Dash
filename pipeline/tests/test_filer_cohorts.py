"""Survivorship measurement: parsing SEC quarterly indexes and counting who left.

The point of this module is to replace "biased upward by an amount this pipeline cannot yet
quantify" with a number. These tests hold it to the two things that make such a number
trustworthy: the index parser must not silently drop filings, and attrition must distinguish a
company acquired from a company that failed, because assuming every disappearance was a
wipe-out overcorrects in the opposite direction.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from build_filer_cohorts import cohorts, parse_form_index  # noqa: E402

# The real header and column spacing of an SEC form.idx, which is fixed-width with at least
# two spaces between fields and a form name that itself contains spaces.
INDEX = """Description:           Master Index of EDGAR Dissemination Feed by Form Type
Last Data Received:    March 31, 2018

Form Type   Company Name                     CIK         Date Filed  File Name
----------------------------------------------------------------------------------
10-K        APPLE INC                        320193      2018-02-01  edgar/data/1.txt
10-Q        NVIDIA CORP                      1045810     2018-02-15  edgar/data/2.txt
4           SOME OFFICER                     1234567     2018-02-16  edgar/data/3.txt
25-NSE      GONE CORP                        7654321     2018-03-01  edgar/data/4.txt
S-1 MEF     A NEW ISSUER                     9999999     2018-03-02  edgar/data/5.txt
"""


def test_the_index_parser_reads_every_filing_including_multi_word_forms():
    rows = parse_form_index(INDEX)
    assert len(rows) == 5
    by_cik = {row["cik"]: row for row in rows}
    assert by_cik["0000000320193"[-10:]]["form"] == "10-K"
    assert by_cik["0001045810"]["name"] == "NVIDIA CORP"
    assert by_cik["0007654321"]["form"] == "25-NSE"
    # A form name containing a space must not be mistaken for a form plus a company name.
    assert by_cik["0009999999"]["form"] == "S-1 MEF"


def test_ciks_are_zero_padded_so_they_join_the_rest_of_the_store():
    rows = parse_form_index(INDEX)
    assert all(len(row["cik"]) == 10 for row in rows)
    assert {row["cik"] for row in rows} >= {"0000320193", "0001045810"}


def test_headers_and_rules_are_not_read_as_filings():
    rows = parse_form_index(INDEX)
    assert all(not row["form"].startswith("-") for row in rows)
    assert all(row["name"] not in ("Company Name", "") for row in rows)


def periodic(first, last, name="X", count=4):
    return {"first": first, "last": last, "name": name, "count": count}


def test_a_company_still_filing_is_not_counted_as_departed():
    by_year, departed = cohorts(
        {"0000000001": periodic("2017-02-01", "2026-02-01")}, {}, {"0000000001"})
    assert departed == []
    assert by_year[2017]["filers"] == 1
    assert by_year[2017]["still_filing"] == 1
    assert by_year[2017]["gone"] == 0


def test_a_company_that_stopped_filing_is_counted_in_every_year_it_filed():
    """A 2017 cohort must include companies that left in 2019 -- that is the whole point."""
    by_year, departed = cohorts(
        {"0000000001": periodic("2017-02-01", "2019-05-01"),
         "0000000002": periodic("2017-02-01", "2026-02-01")},
        {}, {"0000000002"})
    assert by_year[2017]["filers"] == 2
    assert by_year[2017]["gone"] == 1
    assert by_year[2017]["in_current_ticker_map"] == 1
    # And it must not appear in years after it left.
    assert by_year[2020]["filers"] == 1
    assert [row["cik"] for row in departed] == ["0000000001"]


def test_an_acquisition_is_not_counted_as_a_failure():
    """Assuming every disappearance was a wipe-out overcorrects the bias it is fixing."""
    by_year, departed = cohorts(
        {"0000000001": periodic("2017-02-01", "2019-05-01"),
         "0000000002": periodic("2017-02-01", "2019-05-01"),
         "0000000003": periodic("2017-02-01", "2026-02-01")},
        {"0000000001": [{"form": "25-NSE", "filed": "2019-06-01"}]},
        {"0000000003"})
    assert by_year[2017]["gone"] == 2
    assert by_year[2017]["gone_by_transaction"] == 1
    assert by_year[2017]["gone_silently"] == 1
    acquired = next(row for row in departed if row["cik"] == "0000000001")
    assert acquired["exit_forms"][0]["form"] == "25-NSE"


def test_a_company_absent_from_the_current_ticker_map_is_the_measurement():
    """filers minus in_current_ticker_map is exactly what a backtest here cannot see."""
    by_year, _ = cohorts(
        {"0000000001": periodic("2018-02-01", "2020-05-01"),
         "0000000002": periodic("2018-02-01", "2026-02-01")},
        {}, {"0000000002"})
    invisible = by_year[2018]["filers"] - by_year[2018]["in_current_ticker_map"]
    assert invisible == 1


def test_an_empty_index_yields_no_cohorts_rather_than_a_divide_by_zero():
    assert cohorts({}, {}, set()) == ({}, [])
    assert parse_form_index("") == []
