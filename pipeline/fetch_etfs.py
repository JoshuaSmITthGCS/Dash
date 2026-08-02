"""Build a standalone, growth-ranked ETF dataset.

Diversified funds don't carry the fundamentals ratios (PEG, P/S, ROE...) the stock
research pipeline scores on, so ETFs are evaluated separately here, against each other,
on price behavior alone. Growth (20-day return, with weekly/quarterly support) is the
headline metric; dividend yield and expense ratio are informational context, not inputs
to the ranking.
"""

from datetime import datetime, timezone

from advisor_engine import technical_factors
from common import LOG, load_json, save_json, update_pipeline_status
from fetch_prices import fetch_snapshot

UNIVERSE = load_json("universe.json", from_config=True) or {}
ETFS = UNIVERSE.get("etfs", {})
BENCHMARK = "SPY"


def price_history(symbol, yf, ticker_obj=None):
    try:
        source = ticker_obj or yf.Ticker(symbol)
        frame = source.history(period="2y", auto_adjust=False).dropna(subset=["Close"])
        return {
            "closes": [float(value) for value in frame["Close"].tolist()],
            "volumes": [float(value) for value in frame["Volume"].fillna(0).tolist()],
        }
    except Exception as exc:  # noqa: BLE001
        LOG.warn(f"{symbol}: Yahoo price history unavailable ({type(exc).__name__})")
        return {"closes": [], "volumes": []}


def build_etf_row(ticker, meta, snapshot, technical):
    growth_score = round(
        (technical.get("return_20d") or 0) * 0.55
        + (technical.get("return_5d") or 0) * 0.25
        + (technical.get("return_60d") or 0) * 0.20,
        2,
    )
    return {
        "ticker": ticker,
        "name": meta.get("name", ticker),
        "category": meta.get("category", "etf"),
        "expense_ratio": meta.get("expense_ratio"),
        "price": snapshot.get("price"),
        "dividend_yield": snapshot.get("dividend_yield"),
        "growth_score": growth_score,
        "confidence": technical.get("coverage", 1.0),
        "stance": "DIVERSIFIED",
        "technical_detail": technical,
    }


def rank_etf_rows(rows):
    ranked = sorted(rows, key=lambda row: row["growth_score"], reverse=True)
    for index, row in enumerate(ranked):
        row["growth_rank"] = index + 1
    return ranked


def build_etfs():
    try:
        import yfinance as yf
    except ImportError:
        LOG.error("yfinance not installed. pip install -r requirements.txt")
        return None

    tickers = list(ETFS.keys())
    etf_ids = set(tickers)
    benchmark_closes = price_history(BENCHMARK, yf)["closes"]

    rows = []
    for ticker in tickers:
        snapshot = fetch_snapshot(ticker, yf, etf_ids) or {}
        history = price_history(ticker, yf)
        _, technical = technical_factors(history["closes"], benchmark_closes, history["volumes"])
        if not technical.get("coverage"):
            LOG.warn(f"{ticker}: not enough price history for ETF technicals")
            continue
        rows.append(build_etf_row(ticker, ETFS[ticker], snapshot, technical))

    ranked = rank_etf_rows(rows)
    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_mode": "live",
        "benchmark": BENCHMARK,
        "count": len(ranked),
        "etfs": ranked,
    }
    minimum = max(1, len(tickers) // 2)
    if len(ranked) < minimum:
        message = f"Only {len(ranked)}/{len(tickers)} ETF snapshots fetched"
        LOG.error(f"{message}; refusing to replace etfs.json")
        update_pipeline_status("etfs", status="error", source="Yahoo Finance", message=message)
        return None

    save_json("etfs.json", payload)
    update_pipeline_status("etfs", status="healthy", source="Yahoo Finance",
                           details={"requested": len(tickers), "received": len(ranked)})
    LOG.info(f"Wrote etfs.json with {len(ranked)} ETFs")
    return payload


def main():
    return 0 if build_etfs() is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
