"""Round-12 valuation audit: shares_outstanding lineage and plausibility screening.

plausibility.implied_share_count_violations exists to catch a market cap that doesn't
reconcile with price times shares outstanding, but it could never fire in production because
no live snapshot ever set `shares_outstanding`. fetch_snapshot now carries Yahoo's own
`sharesOutstanding` -- the same quote payload as `marketCap`/`currentPrice`, so the check
stays meaningful (it catches a genuine same-source inconsistency) without conflating it with
the separate, unresolved ADR ordinary-vs-ADS share-count question (see adr_registry.py).
"""
import os
import sys
import unittest

import pandas as pd

PIPELINE_DIR = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, PIPELINE_DIR)

from fetch_prices import fetch_snapshot
from plausibility import screen as screen_plausibility


class _FakeTickerObj:
    def __init__(self, info):
        self._info = info

    def history(self, period=None, auto_adjust=False):
        n = 30
        idx = pd.date_range("2026-01-01", periods=n, freq="D")
        return pd.DataFrame({
            "Close": [100.0 + i for i in range(n)], "Volume": [1_000_000] * n,
        }, index=idx)

    @property
    def info(self):
        return self._info


class SharesOutstandingLineageTests(unittest.TestCase):
    def test_shares_outstanding_is_carried_onto_the_snapshot(self):
        ticker_obj = _FakeTickerObj({
            "shortName": "Example Corp", "currentPrice": 100.0, "marketCap": 10_000_000_000,
            "sharesOutstanding": 100_000_000,
        })
        snap = fetch_snapshot("EX", yf=None, etf_ids=set(), ticker_obj=ticker_obj)
        self.assertEqual(snap["shares_outstanding"], 100_000_000)

    def test_self_consistent_quote_never_trips_the_implied_share_count_check(self):
        """Yahoo's own price/marketCap/sharesOutstanding triple should reconcile with itself
        almost always -- this guards against the new field making the check fire on ordinary,
        healthy snapshots.
        """
        ticker_obj = _FakeTickerObj({
            "shortName": "Example Corp", "currentPrice": 100.0, "marketCap": 10_000_000_000,
            "sharesOutstanding": 100_000_000,
        })
        snap = fetch_snapshot("EX", yf=None, etf_ids=set(), ticker_obj=ticker_obj)
        _, violations = screen_plausibility(snap)
        self.assertEqual(violations, [])

    def test_stale_share_count_against_a_live_market_cap_is_caught(self):
        """A market cap that has moved (e.g. after a raise or buyback) while a cached share
        count has not -- the exact failure mode implied_share_count_violations documents --
        must be caught now that the field is actually populated.
        """
        ticker_obj = _FakeTickerObj({
            "shortName": "Example Corp", "currentPrice": 100.0,
            "marketCap": 10_000_000_000,       # implies ~100M shares at $100
            "sharesOutstanding": 20_000_000,   # a stale count implying only $2B
        })
        snap = fetch_snapshot("EX", yf=None, etf_ids=set(), ticker_obj=ticker_obj)
        screened, violations = screen_plausibility(snap)
        rules = {v["rule"] for v in violations}
        self.assertIn("market_cap_inconsistent_with_price_times_shares", rules)
        self.assertIsNone(screened["market_cap"])


if __name__ == "__main__":
    unittest.main()
