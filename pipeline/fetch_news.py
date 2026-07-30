"""Fetch financial news, flag policy sectors and tickers, and write news.json.

Marketaux is the primary provider when MARKETAUX_API_TOKEN is configured. The
existing RSS collection remains a no-key fallback.
"""

import os
import sys
from datetime import datetime, timezone

from alpha_vantage import load_local_env
from common import LOG, load_json, save_json, update_pipeline_status
from marketaux import MarketauxClient, MarketauxError

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


def match_entities(entities, policy, existing=()):
    """Add policy flags when Marketaux identifies a configured ticker."""
    hits = list(existing)
    existing_sectors = {hit["sector"] for hit in hits}
    symbols = {str(entity.get("symbol", "")).upper() for entity in entities}
    for sector, cfg in policy.get("sectors", {}).items():
        configured = [ticker for ticker in cfg.get("tickers", []) if ticker.upper() in symbols]
        if configured and sector not in existing_sectors:
            hits.append({"sector": sector, "keyword": "entity match", "tickers": configured})
    return hits


def build_payload(items, feed_health, policy, source):
    sector_counts = {}
    for item in items:
        for hit in item["flags"]:
            sector_counts[hit["sector"]] = sector_counts.get(hit["sector"], 0) + 1

    flagged = sorted(sector_counts.items(), key=lambda value: value[1], reverse=True)
    flagged_sectors = dict(flagged)
    flagged_tickers = {}
    for sector in flagged_sectors:
        for ticker in policy.get("sectors", {}).get(sector, {}).get("tickers", []):
            flagged_tickers[ticker] = sector

    items = items[:60]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_mode": "live",
        "count": len(items),
        "feed_health": feed_health,
        "flagged_sectors": flagged_sectors,
        "flagged_tickers": flagged_tickers,
        "items": items,
        "provider": source,
    }


def fetch_marketaux(policy):
    client = MarketauxClient()
    limit = max(1, int(os.getenv("MARKETAUX_NEWS_LIMIT", "50")))
    symbols = sorted({
        ticker.upper()
        for config in policy.get("sectors", {}).values()
        for ticker in config.get("tickers", [])
    })
    payload = client.news(
        symbols=",".join(symbols) or None,
        language="en",
        must_have_entities="true",
        filter_entities="true",
        group_similar="true",
        limit=limit,
    )
    articles = payload.get("data", [])
    items = []
    for article in articles:
        summary = article.get("description") or article.get("snippet") or ""
        hits = match_headline(article.get("title", ""), summary, policy)
        hits = match_entities(article.get("entities", []), policy, hits)
        if not hits:
            continue
        items.append({
            "title": article.get("title") or "Untitled article",
            "source": article.get("source") or "Marketaux",
            "url": article.get("url") or "",
            "published": article.get("published_at") or "",
            "summary": summary,
            "image_url": article.get("image_url"),
            "entities": article.get("entities", []),
            "flags": hits,
        })
    feed_health = [{
        "name": "Marketaux",
        "url": "https://api.marketaux.com/v1/news/all",
        "status": "healthy",
        "entries": len(articles),
    }]
    return build_payload(items, feed_health, policy, "Marketaux")


def fetch_rss(policy):
    try:
        import feedparser
    except ImportError:
        LOG.error("feedparser not installed. pip install -r requirements.txt")
        return None

    items = []
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

    return build_payload(items, feed_health, policy, "RSS feeds")


def fetch():
    load_local_env()
    policy = load_json("policy_map.json", from_config=True) or {}
    if os.getenv("MARKETAUX_API_TOKEN"):
        try:
            return fetch_marketaux(policy)
        except (MarketauxError, OSError, ValueError) as exc:
            LOG.warn(f"Marketaux unavailable; falling back to RSS ({type(exc).__name__}: {exc})")
    return fetch_rss(policy)


def main():
    payload = fetch()
    if payload is None:
        return 1
    save_json("news.json", payload)
    update_pipeline_status(
        "news",
        status="healthy",
        source=payload["provider"],
        details={
            "healthy_feeds": sum(h["status"] == "healthy" for h in payload["feed_health"]),
            "total_feeds": len(payload["feed_health"]),
            "flagged_items": payload["count"],
        },
    )
    LOG.info(f"Wrote news.json: {payload['count']} flagged items, "
             f"{len(payload['flagged_sectors'])} hot sectors")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
