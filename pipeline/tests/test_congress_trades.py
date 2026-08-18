import unittest
import urllib.error
from unittest.mock import Mock, patch

from congress_trades import (CongressTradesClient, CongressTradesError, SenateEfdClient,
                             StockWatcherClient, normalize_date)


class NormalizeDateTests(unittest.TestCase):
    """Every date comparison downstream - the publish window, the late-filing flag, the
    price lookup - is a string compare, so a mixed format sorts and filters wrong instead
    of raising."""

    def test_us_slash_dates_become_iso(self):
        self.assertEqual(normalize_date("10/04/2021"), "2021-10-04")
        self.assertEqual(normalize_date("1/2/2021"), "2021-01-02")

    def test_iso_dates_pass_through_and_are_truncated_to_the_day(self):
        self.assertEqual(normalize_date("2026-07-15"), "2026-07-15")
        self.assertEqual(normalize_date("2026-07-15T00:00:00"), "2026-07-15")

    def test_unparseable_and_blank_values_become_none(self):
        for value in (None, "", "--", "not a date"):
            self.assertIsNone(normalize_date(value))


class StockWatcherClientTests(unittest.TestCase):
    HOUSE_ROW = {
        "disclosure_date": "10/04/2021", "transaction_date": "09/27/2021", "owner": "joint",
        "ticker": "bp", "asset_description": "BP plc", "type": "purchase",
        "amount": "$1,001 - $15,000", "representative": "Hon. Virginia Foxx",
        "district": "NC05", "ptr_link": "https://example.com/ptr",
    }
    SENATE_ROW = {
        "disclosure_date": "11/02/2021", "transaction_date": "10/04/2021", "owner": "Spouse",
        "ticker": "AAPL", "asset_description": "Apple Inc", "asset_type": "Stock",
        "type": "Purchase", "amount": "$1,001 - $15,000", "senator": "Thomas H Tuberville",
        "comment": "--", "ptr_link": "https://example.com/senate",
    }

    def test_house_rows_are_normalized_to_the_shared_shape(self):
        client = StockWatcherClient(opener=lambda url: [self.HOUSE_ROW])
        rows, seen = client.house_latest()

        self.assertEqual(seen, 1)
        self.assertEqual(rows[0]["chamber"], "house")
        self.assertEqual(rows[0]["representative"], "Hon. Virginia Foxx")
        self.assertEqual(rows[0]["symbol"], "BP")          # upper-cased from the scrape
        self.assertEqual(rows[0]["transaction_date"], "2021-09-27")
        self.assertEqual(rows[0]["disclosure_date"], "2021-10-04")
        self.assertEqual(rows[0]["link"], "https://example.com/ptr")

    def test_the_senate_dataset_names_the_member_differently_and_still_parses(self):
        client = StockWatcherClient(opener=lambda url: [self.SENATE_ROW])
        rows, _ = client.senate_latest()

        self.assertEqual(rows[0]["representative"], "Thomas H Tuberville")
        self.assertEqual(rows[0]["asset_type"], "Stock")
        self.assertIsNone(rows[0]["comment"])   # "--" is the mirrors' null, not a comment

    def test_rows_with_no_disclosure_date_are_dropped_rather_than_published_undated(self):
        client = StockWatcherClient(opener=lambda url: [
            {**self.HOUSE_ROW, "disclosure_date": "--"}, self.HOUSE_ROW])
        rows, seen = client.house_latest()

        self.assertEqual((len(rows), seen), (1, 2))

    def test_a_transport_failure_is_raised_as_a_congress_trades_error(self):
        def boom(url):
            raise OSError("connection reset")

        with self.assertRaises(CongressTradesError):
            StockWatcherClient(opener=boom).house_latest()

    def test_a_non_list_payload_is_rejected_rather_than_read_as_empty(self):
        client = StockWatcherClient(opener=lambda url: {"message": "forbidden"})
        with self.assertRaises(CongressTradesError):
            client.senate_latest()

    # congress-trading-monitor rows, unlike the original stock-watcher shape: one file with
    # a "chamber" field per row, and both House_DATASET and SENATE_DATASET can point at it.
    KADOA_HOUSE_ROW = {
        "chamber": "house", "filer_name": "Shri Thanedar", "office": "U.S. Representative · MI-13",
        "state": "MI", "ticker": "AAPL", "asset_name": "Apple Inc. - Common Stock",
        "asset_type": "ST", "transaction_type": "Sale (Partial)",
        "amount_range_label": "$100,001 - $250,000", "transaction_date": "2026-01-09",
        "filing_date": "2026-08-13", "owner": None,
    }
    KADOA_SENATE_ROW = {
        "chamber": "senate", "filer_name": "Mark R Warner", "office": "U.S. Senator · VA",
        "state": "VA", "ticker": None, "asset_name": "Manassas VA GO Bonds",
        "asset_type": "Municipal Security", "transaction_type": "Purchase",
        "amount_range_label": "$50,001 - $100,000", "transaction_date": "2026-07-07",
        "filing_date": "2026-08-14", "doc_url": "https://efdsearch.senate.gov/search/view/ptr/x/",
    }
    KADOA_EXECUTIVE_ROW = {
        "chamber": None, "branch": "executive", "filer_name": "Donald J Trump",
        "asset_name": "Some Bond", "asset_type": "CS", "transaction_type": "Purchase",
        "amount_range_label": "$1,001 - $15,000", "transaction_date": "2026-05-01",
        "filing_date": "2026-06-01",
    }

    def test_a_combined_file_is_split_by_each_rows_own_chamber_field(self):
        # congress-trading-monitor publishes House, Senate, and OGE executive-branch rows in
        # one file - house_latest() and senate_latest() must each read only their own slice
        # even when both point at the same URL, and an unrelated (executive) row is neither.
        combined = [self.KADOA_HOUSE_ROW, self.KADOA_SENATE_ROW, self.KADOA_EXECUTIVE_ROW]
        client = StockWatcherClient(opener=lambda url: combined)

        house_rows, house_seen = client.house_latest()
        senate_rows, senate_seen = client.senate_latest()

        self.assertEqual(house_seen, 1)
        self.assertEqual(len(house_rows), 1)
        self.assertEqual(house_rows[0]["symbol"], "AAPL")
        self.assertEqual(senate_seen, 1)
        self.assertEqual(len(senate_rows), 1)
        self.assertEqual(senate_rows[0]["representative"], "Mark R Warner")

    def test_kadoa_shaped_fields_are_read_correctly(self):
        client = StockWatcherClient(opener=lambda url: [self.KADOA_HOUSE_ROW])
        rows, _ = client.house_latest()

        row = rows[0]
        # "office" is a descriptive title in this shape, not a name - filer_name must win.
        self.assertEqual(row["representative"], "Shri Thanedar")
        self.assertEqual(row["district"], "MI")
        self.assertEqual(row["disclosure_date"], "2026-08-13")   # from filing_date
        self.assertEqual(row["amount"], "$100,001 - $250,000")   # from amount_range_label
        self.assertEqual(row["asset_description"], "Apple Inc. - Common Stock")

    def test_the_house_clerks_short_stock_code_is_translated_so_it_still_matches(self):
        # is_equity_purchase() in build_congress_screen.py matches the literal substring
        # "stock" - an untranslated "ST" would silently drop every House stock purchase out
        # of price-performance and the size/novelty flags.
        client = StockWatcherClient(opener=lambda url: [self.KADOA_HOUSE_ROW])
        rows, _ = client.house_latest()

        self.assertIn("stock", rows[0]["asset_type"].lower())

    def test_a_non_stock_short_code_is_left_alone_and_still_excluded_as_non_equity(self):
        client = StockWatcherClient(opener=lambda url: [self.KADOA_SENATE_ROW])
        rows, _ = client.senate_latest()

        # "Municipal Security" already contains no "stock" substring - nothing to translate,
        # and it must keep failing the equity-purchase check, not accidentally pass it.
        self.assertNotIn("stock", rows[0]["asset_type"].lower())

    def test_a_row_with_no_chamber_field_is_trusted_to_be_whichever_chamber_was_asked_for(self):
        # The original stock-watcher shape has no "chamber" field at all - every row in the
        # file is that chamber by construction, and that has to keep working unmodified.
        client = StockWatcherClient(opener=lambda url: [self.HOUSE_ROW])
        rows, seen = client.house_latest()

        self.assertEqual(seen, 1)
        self.assertEqual(rows[0]["chamber"], "house")


class CongressTradesClientTests(unittest.TestCase):
    def test_requires_an_api_key(self):
        with self.assertRaises(CongressTradesError):
            CongressTradesClient(api_key="")

    @patch("congress_trades.requests.get")
    def test_senate_latest_normalizes_fields(self, get):
        get.return_value = Mock(status_code=200, json=lambda: [{
            "symbol": "AAPL", "disclosureDate": "2026-08-01", "transactionDate": "2026-07-15",
            "firstName": "Jane", "lastName": "Doe", "office": "Jane Doe", "owner": "Spouse",
            "type": "Purchase", "amount": "$15,001 - $50,000", "link": "https://example.com/a",
        }])
        client = CongressTradesClient(api_key="key")

        rows = client.senate_latest()

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["chamber"], "senate")
        self.assertEqual(row["representative"], "Jane Doe")
        self.assertEqual(row["transaction_type"], "Purchase")
        self.assertEqual(row["amount"], "$15,001 - $50,000")
        self.assertEqual(row["transaction_date"], "2026-07-15")
        self.assertEqual(row["disclosure_date"], "2026-08-01")

    @patch("congress_trades.requests.get")
    def test_house_latest_falls_back_to_first_last_name_when_office_is_missing(self, get):
        get.return_value = Mock(status_code=200, json=lambda: [{
            "symbol": "MSFT", "firstName": "John", "lastName": "Smith",
            "district": "TX-01", "type": "Sale", "amount": "$1,001 - $15,000",
        }])
        client = CongressTradesClient(api_key="key")

        rows = client.house_latest()

        self.assertEqual(rows[0]["representative"], "John Smith")
        self.assertEqual(rows[0]["chamber"], "house")
        self.assertEqual(rows[0]["district"], "TX-01")

    @patch("congress_trades.requests.get")
    def test_http_error_does_not_expose_the_api_key(self, get):
        get.return_value = Mock(status_code=401, json=lambda: {})
        client = CongressTradesClient(api_key="super-secret-key")

        with self.assertRaisesRegex(CongressTradesError, r"HTTP 401") as raised:
            client.senate_latest()
        self.assertNotIn("super-secret-key", str(raised.exception))

    @patch("congress_trades.requests.get")
    def test_error_payload_message_is_surfaced(self, get):
        get.return_value = Mock(status_code=200, json=lambda: {"Error Message": "Invalid API KEY."})
        client = CongressTradesClient(api_key="key")

        with self.assertRaisesRegex(CongressTradesError, "Invalid API KEY"):
            client.senate_latest()

    @patch("congress_trades.requests.get")
    def test_price_history_sorts_oldest_first_and_falls_back_to_price_field(self, get):
        get.return_value = Mock(status_code=200, json=lambda: [
            {"date": "2026-07-15", "close": 200.0},
            {"date": "2026-07-10", "price": 195.0},
        ])
        client = CongressTradesClient(api_key="key")

        points = client.price_history("AAPL", from_date="2026-07-01")

        self.assertEqual(points, [
            {"date": "2026-07-10", "close": 195.0},
            {"date": "2026-07-15", "close": 200.0},
        ])

    @patch("congress_trades.requests.get")
    def test_price_history_skips_rows_missing_a_date_or_close(self, get):
        get.return_value = Mock(status_code=200, json=lambda: [
            {"date": "2026-07-15", "close": 200.0},
            {"date": None, "close": 100.0},
            {"date": "2026-07-16"},
        ])
        client = CongressTradesClient(api_key="key")

        points = client.price_history("AAPL")

        self.assertEqual(points, [{"date": "2026-07-15", "close": 200.0}])


EFD_HOME_HTML = ('<form><input type="hidden" name="csrfmiddlewaretoken" value="tok-1">'
                 '<input type="checkbox" name="prohibition_agreement"></form>')

EFD_REPORT_HTML = """
<table class="table">
  <thead><tr>
    <th>#</th><th>Transaction Date</th><th>Owner</th><th>Ticker</th><th>Asset Name</th>
    <th>Asset Type</th><th>Type</th><th>Amount</th><th>Comment</th>
  </tr></thead>
  <tbody>
    <tr><td>1</td><td>07/15/2026</td><td>Spouse</td>
        <td><a href="/x">AAPL</a></td><td>Apple Inc</td><td>Stock</td>
        <td>Purchase</td><td>$1,001 - $15,000</td><td>--</td></tr>
    <tr><td>2</td><td>07/16/2026</td><td>Self</td>
        <td>--</td><td>US Treasury Note</td><td>Corporate Bond</td>
        <td>Sale (Full)</td><td>$15,001 - $50,000</td><td>maturity</td></tr>
  </tbody>
</table>"""


class _FakeEfdSession:
    """Stands in for a requests.Session across eFD's three-step flow."""

    def __init__(self, search_pages, report_html=EFD_REPORT_HTML, home_html=EFD_HOME_HTML):
        self.headers = {}
        self.search_pages = list(search_pages)
        self.report_html = report_html
        self.home_html = home_html
        self.posts = []

    def get(self, url, timeout=None):
        html = self.home_html if url.endswith("/search/home/") else self.report_html
        return Mock(text=html, raise_for_status=lambda: None)

    def post(self, url, data=None, headers=None, timeout=None):
        self.posts.append((url, data))
        if url.endswith("/search/home/"):
            return Mock(text=self.home_html, raise_for_status=lambda: None)
        page = self.search_pages.pop(0) if self.search_pages else []
        return Mock(raise_for_status=lambda: None, json=lambda: {"data": page})


def _efd_row(link="/search/view/ptr/abc-123/"):
    return ["Thomas", "Tuberville", "Tuberville, Thomas H. (Senator)",
            f'<a href="{link}">Periodic Transaction Report</a>', "08/01/2026"]


class SenateEfdClientTests(unittest.TestCase):
    """The Senate's own eFD, added because both community mirrors were withdrawn and now
    answer 403 to every request. Fixtures mirror eFD's documented response shapes; the live
    service is not reachable from this repository, so these pin the parsing, not the API."""

    def test_a_periodic_transaction_report_becomes_trades_in_the_shared_shape(self):
        session = _FakeEfdSession([[_efd_row()]])
        client = SenateEfdClient(session=session, request_delay=0)

        rows, seen = client.fetch(since_days=120)

        self.assertEqual(seen, 1)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["chamber"], "senate")
        self.assertEqual(rows[0]["symbol"], "AAPL")
        self.assertEqual(rows[0]["transaction_type"], "Purchase")
        self.assertEqual(rows[0]["amount"], "$1,001 - $15,000")
        self.assertEqual(rows[0]["transaction_date"], "2026-07-15")
        self.assertEqual(rows[0]["disclosure_date"], "2026-08-01")
        self.assertEqual(rows[0]["representative"], "Thomas Tuberville")

    def test_a_holding_with_no_ticker_is_kept_by_its_description(self):
        # A bond has no ticker but is still a disclosed trade; dropping it would understate
        # the volume this screen reports.
        session = _FakeEfdSession([[_efd_row()]])
        rows, _ = SenateEfdClient(session=session, request_delay=0).fetch()
        self.assertIsNone(rows[1]["symbol"])
        self.assertEqual(rows[1]["asset_description"], "US Treasury Note")

    def test_columns_are_read_by_header_not_position(self):
        # eFD drops the owner column when no report on the page has one. Reading positionally
        # would slide ticker into asset-name for every row after that.
        reordered = """
        <table><tr><th>Transaction Date</th><th>Ticker Symbol</th><th>Asset Name</th>
        <th>Type</th><th>Amount</th></tr>
        <tr><td>07/15/2026</td><td>MSFT</td><td>Microsoft</td><td>Purchase</td>
        <td>$1,001 - $15,000</td></tr></table>"""
        session = _FakeEfdSession([[_efd_row()]], report_html=reordered)
        rows, _ = SenateEfdClient(session=session, request_delay=0).fetch()
        self.assertEqual(rows[0]["symbol"], "MSFT")
        self.assertEqual(rows[0]["asset_description"], "Microsoft")

    def test_a_paper_filing_is_skipped_rather_than_read_as_a_senator_who_traded_nothing(self):
        session = _FakeEfdSession([[_efd_row(link="/search/view/paper/abc-123/")]])
        rows, seen = SenateEfdClient(session=session, request_delay=0).fetch()
        self.assertEqual(rows, [])
        self.assertEqual(seen, 1)  # counted, so coverage reads as partial rather than empty

    def test_a_home_page_without_a_csrf_token_fails_loudly(self):
        session = _FakeEfdSession([], home_html="<html><body>maintenance</body></html>")
        with self.assertRaises(CongressTradesError) as caught:
            SenateEfdClient(session=session, request_delay=0).fetch()
        self.assertIn("CSRF", str(caught.exception))

    def test_the_agreement_is_accepted_before_any_search_is_attempted(self):
        session = _FakeEfdSession([[_efd_row()]])
        SenateEfdClient(session=session, request_delay=0).fetch()
        self.assertEqual(session.posts[0][0], "https://efdsearch.senate.gov/search/home/")
        self.assertEqual(session.posts[0][1]["prohibition_agreement"], "1")
        self.assertIn("report/data", session.posts[1][0])


class WithdrawnMirrorTests(unittest.TestCase):
    def test_a_403_says_the_dataset_is_no_longer_public_rather_than_that_a_request_failed(self):
        # The actual production failure: both stock-watcher buckets answer AccessDenied.
        # "request failed" reads like something a retry next week could fix. It is not.
        def forbidden(url):
            raise urllib.error.HTTPError(url, 403, "Forbidden", {}, None)

        client = StockWatcherClient(opener=forbidden)
        with self.assertRaises(CongressTradesError) as caught:
            client.house_latest()

        self.assertIn("no longer public", str(caught.exception))
        self.assertIn("CONGRESS_HOUSE_DATASET_URL", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
