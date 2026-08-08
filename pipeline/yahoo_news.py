"""Per-symbol company news from Yahoo, normalized for the event layer.

The catalyst model was complete and had nothing to score: entity-level sentiment was fetched
only for the five Alpha-enriched symbols per refresh, so `news_score` resolved on 3 of 877
rows and the model correctly returned an empty list. Yahoo's own news endpoint is free and
per-symbol, which is the one source that can cover the whole polled universe.

What Yahoo gives is coverage. What it does not give is **sentiment** - there is no polarity
score anywhere in the feed. So direction is derived here, from a deterministic phrase lexicon
over the headline and summary, in exactly the style the event-type and source-quality
classifiers already use (`news_intelligence.classify_event_type`). Three rules keep that
honest:

  * **No marker, no direction.** A headline that matches nothing is still recorded as an
    event - it is real coverage and it counts toward how much is happening - but it carries
    no direction and therefore contributes nothing to the score. Guessing neutral would be a
    fabricated reading; guessing a polarity from tone would be worse.
  * **Strongest marker wins, markers are not summed.** Headlines are short. Summing lets
    three mild words outvote one decisive one, so "cuts full-year guidance" must not be
    diluted by two incidental positives elsewhere in the sentence.
  * **The source of the direction is published.** Every event records whether its direction
    came from a provider sentiment score or from this lexicon, so nobody later mistakes a
    keyword match for a measured sentiment model.

Direction and event type are deliberately separate axes. "Raises FY guidance" and "cuts FY
guidance" are the same event type carrying the same materiality; only the direction
distinguishes them, which is what lets the reversal model's thesis-break gate tell a bounce
after a guidance cut from a bounce after a guidance raise.
"""

from datetime import datetime, timezone

from common import LOG

# Yahoo's own aggregation domain: an article syndicated onto finance.yahoo.com is not an
# independent source, and treating it as one is how coverage volume masquerades as
# corroboration.
YAHOO_AGGREGATOR_DOMAINS = ("finance.yahoo.com", "yahoo.com")


def _text(value):
    return str(value or "").strip()


def _first(*values):
    for value in values:
        text = _text(value)
        if text:
            return text
    return ""


def _parse_epoch(value):
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return None
    if seconds <= 0:
        return None
    try:
        return datetime.fromtimestamp(seconds, tz=timezone.utc).isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def normalize_article(raw, symbol):
    """One Yahoo news item in the shape the event layer reads, or None if unusable.

    Two payload shapes are handled because yfinance has served both: the current nested
    ``{"content": {...}}`` stream item, and the older flat ``{"title", "publisher", "link",
    "providerPublishTime"}`` record. A pipeline that only understands one of them loses the
    entire news leg the day the dependency moves.
    """
    if not isinstance(raw, dict):
        return None
    content = raw.get("content") if isinstance(raw.get("content"), dict) else {}

    title = _first(content.get("title"), raw.get("title"))
    if not title:
        return None

    provider = content.get("provider") if isinstance(content.get("provider"), dict) else {}
    source = _first(provider.get("displayName"), raw.get("publisher"), "Yahoo Finance")

    canonical = content.get("canonicalUrl") if isinstance(content.get("canonicalUrl"), dict) else {}
    click_through = content.get("clickThroughUrl") if isinstance(content.get("clickThroughUrl"), dict) else {}
    url = _first(canonical.get("url"), click_through.get("url"), raw.get("link"), raw.get("url"))

    published_at = _first(content.get("pubDate"), content.get("displayTime"), raw.get("published_at"))
    if not published_at:
        published_at = _parse_epoch(raw.get("providerPublishTime")) or ""

    summary = _first(content.get("summary"), content.get("description"), raw.get("summary"))

    return {
        "title": title,
        "summary": summary,
        "source": source,
        "url": url,
        "published_at": published_at,
        "ticker": str(symbol).upper(),
        "provider_feed": "yahoo_news",
    }


def headline_direction(item, config):
    """Signed polarity in [-1, 1] from the phrase lexicon, or (None, None) when nothing matched.

    Returns ``(direction, matched_phrase)`` so the match is auditable: a direction nobody can
    trace back to the words that produced it is not reviewable, and this one is a keyword
    match rather than a sentiment model - it should be easy to check and easy to disagree with.
    """
    markers = config.get("headline_direction_markers") or {}
    haystack = f"{_text(item.get('title'))} {_text(item.get('summary'))}".lower()
    best_phrase, best_weight = None, 0.0
    for phrase, weight in markers.items():
        if phrase.startswith("_"):
            continue
        if phrase in haystack and abs(weight) > abs(best_weight):
            best_phrase, best_weight = phrase, float(weight)
    if best_phrase is None:
        return None, None
    return max(-1.0, min(1.0, best_weight)), best_phrase


def annotate_direction(articles, config):
    """Attach a derived direction to each article that has no provider sentiment of its own.

    Provider sentiment always wins where it exists (Marketaux/Alpha entity scores are a real
    model over the article body, not a keyword match over its headline), so this only fills
    the gap Yahoo leaves.
    """
    annotated = []
    for article in articles:
        item = dict(article)
        has_provider_score = bool(item.get("ticker_sentiment")) or item.get("overall_sentiment_score") is not None
        if not has_provider_score:
            direction, phrase = headline_direction(item, config)
            if direction is not None:
                item["headline_direction"] = direction
                item["headline_direction_marker"] = phrase
        annotated.append(item)
    return annotated


def is_aggregator(article):
    haystack = f"{_text(article.get('source'))} {_text(article.get('url'))}".lower()
    return any(domain in haystack for domain in YAHOO_AGGREGATOR_DOMAINS)


def new_diagnostics():
    return {"symbols_requested": 0, "symbols_with_news": 0, "feed_failures": 0,
            "items_received": 0, "items_normalized": 0}


def fetch_company_news(symbol, ticker_obj, config, *, count=None, cache=None, tab="news",
                       diagnostics=None):
    """Yahoo's per-symbol news, normalized, direction-annotated, newest first.

    Cached under the existing ``news`` namespace (30-minute TTL): a fast refresh polling the
    same leaders every few minutes must not re-request the same headlines each time, and news
    that is half an hour stale changes no decision this layer makes.

    ``diagnostics`` accumulates received-versus-normalized counts across the run, and it is
    not optional bookkeeping. yfinance passes Yahoo's stream items through untouched, so this
    module is parsing an undocumented third-party shape that can change without notice. If it
    does change, every item fails to normalize and the news leg goes quiet - which is exactly
    how the Form 4 layer once reported itself healthy while scoring zero transactions for the
    entire universe. Counting both sides makes that failure visible as "received 2,400 items
    and could read none of them" instead of "no news happened".
    """
    if ticker_obj is None:
        return []
    limit = int(count or config.get("yahoo_news_count", 20))
    if diagnostics is not None:
        diagnostics["symbols_requested"] += 1

    def produce():
        # Inside the producer, not around the whole call: a cache hit costs Yahoo nothing and
        # must not consume a slot. This adds one request per polled symbol - up to ~900 on a
        # full sweep - to a provider that publishes no rate limit and is already being paced
        # at 4/s, so skipping the shared limiter here would quietly undo that pacing.
        from cache import limiter_for  # local import keeps this module standalone-usable

        limiter_for("yahoo").acquire()
        return ticker_obj.get_news(count=limit, tab=tab) or []

    try:
        raw = cache.fetch("news", f"yahoo:{symbol}:{tab}:{limit}", produce, source="yahoo_news") \
            if cache else produce()
    except Exception as exc:  # noqa: BLE001 - a dark news feed must not sink the company
        LOG.warn(f"{symbol}: Yahoo news unavailable ({type(exc).__name__})")
        if diagnostics is not None:
            diagnostics["feed_failures"] += 1
        return []

    raw = raw or []
    articles = [article for article in (normalize_article(item, symbol) for item in raw) if article]
    if diagnostics is not None:
        diagnostics["items_received"] += len(raw)
        diagnostics["items_normalized"] += len(articles)
        diagnostics["symbols_with_news"] += 1 if articles else 0
    if raw and not articles:
        LOG.warn(f"{symbol}: {len(raw)} Yahoo news items received, none in a readable shape")
    return annotate_direction(articles, config)
