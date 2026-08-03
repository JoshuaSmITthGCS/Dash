"""Fetch adjusted histories and publish versioned ETF comparison files.

Run from pipeline/: python build_etf_comparisons.py. Existing advisor/prices outputs are
not replaced; each contract is atomically written under public/data/etf/.
"""

import json
import os
from datetime import timezone

from cache import CACHE, limiter_for, parallel_map, retry_with_backoff
from common import CONFIG_DIR, DATA_DIR, LOG, load_json, update_pipeline_status
from etf_comparison import build_contract


def _rows(frame):
    if frame is None or frame.empty:
        return []
    # auto_adjust=True incorporates splits and cash distributions into Close.
    return [{"date": index.tz_convert("UTC").date().isoformat() if getattr(index, "tzinfo", None) else index.date().isoformat(),
             "adjusted_close": float(row["Close"])} for index, row in frame.iterrows()
            if row.get("Close") is not None]


def _registry():
    with open(os.path.join(CONFIG_DIR, "etf_benchmarks.json")) as handle:
        return json.load(handle)


def _fetch_rows(symbol, yf, period, cache):
    """Full adjusted history for one symbol - rate-limited, retried, and cached.

    This used to call yf.Ticker(...).history() directly with no pacing at all, right after
    fetch_advisor.py and fetch_etfs.py had already spent the same run's Yahoo budget on
    ~1,000 other symbols. Routing through the shared limiter and disk cache (same as every
    other Yahoo call in the pipeline) means a rate-limited fetch retries with backoff and,
    failing that, falls back to yesterday's cached history instead of going unavailable.
    """
    def produce():
        limiter_for("yahoo").acquire()
        frame = retry_with_backoff(
            lambda: yf.Ticker(symbol).history(period=period, auto_adjust=True, actions=True),
            description=f"full history for {symbol}")
        return _rows(frame)
    return cache.fetch("etf_full_history", f"{symbol}:{period}", produce, source="yahoo")


def _fetch_histories(symbols, yf, period, cache, max_workers=None):
    """Fetch distinct histories concurrently while each request remains rate-limited."""
    distinct = list(dict.fromkeys(symbol for symbol in symbols if symbol))
    workers = max_workers or int(os.getenv("ETF_COMPARISON_WORKERS", "6"))
    results = parallel_map(
        lambda symbol: (symbol, _fetch_rows(symbol, yf, period, cache)),
        distinct,
        provider="yahoo",
        max_workers=workers,
        on_error=lambda symbol, _error: (symbol, None),
    )
    return dict(results)


def build_all(period="max"):
    try:
        import yfinance as yf
    except ImportError:
        LOG.error("yfinance missing; cannot build ETF comparisons")
        return None
    universe = load_json("universe.json", from_config=True) or {}
    registry = _registry()
    output_dir = os.path.join(DATA_DIR, "etf")
    os.makedirs(output_dir, exist_ok=True)
    complete, failed = [], {}
    etfs = universe.get("etfs", {})
    benchmarks = {
        ticker: {**registry["default"], **registry.get("funds", {}).get(ticker, {})}
        for ticker in etfs
    }
    fetch_symbols = [
        symbol
        for ticker, benchmark in benchmarks.items()
        for symbol in (ticker, benchmark.get("benchmark_ticker"))
    ]
    fetched = _fetch_histories(fetch_symbols, yf, period, CACHE)
    for ticker in etfs:
        benchmark = benchmarks[ticker]
        benchmark_ticker = benchmark.get("benchmark_ticker")
        try:
            if not fetched.get(ticker):
                raise ValueError(f"No adjusted history for {ticker}")
            payload = build_contract(ticker, fetched[ticker], fetched.get(benchmark_ticker) or [], benchmark)
            path = os.path.join(output_dir, f"{ticker}.json")
            temporary = f"{path}.tmp"
            with open(temporary, "w") as handle:
                json.dump(payload, handle, indent=2, allow_nan=False)
                handle.write("\n")
            os.replace(temporary, path)
            complete.append(ticker)
        except Exception as error:  # noqa: BLE001
            failed[ticker] = type(error).__name__
            LOG.warn(f"{ticker}: ETF comparison unavailable ({type(error).__name__})")
    status = "healthy" if not failed else ("degraded" if complete else "error")
    update_pipeline_status("etf_comparisons", status=status, source="Yahoo Finance adjusted history",
                           details={"complete": complete, "failed": failed, "output": "public/data/etf/<ticker>.json"})
    return {"complete": complete, "failed": failed}


if __name__ == "__main__":
    raise SystemExit(0 if build_all() is not None else 1)
