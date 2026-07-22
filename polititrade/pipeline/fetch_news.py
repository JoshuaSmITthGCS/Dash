"""
fetch_news.py
Parse RSS feeds, match headlines against policy_map keywords, flag sectors + tickers.
Writes news.json. The 'flagged_sectors' block feeds the scorer's policy-catalyst factor.
"""

from datetime import datetime, timezone

from common import LOG, load_json, save_json

FEEDS = [
    "https://feeds.reuters.com/reuters/businessNews",
    "https://finance.yahoo.com/news/rssindex",
    "https://feeds.marketwatch.com/marketwatch/topstories/",
    "https://www.politico.com/rss/politics08.xml",
    "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
]


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

    for url in FEEDS:
        try:
            feed = feedparser.parse(url)
        except Exception as e:  # noqa: BLE001
            LOG.warn(f"feed failed {url}: {e}")
            continue
        source = feed.feed.get("title", url) if getattr(feed, "feed", None) else url
        for entry in feed.entries[:40]:
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

    # Which sectors are hot this week -> scorer reads this
    flagged = sorted(sector_counts.items(), key=lambda x: x[1], reverse=True)
    flagged_sectors = {s: c for s, c in flagged}
    flagged_tickers = {}
    for s in flagged_sectors:
        for tk in policy["sectors"][s].get("tickers", []):
            flagged_tickers[tk] = s

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(items),
        "flagged_sectors": flagged_sectors,
        "flagged_tickers": flagged_tickers,
        "items": items[:60],
    }


def main():
    payload = fetch()
    if payload is None:
        return
    save_json("news.json", payload)
    LOG.info(f"Wrote news.json: {payload['count']} flagged items, "
             f"{len(payload['flagged_sectors'])} hot sectors")


if __name__ == "__main__":
    main()
