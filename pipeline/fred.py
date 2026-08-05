"""Minimal FRED macro-regime integration.

Raw observations are held in memory only. The published output contains derived
factor scores, coverage, freshness dates, series identifiers, and attribution.
"""

import os
from datetime import datetime, timezone

import requests

from alpha_vantage import load_local_env

BASE_URL = "https://api.stlouisfed.org/fred/series/observations"
TERMS_URL = "https://fred.stlouisfed.org/docs/api/terms_of_use.html"
NOTICE = "This product uses the FRED® API but is not endorsed or certified by the Federal Reserve Bank of St. Louis."

SERIES = {
    "treasury_10y": {"id": "DGS10", "limit": 90},
    "fed_funds": {"id": "DFF", "limit": 30},
    "cpi": {"id": "CPIAUCSL", "limit": 25},
    "unemployment": {"id": "UNRATE", "limit": 6},
    "yield_curve": {"id": "T10Y2Y", "limit": 90},
    "sahm": {"id": "SAHMREALTIME", "limit": 6},
}


class FredError(RuntimeError):
    pass


class FredClient:
    def __init__(self, api_key=None):
        load_local_env()
        self.api_key = api_key or os.getenv("FRED_API_KEY")
        if not self.api_key:
            raise FredError("FRED_API_KEY is not configured")

    def observations(self, series_id, limit):
        response = requests.get(
            BASE_URL,
            params={
                "series_id": series_id,
                "api_key": self.api_key,
                "file_type": "json",
                "sort_order": "desc",
                "limit": limit,
            },
            headers={"User-Agent": "ValueSignal/1.0 personal-research-dashboard"},
            timeout=30,
        )
        if response.status_code != 200:
            raise FredError(f"FRED {series_id} request failed with HTTP {response.status_code}")
        payload = response.json()
        if not isinstance(payload.get("observations"), list):
            raise FredError(f"FRED {series_id} returned an invalid response")
        rows = []
        for row in payload["observations"]:
            try:
                rows.append({"date": row["date"], "value": float(row["value"])})
            except (KeyError, TypeError, ValueError):
                continue
        if not rows:
            raise FredError(f"FRED {series_id} returned no numeric observations")
        return rows


def clamp(value, low=0.0, high=100.0):
    return max(low, min(high, value))


def label(score):
    if score >= 65:
        return "supportive"
    if score <= 35:
        return "restrictive"
    return "neutral"


def _change(rows, periods):
    if len(rows) <= periods:
        return 0.0
    return rows[0]["value"] - rows[periods]["value"]


def derive_regime(series_rows):
    """Turn current observations into bounded, auditable 0-100 factor scores."""
    present = set(series_rows)
    factors = {}

    if {"treasury_10y", "fed_funds"} & present:
        ten_year = series_rows.get("treasury_10y", [{"value": 4.0}])
        fed_funds = series_rows.get("fed_funds", [{"value": 4.0}])
        level = 0.65 * ten_year[0]["value"] + 0.35 * fed_funds[0]["value"]
        trend = 0.65 * _change(ten_year, min(59, len(ten_year) - 1)) + 0.35 * _change(
            fed_funds, min(19, len(fed_funds) - 1)
        )
        score = clamp(92 - max(0, level - 2.0) * 18 - max(0, trend) * 12 + max(0, -trend) * 5)
        factors["rates"] = {
            "score": round(score, 1), "label": label(score),
            "as_of": max(ten_year[0]["date"], fed_funds[0]["date"]),
        }

    cpi = series_rows.get("cpi", [])
    if len(cpi) >= 13 and cpi[12]["value"]:
        yoy = (cpi[0]["value"] / cpi[12]["value"] - 1) * 100
        prior_yoy = (cpi[1]["value"] / cpi[13]["value"] - 1) * 100 if len(cpi) >= 14 and cpi[13]["value"] else yoy
        trend = yoy - prior_yoy
        score = clamp(90 - abs(yoy - 2.0) * 20 - max(0, trend) * 20)
        factors["inflation"] = {"score": round(score, 1), "label": label(score), "as_of": cpi[0]["date"]}

    unemployment = series_rows.get("unemployment", [])
    sahm = series_rows.get("sahm", [])
    if unemployment or sahm:
        labor_scores = []
        if unemployment:
            level = unemployment[0]["value"]
            trend = _change(unemployment, min(3, len(unemployment) - 1))
            labor_scores.append(clamp(88 - max(0, level - 3.5) * 16 - max(0, trend) * 30))
        if sahm:
            labor_scores.append(clamp(95 - max(0, sahm[0]["value"]) * 100))
        score = sum(labor_scores) / len(labor_scores)
        labor_dates = [
            rows[0]["date"] for rows in (unemployment, sahm) if rows
        ]
        factors["labor"] = {
            "score": round(score, 1), "label": label(score), "as_of": max(labor_dates),
        }

    curve = series_rows.get("yield_curve", [])
    if curve:
        score = clamp(50 + curve[0]["value"] * 32 + max(0, _change(curve, min(59, len(curve) - 1))) * 8)
        factors["yield_curve"] = {
            "score": round(score, 1), "label": label(score), "as_of": curve[0]["date"],
        }

    weights = {"rates": 0.30, "inflation": 0.25, "labor": 0.25, "yield_curve": 0.20}
    available = [(factors[name]["score"], weight) for name, weight in weights.items() if name in factors]
    score = sum(value * weight for value, weight in available) / sum(weight for _, weight in available)
    freshness = max(
        (rows[0]["date"] for rows in series_rows.values() if rows),
        default=datetime.now(timezone.utc).date().isoformat(),
    )
    risk_free_rates = {
        name: {
            "annual_percent": round(rows[0]["value"], 4),
            "as_of": rows[0]["date"],
            "series_id": SERIES[name]["id"],
        }
        for name, rows in series_rows.items()
        if name in {"fed_funds", "treasury_10y"} and rows
    }
    return {
        "score": round(score, 1),
        "label": label(score),
        "coverage": round(sum(weight for name, weight in weights.items() if name in factors), 2),
        "freshness_date": freshness,
        "factors": factors,
        "series": {name: config["id"] for name, config in SERIES.items() if name in series_rows},
        "risk_free_rates": risk_free_rates,
        "attribution": "Federal Reserve Economic Data (FRED), Federal Reserve Bank of St. Louis",
        "notice": NOTICE,
        "terms_url": TERMS_URL,
    }


def fetch_regime(client):
    rows, failures = {}, []
    for name, config in SERIES.items():
        try:
            rows[name] = client.observations(config["id"], config["limit"])
        except FredError:
            failures.append(config["id"])
    if len(rows) < 2:
        raise FredError("Too few FRED series were available to derive a macro regime")
    regime = derive_regime(rows)
    regime["failed_series"] = failures
    return regime
