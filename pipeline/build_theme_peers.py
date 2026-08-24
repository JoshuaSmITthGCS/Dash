"""Re-rank the theme screen's sector-connected tier across the whole peer pool.

The daily refresh scores themes over published leaders, holdings, and a bounded slice of
sector peers -- ``themes.TOTAL_SECTOR_PEER_BUDGET``, 120 names shared across every theme.
That budget is not arbitrary: inside ``fetch_advisor.py`` each peer costs up to two 10-K
documents, megabytes apiece, in the same CI cache the price and statement layers already
fill, so lifting it there would multiply the refresh's footprint. The measured consequence
is in the refresh log: "Theme peer expansion stopped at the shared budget of 120
candidates; lower-ranked peers were not evaluated this run."

This job lifts the budget by moving the work out of the refresh instead of enlarging it.
It reads the published ``advisor.json`` from disk and re-scores only the sector-connected
tier, so it polls no market data at all -- no Yahoo request, no Alpha Vantage quota, no
scoring rerun. The only network cost is SEC EDGAR, which is free, cached per ticker, and
already warm for whatever the refresh evaluated earlier the same day.

Scope, and why it is much smaller than "the rest of the universe": a peer must sit in the
same peer group as one of the theme's seed tickers AND inside the theme's declared sector
scope. Against the published snapshot that is 329 distinct names out of 877 non-fund rows,
not 837 -- one job's work rather than a rotation spread over weeks.

Published leaders and portfolio holdings are excluded by construction. They already carry a
top research score or are already owned, so "connected, not yet re-rated" is precisely the
wrong label for them, and re-scoring them here would duplicate rows the refresh publishes.
"""

import json
import os
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from common import LOG, load_json, save_json  # noqa: E402
from peer_groups import peer_group  # noqa: E402
from sec_edgar import SecEdgarClient  # noqa: E402
from theme_signals import EdgarThemeSignals  # noqa: E402
from themes import build_theme_screen, empty_screen, in_theme_scope, load_themes  # noqa: E402

OUTPUT = "theme-peers.json"
SCHEMA_VERSION = 1
# Rows published per theme. The refresh's own screen publishes up to
# themes.PUBLISHED_ROWS_PER_GROUP (20) per group; this list is a shortlist of names the
# reader has not seen anywhere else, so it is deliberately shorter than the leaderboard it
# sits beside. Overridable for a one-off wider look without a code change.
PUBLISHED_ROWS_PER_THEME = max(1, int(os.getenv("THEME_PEERS_ROWS_PER_THEME", "10")))
# 0 means "every eligible peer". A cap here bounds EDGAR reads on a first run against a
# universe nothing has scored yet; it is not needed at the measured pool size.
CANDIDATE_LIMIT = max(0, int(os.getenv("THEME_PEERS_CANDIDATE_LIMIT", "0")))


def already_covered(advisor):
    """Tickers the refresh already publishes: the top-``publish_limit`` research rows and
    every configured holding.

    Both are excluded rather than merely deprioritised. The screen this feeds answers "what
    is connected to this theme that I am not already looking at", so a name that is either a
    published leader or something the reader owns is not an answer to it.
    """
    published = {row.get("ticker") for row in advisor.get("research") or () if row.get("ticker")}
    held = {row.get("ticker") for row in advisor.get("portfolio_coverage") or () if row.get("ticker")}
    return published | held


def peer_candidates(themes, advisor, *, limit=CANDIDATE_LIMIT):
    """Every sector peer of a theme's seeds that the refresh is not already publishing.

    Reads ``research`` and ``screen_universe`` together: the screen tail is where the
    unrecognised names live, and scoring only the published rows would reproduce exactly the
    blind spot this job exists to remove. Funds are excluded for the same reason
    ``themes.expand_theme_candidates`` excludes them -- a fund has no place in a supply chain
    and no 10-K to read.

    Returns ``(candidates, per_theme_counts)``; candidates are tagged ``sector_peer`` so
    ``build_theme_screen`` files them under the connected group, not the leaders group.
    """
    rows = (*(advisor.get("research") or ()), *(advisor.get("screen_universe") or ()))
    by_ticker = {row["ticker"]: row for row in rows
                 if row.get("ticker") and not row.get("is_etf")}
    covered = already_covered(advisor)

    candidates, counts = {}, {}
    for theme in themes:
        seed_groups = set()
        for ticker in theme.get("seed_tickers") or ():
            seed_row = by_ticker.get(ticker)
            if seed_row:
                seed_groups.add(peer_group(seed_row)[0])
        if not seed_groups:
            LOG.warn(f"{theme['id']}: no seed ticker resolves to a peer group; skipped")
            counts[theme["id"]] = 0
            continue
        peers = [row for ticker, row in by_ticker.items()
                 if ticker not in covered
                 and peer_group(row)[0] in seed_groups
                 and in_theme_scope(theme, row)]
        counts[theme["id"]] = len(peers)
        for row in peers:
            candidates.setdefault(row["ticker"], {**row, "candidate_source": "sector_peer"})

    if limit and len(candidates) > limit:
        # Strongest first, so a truncated run still evaluates the peers most likely to be
        # worth reading rather than an alphabetical slice.
        keep = sorted(candidates.values(), key=lambda row: row.get("score") or 0,
                      reverse=True)[:limit]
        LOG.info(f"Candidate cap {limit} applied: {len(candidates) - limit} lower-scoring "
                 "peers were not evaluated this run")
        candidates = {row["ticker"]: row for row in keep}
    return candidates, counts


def build(advisor=None):
    advisor = advisor if advisor is not None else (load_json("advisor.json") or {})
    if not advisor.get("research"):
        return empty_screen("advisor.json has no published research rows to draw peers from")
    themes = load_themes()
    if not themes:
        return empty_screen("no active theme definitions in pipeline/themes/")

    candidates, per_theme_pool = peer_candidates(themes, advisor)
    if not candidates:
        return empty_screen("every sector peer is already a published leader or a holding")

    sec = SecEdgarClient()
    provider = EdgarThemeSignals(sec)
    if not provider.available:
        return empty_screen("SEC_USER_AGENT is required by SEC fair-access policy; "
                            "theme signals come from EDGAR filings")

    LOG.info(f"Theme peers: scoring {len(candidates)} sector-connected candidates across "
             f"{len(themes)} themes (leaders and holdings excluded)")
    screen = build_theme_screen(themes, list(candidates.values()), provider,
                                limit_per_group=PUBLISHED_ROWS_PER_THEME)

    screen["schema_version"] = SCHEMA_VERSION
    # The advisor snapshot this was derived from. Two files with two generation times sit
    # beside each other in the UI, and a reader comparing them needs to know which snapshot
    # the peer rows were scored against rather than assuming both are from the same run.
    screen["source"] = {
        "advisor_generated_at": advisor.get("generated_at"),
        "advisor_universe_mode": advisor.get("universe_mode"),
        "advisor_universe_count": advisor.get("universe_count"),
    }
    screen["scope"] = {
        "candidates_scored": len(candidates),
        "excluded_already_published": len(already_covered(advisor)),
        "eligible_peer_pool_by_theme": per_theme_pool,
        "published_rows_per_theme": PUBLISHED_ROWS_PER_THEME,
        "note": "Sector peers of each theme's seed tickers, excluding published research "
                "leaders and portfolio holdings. Scored from the committed advisor snapshot "
                "and SEC EDGAR filings only - this job polls no market data.",
    }
    return screen


def run():
    screen = build()
    save_json(OUTPUT, screen)
    themes = screen.get("themes") or []
    scored = sum(theme.get("count", 0) for theme in themes)
    published = sum(len(theme.get("rows") or []) for theme in themes)
    if screen.get("unavailable_reason"):
        LOG.warn(f"Theme peers unavailable: {screen['unavailable_reason']}")
    else:
        LOG.info(f"Theme peers: {len(themes)} theme(s), {scored} scored exposures, "
                 f"{published} published (top {PUBLISHED_ROWS_PER_THEME} per theme)")
    return screen


if __name__ == "__main__":
    run()
