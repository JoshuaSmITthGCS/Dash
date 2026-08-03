"""CLI: python -m pipeline.audit_ticker HIG --as-of YYYY-MM-DD"""

import argparse
import json
import os


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("ticker")
    parser.add_argument("--as-of", help="Declared review date; artifact remains point-in-time to its run manifest")
    parser.add_argument("--data", default=os.path.join(os.path.dirname(os.path.dirname(__file__)), "public", "data", "diagnostics.json"))
    args = parser.parse_args()
    try:
        with open(args.data, encoding="utf-8") as handle:
            payload = json.load(handle)
    except FileNotFoundError:
        parser.error("diagnostics.json does not exist; run fetch_advisor.py first")
    row = payload.get("tickers", {}).get(args.ticker.upper())
    if not row:
        parser.error(f"{args.ticker.upper()} is not present in the diagnostics artifact")
    output = {"requested_as_of": args.as_of, "artifact_generated_at": payload.get("generated_at"), **row}
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
