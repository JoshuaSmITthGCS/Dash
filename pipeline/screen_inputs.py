"""Shared inputs for the research screens that score the whole published universe.

Three screens (quality-value, earnings-timeliness, structural-tactical) all need the same
four things: the scored universe, a company's cached price and statement history, whatever
the point-in-time store last observed about it, and a way to turn a raw factor into a
cross-sectional percentile. Collecting that here keeps the three builders to their own
scoring logic and keeps one definition of, for example, what "market cap" means.

Nothing here fetches. Every source is already on disk and already committed: the published
advisor snapshot, the backtest cache's decade of closes and recent statements, and the
point-in-time observation store. That is deliberate - these screens have to be rebuildable
from the repository alone, without a provider key, or they cannot be tested or re-derived.
"""

from __future__ import annotations

import json
import math
import os

from common import STORE_DIR, load_json

BACKTEST_CACHE = os.path.join(STORE_DIR, "backtest_cache")
OBSERVATIONS = os.path.join(STORE_DIR, "pit", "observations.jsonl")


def universe_rows(advisor=None):
    """The scored universe, richest row per ticker.

    `screen_universe` covers the whole scored cross-section but carries only published
    summary detail; `research` and `portfolio_coverage` carry the full fundamental row for the
    names that made the report. Merging gives every ticker whatever detail exists for it -
    notably `industry`, which the business-profile classifier needs and the summary row lacks.
    """
    advisor = advisor if advisor is not None else (load_json("advisor.json") or {})
    merged = {}
    for row in advisor.get("screen_universe") or []:
        if row.get("ticker"):
            merged[row["ticker"]] = dict(row)
    for row in [*(advisor.get("research") or []), *(advisor.get("portfolio_coverage") or [])]:
        ticker = row.get("ticker")
        if not ticker:
            continue
        merged[ticker] = {**row, **merged.get(ticker, {}),
                          # The detailed row is the only source of these two.
                          "industry": row.get("industry"), "market_cap": row.get("market_cap")}
    return list(merged.values())


def backtest_entry(ticker, root=None):
    """One ticker's cached daily closes, volumes and quarterly statements, or None."""
    path = os.path.join(root or BACKTEST_CACHE, f"{str(ticker).upper()}.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path) as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


def latest_observations(path=None):
    """{ticker: values} from the newest point-in-time observation recorded for each ticker.

    The store is append-only and one ticker appears on many days, so the last line wins.
    """
    path = path or OBSERVATIONS
    if not os.path.exists(path):
        return {}
    latest = {}
    with open(path) as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if not isinstance(row, dict):
                continue
            ticker, observed = row.get("ticker"), str(row.get("observed_at") or row.get("observation_date") or "")
            if not ticker:
                continue
            if ticker not in latest or observed >= latest[ticker]["observed_at"]:
                latest[ticker] = {"observed_at": observed, "values": row.get("values") or {}}
    return {ticker: item["values"] for ticker, item in latest.items()}


def with_current_price(entry, price, as_of):
    """Extend a cached price series by today's published close.

    The backtest cache is refreshed on its own schedule, so its last session can be several
    days old - and "cheapest in its own history" is a statement about *today's* price. This
    appends the price the advisor snapshot just polled, when it is genuinely newer than
    anything cached. Volume is appended as None rather than invented: there is no volume
    figure in the snapshot, and repeating yesterday's would fabricate liquidity.
    """
    dates = (entry or {}).get("dates") or []
    day = str(as_of)[:10] if as_of else None
    if not entry or not dates or price is None or not day or day <= dates[-1]:
        return entry
    updated = {**entry, "dates": [*dates, day]}
    for key in ("closes", "raw_closes"):
        if entry.get(key):
            updated[key] = [*entry[key], float(price)]
    if entry.get("volumes"):
        updated["volumes"] = [*entry["volumes"], None]
    return updated


def median_dollar_volume(closes, volumes, window=60):
    """Median daily dollar volume over the trailing window - the liquidity screen filters use."""
    if not closes or not volumes or len(closes) != len(volumes):
        return None
    paired = [(close, volume) for close, volume in zip(closes[-window:], volumes[-window:])
              if close is not None and volume is not None]
    if not paired:
        return None
    dollar = sorted(close * volume for close, volume in paired)
    middle = len(dollar) // 2
    return dollar[middle] if len(dollar) % 2 else (dollar[middle - 1] + dollar[middle]) / 2


def cross_sectional_percentiles(values):
    """Rank a factor across the universe onto 0-100, highest value at 100.

    The tactical formulas in research_screens_v2 read their inputs on a 0-100 scale and treat
    60 as the "timely" line, so raw factors (a revision breadth of -0.2, a 17% twelve-month
    return) have to be ranked before they mean anything to it. Ties share the average rank so
    a factor that is flat across half the universe does not hand half the universe a 100.
    """
    present = sorted((float(value), index) for index, value in enumerate(values)
                     if value is not None and math.isfinite(float(value)))
    output = [None] * len(values)
    if not present:
        return output
    if len(present) == 1:
        output[present[0][1]] = 50.0
        return output
    position, count = 0, len(present)
    while position < count:
        end = position
        while end + 1 < count and present[end + 1][0] == present[position][0]:
            end += 1
        rank = (position + end) / 2
        for item in present[position:end + 1]:
            output[item[1]] = 100 * rank / (count - 1)
        position = end + 1
    return output
