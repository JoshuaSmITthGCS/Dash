"""Fetch adjusted histories and publish versioned ETF comparison files.

Run from pipeline/: python build_etf_comparisons.py. Existing advisor/prices outputs are
not replaced; each contract is atomically written under public/data/etf/.
"""

import json
import os
from datetime import timezone

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
    cache = {}
    for ticker in universe.get("etfs", {}):
        benchmark = {**registry["default"], **registry.get("funds", {}).get(ticker, {})}
        benchmark_ticker = benchmark.get("benchmark_ticker")
        try:
            for symbol in (ticker, benchmark_ticker):
                if symbol and symbol not in cache:
                    cache[symbol] = yf.Ticker(symbol).history(period=period, auto_adjust=True, actions=True)
            payload = build_contract(ticker, _rows(cache[ticker]), _rows(cache.get(benchmark_ticker)), benchmark)
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
