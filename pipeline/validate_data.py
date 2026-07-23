"""Validate public JSON against versioned schemas and cross-file invariants."""

import argparse
import json
import os
import sys
from datetime import date
from jsonschema import Draft202012Validator, FormatChecker

from common import DATA_DIR

SCHEMA_DIR = os.path.join(os.path.dirname(__file__), "schemas")
FILES = ("trades", "prices", "news", "politicians", "signals", "picks", "status", "advisor")


def load(path):
    with open(path) as handle:
        return json.load(handle)


def validate(production=False):
    errors = []
    payloads = {}
    for name in FILES:
        data_path = os.path.join(DATA_DIR, f"{name}.json")
        schema_path = os.path.join(SCHEMA_DIR, f"{name}.schema.json")
        if not os.path.exists(data_path):
            errors.append(f"{name}.json: missing")
            continue
        payload = payloads[name] = load(data_path)
        validator = Draft202012Validator(load(schema_path), format_checker=FormatChecker())
        for error in sorted(validator.iter_errors(payload), key=lambda e: list(e.path)):
            location = ".".join(str(part) for part in error.path) or "$"
            errors.append(f"{name}.json:{location}: {error.message}")

    for name in ("trades", "prices", "news", "politicians", "signals"):
        payload = payloads.get(name, {})
        collection = payload.get(name if name != "politicians" else "leaderboard")
        if name == "prices":
            collection = payload.get("prices")
        if collection is not None and payload.get("count") != len(collection):
            errors.append(f"{name}.json: count does not match collection length")

    advisor = payloads.get("advisor", {})
    if advisor and advisor.get("count") != len(advisor.get("research", [])):
        errors.append("advisor.json: count does not match research length")
    expected_weights = {"fundamentals": 0.75, "market_behavior": 0.15, "news_sentiment": 0.10}
    if advisor and advisor.get("methodology", {}).get("weights") != expected_weights:
        errors.append("advisor.json: ranking weights must remain 75% fundamentals, 15% market behavior, 10% news")
    scores = [row.get("score", -1) for row in advisor.get("research", [])]
    if scores != sorted(scores, reverse=True):
        errors.append("advisor.json: research rows are not ranked by descending score")
    if advisor.get("universe_count", 0) >= 20 and advisor.get("count") != 20:
        errors.append("advisor.json: a universe of 20+ companies must publish exactly 20 rankings")
    for index, row in enumerate(advisor.get("research", [])):
        if row.get("components", {}).get("fundamentals") is None:
            errors.append(f"advisor.json:research.{index}: ranked company lacks a fundamental score")
        if all(row.get(metric) is None for metric in ("peg", "forward_pe", "price_to_sales", "price_to_book")):
            errors.append(f"advisor.json:research.{index}: ranked company lacks every valuation metric")

    # Legacy political fixtures stay explicitly demo while the independent advisor dataset is live.
    modes = {p.get("data_mode") for key, p in payloads.items() if key not in ("status", "advisor")}
    if len(modes) > 1:
        errors.append(f"data_mode mismatch across payloads: {sorted(modes)}")
    if production and modes != {"live"}:
        errors.append("production validation requires data_mode=live in every payload")

    for index, trade in enumerate(payloads.get("trades", {}).get("trades", [])):
        if trade.get("filing_lag_days") is not None and trade["filing_lag_days"] < 0:
            errors.append(f"trades.json:trades.{index}: filing date precedes trade date")
        if production and trade.get("source") == "mock":
            errors.append(f"trades.json:trades.{index}: mock source forbidden in production")

    if production:
        oldest = payloads.get("trades", {}).get("history_oldest_trade_date")
        try:
            history_days = (date.today() - date.fromisoformat(oldest)).days
        except (TypeError, ValueError):
            history_days = 0
        if history_days < 95:
            errors.append(f"production requires at least 95 days of trade history (found {history_days})")

    for index, item in enumerate(payloads.get("news", {}).get("items", [])):
        if payloads["news"].get("data_mode") == "live" and not item.get("url", "").startswith("http"):
            errors.append(f"news.json:items.{index}: live item needs an http(s) source URL")

    return errors


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--production", action="store_true", help="reject demo/mock data")
    args = parser.parse_args()
    errors = validate(production=args.production)
    if errors:
        print("Data validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(f"Validated {len(FILES)} public data contracts ({'production' if args.production else 'any mode'}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
