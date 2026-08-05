"""Cache and publish the monthly Fama/French five factors plus momentum."""

import csv
import io
import json
import os
import urllib.request
import zipfile
from datetime import datetime, timezone

from common import LOG, load_json, save_json, update_pipeline_status


SETTINGS = load_json("settings.json", from_config=True) or {}
CONFIG = SETTINGS["factor_data"]
FACTOR_DIR = os.path.join(os.path.dirname(__file__), "data", "factors")
PUBLIC_NAME = "factors/french.json"
FIVE_FACTOR_FILE = os.path.join(FACTOR_DIR, "fama_french_5_monthly.zip")
MOMENTUM_FILE = os.path.join(FACTOR_DIR, "momentum_monthly.zip")


def _current_month():
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _download(url, destination):
    request = urllib.request.Request(url, headers={"User-Agent": "ValueSignal research pipeline"})
    with urllib.request.urlopen(request, timeout=CONFIG["request_timeout_seconds"]) as response:
        payload = response.read()
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    temporary = f"{destination}.tmp"
    with open(temporary, "wb") as handle:
        handle.write(payload)
    os.replace(temporary, destination)


def _read_zip_text(path):
    with zipfile.ZipFile(path) as archive:
        names = [name for name in archive.namelist() if not name.endswith("/")]
        if not names:
            raise ValueError(f"No data file found in {path}")
        return archive.read(names[0]).decode("utf-8-sig", errors="replace")


def parse_monthly_csv(text, required_columns):
    """Read the first YYYYMM section and stop before the annual table."""
    lines = text.splitlines()
    def is_header(line):
        cells = {cell.strip().replace(" ", "").lower() for cell in next(csv.reader([line]))}
        return all(column.lower() in cells for column in required_columns)

    header_index = next(index for index, line in enumerate(lines) if is_header(line))
    header = [cell.strip().replace(" ", "") for cell in next(csv.reader([lines[header_index]]))]
    rows = {}
    for cells in csv.reader(lines[header_index + 1:]):
        if not cells:
            continue
        period = cells[0].strip()
        if len(period) != 6 or not period.isdigit():
            if rows:
                break
            continue
        values = {}
        for index, name in enumerate(header[1:], start=1):
            if index >= len(cells) or not cells[index].strip():
                continue
            values[name] = float(cells[index].strip()) / 100
        rows[f"{period[:4]}-{period[4:]}"] = values
    return rows


def build_factor_payload(five_factor_text, momentum_text, generated_at=None):
    five = parse_monthly_csv(five_factor_text, ["Mkt-RF", "SMB", "HML", "RMW", "CMA", "RF"])
    momentum = parse_monthly_csv(momentum_text, ["Mom"])
    observations = []
    for month in sorted(set(five).intersection(momentum)):
        row = five[month]
        momentum_row = momentum[month]
        observations.append({
            "month": month,
            "market_excess": row["Mkt-RF"],
            "size": row["SMB"],
            "value": row["HML"],
            "profitability": row["RMW"],
            "investment": row["CMA"],
            "momentum": momentum_row.get("Mom", momentum_row.get("MOM")),
            "risk_free": row["RF"],
        })
    if not observations:
        raise ValueError("No overlapping monthly factor observations were parsed")
    return {
        "schema_version": CONFIG["schema_version"],
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "source": "Kenneth R. French Data Library",
        "frequency": "monthly",
        "units": "decimal_return",
        "count": len(observations),
        "observations": observations,
    }


def refresh_factors(force=False):
    existing = load_json(PUBLIC_NAME) or {}
    generated_month = str(existing.get("generated_at") or "")[:7]
    if not force and generated_month == _current_month() and os.path.exists(FIVE_FACTOR_FILE) and os.path.exists(MOMENTUM_FILE):
        LOG.info(f"Factor data is current for {_current_month()}")
        return existing
    try:
        _download(CONFIG["five_factor_url"], FIVE_FACTOR_FILE)
        _download(CONFIG["momentum_url"], MOMENTUM_FILE)
        payload = build_factor_payload(_read_zip_text(FIVE_FACTOR_FILE), _read_zip_text(MOMENTUM_FILE))
        save_json(PUBLIC_NAME, payload)
        update_pipeline_status("factors", status="healthy", source=payload["source"],
                               details={"observations": payload["count"]})
        LOG.info(f"Published {payload['count']} monthly factor observations")
        return payload
    except Exception as exc:  # noqa: BLE001
        update_pipeline_status("factors", status="error", source="Kenneth R. French Data Library",
                               message=f"{type(exc).__name__}: {exc}")
        LOG.error(f"Factor refresh failed: {type(exc).__name__}: {exc}")
        return None


def main():
    return 0 if refresh_factors() is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
