"""Rebuild the compact report payload from the latest complete advisor payload."""

from common import load_json, save_json
from fetch_advisor import report_snapshot


def run():
    payload = load_json("advisor.json")
    if not payload:
        raise SystemExit("public/data/advisor.json is unavailable")
    save_json("report.json", report_snapshot(payload))


if __name__ == "__main__":
    run()
