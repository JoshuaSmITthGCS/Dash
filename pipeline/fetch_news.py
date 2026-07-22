"""
fetch_news.py
Parse RSS feeds, match headlines against policy_map keywords, flag sectors + tickers.
Writes news.json. The 'flagged_sectors' block feeds the scorer's policy-catalyst factor.
"""

import sys
from datetime import datetime, timezone

from common import LOG, load_json, save_json, update_pipeline_status

FEEDS = [
    ("BBC Business", "https://feeds.bbci.co.uk/news/business/rss.xml"),
    ("Yahoo Finance", "https://finance.yahoo.com/news/rssindex"),
    ("MarketWatch", "https://feeds.marketwatch.com/marketwatch/topstories/"),
    ("Politico Politics", "https://rss.politico.com/politics-news.xml"),
    ("Politico Congress", "https://rss.politico.com/congress.xml"),
    ("WSJ Markets", "https://feeds.a.dj.com/rss/RSSMarketsMain.xml"),
]
MIN_HEALTHY_FEEDS = 3


def match_headline(title, summary, policy):
    text = f"{title} {summary}".lower()
    hits = []
    for sector, cfg in policy.get("sectors", {}).items():
        for kw in cfg.get("keywords", []):
            if kw.lower() in text:
                hits.append({"sector": sector, "keyword": kw, "tickers": cfg.get("tickers", [])})
                break
    return hits


def fetch():
    try:
        import feedparser
    except ImportError:
        LOG.error("feedparser not installed. pip install -r requirements.txt")
        return None

    policy = load_json("policy_map.json", from_config=True) or {}
    items = []
    sector_counts = {}
    feed_health = []

    for configured_name, url in FEEDS:
        try:
            feed = feedparser.parse(url)
        except Exception as e:  # noqa: BLE001
            LOG.warn(f"feed failed {url}: {e}")
            feed_health.append({"name": configured_name, "url": url, "status": "error", "entries": 0})
            continue
        entries = list(getattr(feed, "entries", []))
        bozo = bool(getattr(feed, "bozo", False))
        status = getattr(feed, "status", 200)
        healthy = bool(entries) and status < 400
        feed_health.append({"name": configured_name, "url": url,
                            "status": "healthy" if healthy else "error",
                            "http_status": status, "entries": len(entries), "parse_warning": bozo})
        if not healthy:
            LOG.warn(f"feed unhealthy {url}: HTTP {status}, {len(entries)} entries")
            continue
        source = feed.feed.get("title", configured_name) if getattr(feed, "feed", None) else configured_name
        for entry in entries[:40]:
            title = entry.get("title", "")
            summary = entry.get("summary", "")
            hits = match_headline(title, summary, policy)
            if not hits:
                continue
            for h in hits:
                sector_counts[h["sector"]] = sector_counts.get(h["sector"], 0) + 1
            items.append({
                "title": title,
                "source": source,
                "url": entry.get("link", ""),
                "published": entry.get("published", ""),
                "flags": hits,
            })

    healthy_count = sum(h["status"] == "healthy" for h in feed_health)
    if healthy_count < MIN_HEALTHY_FEEDS:
        LOG.error(f"Only {healthy_count}/{len(FEEDS)} news feeds healthy; refusing to replace news.json")
        update_pipeline_status("news", status="error", source="RSS feeds",
                               message="Healthy feed threshold not met", details={"feeds": feed_health})
        return None

    # Which sectors are hot this week -> scorer reads this
    flagged = sorted(sector_counts.items(), key=lambda x: x[1], reverse=True)
    flagged_sectors = {s: c for s, c in flagged}
    flagged_tickers = {}
    for s in flagged_sectors:
        for tk in policy["sectors"][s].get("tickers", []):
            flagged_tickers[tk] = s

    items = items[:60]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_mode": "live",
        "count": len(items),
        "feed_health": feed_health,
        "flagged_sectors": flagged_sectors,
        "flagged_tickers": flagged_tickers,
        "items": items,
    }


def main():
    payload = fetch()
    if payload is None:
        return 1
    save_json("news.json", payload)
    update_pipeline_status("news", status="healthy", source="RSS feeds",
                           details={"healthy_feeds": sum(h["status"] == "healthy" for h in payload["feed_health"]),
                                    "total_feeds": len(payload["feed_health"]), "flagged_items": payload["count"]})
    LOG.info(f"Wrote news.json: {payload['count']} flagged items, "
             f"{len(payload['flagged_sectors'])} hot sectors")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
