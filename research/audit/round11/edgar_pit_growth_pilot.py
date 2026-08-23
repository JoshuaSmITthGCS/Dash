"""Round 11 Priority 4 -- bounded pilot: can EDGAR PIT facts reconstruct historical growth?

Round 10 found the backtest panel's ``growth`` leg at 0.0% coverage across all 51,600
ticker-periods, root-caused to a real data-availability ceiling: Yahoo's quarterly statement
history typically reaches back only ~8 quarters, so ``backtest_historical.py`` almost never
has the two full trailing-twelve-month windows year-over-year growth needs. This script
checks whether the EDGAR point-in-time fundamentals store already collected in
``pipeline/data/pit/fundamentals/`` (4.78M+ as-filed observations, ``filed`` timestamps back
to 2009) can do better, without look-ahead risk -- every value used here is filtered to
``filed <= as_of``, the same guarantee ``edgar_enrichment.edgar_ttm_statements`` already
provides for the live pipeline's statement enrichment path.

Scope, deliberately bounded per the brief: the 21 names in ``advisor_universe.json``'s
``portfolio_symbols`` (not "45" -- that number was the brief's assumption; the live universe
has 21, of which 19 are equities with a resolvable CIK and 2 -- VOO, VGT -- are ETFs with no
XBRL financials to fetch), over the most recent 24 monthly dates already present in
``pipeline/backtest_signal_panel.json`` (2024-09 through 2026-08). Revenue TTM growth only,
not the full multi-input growth score -- this is a feasibility check on data availability,
not a re-derivation of the production growth metric.

Runs entirely from data already collected and committed to the repo (the PIT fundamentals
shards and the SEC ticker->CIK entity map cache) -- no network access needed or used.
"""

import json
import os
import sys
from datetime import datetime, timedelta

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(REPO, "pipeline"))

from edgar_enrichment import _ticker_to_cik, edgar_ttm_statements  # noqa: E402

PANEL_PATH = os.path.join(REPO, "pipeline", "backtest_signal_panel.json")
UNIVERSE_PATH = os.path.join(REPO, "pipeline", "config", "advisor_universe.json")
ADVISOR_PATH = os.path.join(REPO, "public", "data", "advisor.json")
OUTPUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "edgar_pit_growth_pilot_results.json")

PILOT_WINDOW = 24  # months


def one_year_before(date_str):
    date = datetime.strptime(date_str, "%Y-%m-%d")
    return (date - timedelta(days=365)).strftime("%Y-%m-%d")


def ttm_revenue(symbol, as_of):
    statements = edgar_ttm_statements(symbol, as_of)
    if not statements:
        return None
    row = statements.get("income", {}).get("rows", {}).get("Total Revenue")
    return row[0] if row else None


def revenue_growth(symbol, as_of):
    current = ttm_revenue(symbol, as_of)
    prior = ttm_revenue(symbol, one_year_before(as_of))
    if current is None or prior is None or prior == 0:
        return None
    return round((current - prior) / abs(prior), 4)


def main():
    panel = json.load(open(PANEL_PATH))
    dates = [period["date"] for period in panel["periods"]][-PILOT_WINDOW:]
    universe = json.load(open(UNIVERSE_PATH))
    portfolio_symbols = universe.get("portfolio_symbols", [])

    cik_map = _ticker_to_cik()
    equities = [symbol for symbol in portfolio_symbols if symbol in cik_map]
    no_cik = [symbol for symbol in portfolio_symbols if symbol not in cik_map]

    rows = []
    covered = 0
    for symbol in equities:
        for date in dates:
            growth = revenue_growth(symbol, date)
            rows.append({"symbol": symbol, "date": date, "revenue_ttm_growth": growth})
            if growth is not None:
                covered += 1

    total = len(rows)
    coverage_pct = round(100 * covered / total, 1) if total else 0.0

    # Compare the most recent reconstructed value against the live published growth score,
    # as a directional sanity check (not an exact match -- production's growth score blends
    # revenue growth with earnings growth and other inputs; EDGAR PIT here is revenue only).
    sanity_check = []
    try:
        advisor = json.load(open(ADVISOR_PATH))
        published_by_ticker = {row["ticker"]: row for row in advisor.get("research", [])}
        latest_date = dates[-1]
        for symbol in equities:
            published = published_by_ticker.get(symbol)
            if not published:
                continue
            published_growth = (published.get("fundamental_categories") or {}).get("growth")
            reconstructed = next((row["revenue_ttm_growth"] for row in rows
                                  if row["symbol"] == symbol and row["date"] == latest_date), None)
            sanity_check.append({
                "symbol": symbol,
                "reconstructed_revenue_ttm_growth_pct": None if reconstructed is None
                else round(reconstructed * 100, 1),
                "published_growth_score": published_growth,
            })
    except (OSError, ValueError):
        pass

    result = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "method": "edgar_enrichment.edgar_ttm_statements, filed<=as_of enforced, no network access used",
        "window_months": PILOT_WINDOW,
        "dates": [dates[0], dates[-1]],
        "portfolio_symbols_total": len(portfolio_symbols),
        "portfolio_symbols_with_cik": len(equities),
        "portfolio_symbols_without_cik": no_cik,
        "ticker_periods_attempted": total,
        "ticker_periods_covered": covered,
        "coverage_pct": coverage_pct,
        "rows": rows,
        "sanity_check_against_live_production": sanity_check,
    }
    with open(OUTPUT, "w") as handle:
        json.dump(result, handle, indent=2)
    print(json.dumps({k: v for k, v in result.items() if k not in ("rows",)}, indent=2))


if __name__ == "__main__":
    main()
