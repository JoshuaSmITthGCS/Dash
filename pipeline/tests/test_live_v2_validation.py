"""Regression coverage for the Round 8 evidence/confidence-gate defect.

Every sampled ticker on the live v2 validation dashboard (HIG, JPM, O, NEE, BSX, MSFT, XOM,
MRNA, VTI, TLT) published "Company evidence: INSUFFICIENT EVIDENCE", "Peer sample: 0 / 0",
and "Profile confidence: 0%" -- implausible for large, liquid names like MSFT and JPM.

Root cause, confirmed by direct source read of pipeline/live_v2_validation.py:

  1. ``classification`` was a hardcoded literal --
     ``{"total_peer_count": 0, "valid_peer_count": 0, "percentile_status":
     "INSUFFICIENT_VALID_PEERS"}`` for every ticker on every run -- never a call into
     peer_groups.canonical_percentiles(), the module fetch_advisor.py and
     migrate_advisor_v2.py both already use for the real peer computation. A pure stub,
     not a genuine peer-sample shortfall.
  2. ``validate_live()`` built its canonical observations from
     ``canonical_metrics.yahoo_observations(info)`` alone -- the ~11 quote-level Yahoo
     ``.info`` fields -- and never called the statement-enrichment step
     (``fetch_advisor.yahoo_extended`` / ``fundamentals_extended.extended_observations``)
     that the production pipeline's ``enrich()`` runs for its shortlist. Every
     statement-derived metric (ROIC, EV/EBITDA, Piotroski F, interest coverage, accruals
     ratio, ...) -- the metrics carrying most of the structural score's declared weight --
     therefore reported missing for every ticker regardless of real-world coverage, which
     is what dragged every company's confidence below the 0.40 insufficient-evidence gate.
     (See fundamentals_extended.py's ``EXTENDED_METRIC_UNITS`` docstring, which already
     named this exact failure mode before this fix wired the missing call in.)

Both are wiring/data-join defects in the validation harness, not a real data-coverage
gap being correctly reported -- confirmed by comparing against production: the committed
``public/data/advisor.json`` shows HIG at ``data_coverage: 0.82`` the same week this view
published ``coverage: 0.25`` for the identical company.

The timeliness layer legitimately publishing ``effective_score: None`` (no free provider
supplies broad forward-estimate revisions) is a *separate*, correctly-reported gap and is
deliberately left untouched here -- see scoring_v2.py's own ``unavailable_reason`` string.
"""

import os
import sys
import tempfile
import unittest

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from live_v2_validation import validate_live  # noqa: E402


def _statement_frame(rows, periods=("2025-12-31", "2024-12-31")):
    return pd.DataFrame(rows, index=list(periods)).T


def _price_frame(n=320, start_price=380.0, drift=0.0003, volume=20_000_000):
    dates = pd.date_range("2024-11-01", periods=n, freq="B")
    closes = [round(start_price * (1 + drift) ** i, 2) for i in range(n)]
    return pd.DataFrame({"Close": closes, "Volume": [volume] * n}, index=dates)


class _FakeTicker:
    """A single company with a full Yahoo quote payload and, optionally, statement
    frames -- everything ``yahoo_observations``, ``fetch_snapshot``, and
    ``fetch_advisor.yahoo_extended`` need to resolve real values."""

    def __init__(self, ticker, *, sector="Technology", industry="Software",
                market_cap=3_000_000_000_000.0, price=420.0, has_statements=True):
        self._info = {
            "currentPrice": price, "regularMarketPrice": price, "marketCap": market_cap,
            "shortName": ticker, "longName": ticker, "sector": sector, "industry": industry,
            "quoteType": "EQUITY", "forwardPE": 28.0, "trailingPegRatio": 2.1,
            "currentRatio": 1.9, "priceToBook": 11.0, "priceToSalesTrailing12Months": 12.0,
            "returnOnEquity": 0.35, "profitMargins": 0.36, "revenueGrowth": 0.14,
            "earningsGrowth": 0.2, "debtToEquity": 45.0, "freeCashflow": 65_000_000_000.0,
        }
        if has_statements:
            self.income_stmt = _statement_frame({
                "Total Revenue": [245_000.0, 212_000.0], "EBIT": [110_000.0, 94_000.0],
                "Net Income": [88_000.0, 72_000.0], "Pretax Income": [102_000.0, 86_000.0],
                "Tax Provision": [14_000.0, 14_000.0], "Gross Profit": [170_000.0, 146_000.0],
            })
            self.balance_sheet = _statement_frame({
                "Total Assets": [500_000.0, 420_000.0], "Total Debt": [80_000.0, 75_000.0],
                "Stockholders Equity": [250_000.0, 210_000.0],
                "Cash And Cash Equivalents": [90_000.0, 80_000.0],
            })
            self.cashflow = _statement_frame({
                "Free Cash Flow": [65_000.0, 55_000.0], "Operating Cash Flow": [90_000.0, 78_000.0],
                "Capital Expenditure": [-25_000.0, -23_000.0],
            })
        else:
            self.income_stmt = pd.DataFrame()
            self.balance_sheet = pd.DataFrame()
            self.cashflow = pd.DataFrame()
        self.quarterly_income_stmt = pd.DataFrame()
        self.quarterly_balance_sheet = pd.DataFrame()
        self.quarterly_cashflow = pd.DataFrame()
        self.options = ()
        self._history = _price_frame(start_price=price)

    @property
    def info(self):
        return dict(self._info)

    def history(self, period=None, auto_adjust=None, actions=None):
        return self._history


class _FakeYFinance:
    def __init__(self, tickers):
        self._tickers = tickers

    def Ticker(self, symbol):
        return self._tickers[symbol]


class ValidateLiveEvidenceGateTests(unittest.TestCase):
    def _run(self, fakes):
        sys.modules["yfinance"] = _FakeYFinance(fakes)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                return validate_live(
                    os.path.join(tmp, "live_v2_validation.json"),
                    os.path.join(tmp, "raw"),
                    tickers=tuple(fakes),
                )
        finally:
            del sys.modules["yfinance"]

    def test_peer_sample_is_computed_not_hardcoded_zero_zero(self):
        # Three same-sector companies with real valuation scores must count each other as
        # peers -- the pre-fix code published "0 / 0" for every ticker unconditionally,
        # including this case, where the real batch total is unambiguously 3.
        fakes = {
            "AAA": _FakeTicker("AAA", price=100.0),
            "BBB": _FakeTicker("BBB", price=150.0),
            "CCC": _FakeTicker("CCC", price=200.0),
        }

        payload = self._run(fakes)

        for row in payload["results"]:
            classification = row["classification"]
            self.assertEqual(classification["peer_group"], "sector:technology")
            self.assertEqual(classification["total_peer_count"], 3)
            self.assertEqual(classification["valid_peer_count"], 3)
            # 3 < peer_groups.MINIMUM_VALID_PEERS (30): correctly still insufficient for a
            # tier, but now an honest small-sample result instead of a fabricated "0 of 0".
            self.assertEqual(classification["percentile_status"], "INSUFFICIENT_VALID_PEERS")
            self.assertTrue(row["invariants"]["invalid_peer_sample_no_percentile"]["status"] == "pass")

    def test_statement_enrichment_is_wired_in_and_raises_confidence(self):
        # Same company, same quote payload, only difference is whether Yahoo's financial
        # statements resolve. The pre-fix code never called yahoo_extended at all, so both
        # runs would have reported identical (near-zero) structural confidence for a
        # blue-chip-shaped company -- the implausible pattern the brief flagged.
        enriched = self._run({"HEALTHY": _FakeTicker("HEALTHY", has_statements=True)})
        starved = self._run({"HEALTHY": _FakeTicker("HEALTHY", has_statements=False)})

        enriched_row = enriched["results"][0]
        starved_row = starved["results"][0]

        enriched_structural = enriched_row["analysis"]["structural"]
        starved_structural = starved_row["analysis"]["structural"]

        # Statement-derived metrics (ROIC among them) must be present with real lineage.
        self.assertIn("return_on_invested_capital", enriched_row["observations"])
        self.assertTrue(enriched_row["observations"]["return_on_invested_capital"])
        self.assertNotIn("return_on_invested_capital", starved_row["observations"])

        self.assertGreater(enriched_structural["evidence_weight_resolved"],
                           starved_structural["evidence_weight_resolved"])
        self.assertGreater(enriched_structural["coverage"], starved_structural["coverage"])

    def test_starved_company_still_correctly_reports_insufficient_evidence(self):
        # The fix must not paper over a genuine gap: a company with no statement data at
        # all should still legitimately gate low, distinguishing a real scarcity from the
        # wiring defect this module locks against above.
        payload = self._run({"STARVED": _FakeTicker("STARVED", has_statements=False)})

        row = payload["results"][0]
        self.assertEqual(row["company_action"]["label"], "insufficient_evidence")
        self.assertLess(row["company_action"]["confidence"], 0.40)


if __name__ == "__main__":
    unittest.main()
