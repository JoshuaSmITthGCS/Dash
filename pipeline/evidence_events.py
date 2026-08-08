"""Dated evidence events with per-event recency decay.

The layer this replaces produced two static numbers per company - a news sentiment score and
an insider points total - and every consumer had to treat them as equally current. That is
wrong in both directions. A guidance raise published yesterday and a "great workplace" award
from five weeks ago collapsed into the same average; an insider purchase decayed on the same
schedule as a headline even though the documented insider effect accrues over one to three
months, not one to three days.

So evidence is modelled here as *events*, each carrying its own timestamp, and each decaying
on a half-life chosen for what kind of event it is:

    strength = direction x materiality x source_quality x novelty x 2^(-age / half_life)

Three rules the implementation is built around.

**One event, not ten articles.** When Reuters reports an earnings beat and six aggregators
rewrite it, that is one event with seven articles, not seven catalysts. Clustering happens
before scoring, so the most-covered company does not automatically win the catalyst screen.
The cluster keeps the earliest timestamp (when the information actually reached the market)
and the best available source.

**Materiality outranks sentiment.** "Recognized as a great workplace" can score +0.95 on
sentiment and still be worth almost nothing; "raises FY EPS guidance 18%" can score +0.75 and
be worth everything. The event-type taxonomy carries a materiality weight, and it multiplies.

**Different horizons for different evidence.** News half-lives run 1-10 trading days by event
type. Insider purchases decay far more slowly - 30 trading days for the short-term catalyst
view and 60 for the long-term one - because that is the horizon the effect is documented over
(Cohen, Malloy & Pomorski 2012), not because a purchase stops being interesting on day four.

Everything here is pure: events in, scored events out, no network and no clock except the
``now``/``as_of`` the caller passes. Weights are priors to be validated against the
point-in-time store, not measured constants - they live in config for that reason.
"""

import math
from datetime import datetime, timezone

from news_intelligence import (annotate_article, normalized_title, parse_published_at,
                               title_similarity)

# Trading days, not calendar days: an event that lands on Friday should not have burned two
# half-lives by Monday morning when the market has not had a session to react.
CALENDAR_TO_TRADING_DAYS = 7.0 / 5.0


def _finite(value):
    return isinstance(value, (int, float)) and math.isfinite(value)


def decay_weight(age_trading_days, half_life_trading_days):
    """2^(-age/half_life), floored at zero. An undated event gets no decay credit at all."""
    if age_trading_days is None or half_life_trading_days in (None, 0):
        return 0.0
    if age_trading_days <= 0:
        return 1.0
    return 2.0 ** (-age_trading_days / float(half_life_trading_days))


def trading_days_between(published, now):
    if published is None or now is None:
        return None
    calendar_days = max(0.0, (now - published).total_seconds() / 86400.0)
    return calendar_days / CALENDAR_TO_TRADING_DAYS


def event_materiality(event_types, config):
    """The highest materiality among the types a headline matched.

    Highest rather than average: "CFO resigns amid SEC investigation" is both a management
    item and a regulatory one, and the regulatory reading is the one that moves a price. An
    unclassified headline falls back to the routine-commentary weight, which is deliberately
    low - it is ordinary coverage until something identifies it otherwise.
    """
    weights = config["event_materiality"]
    matched = [weights[kind] for kind in event_types or [] if kind in weights]
    return max(matched) if matched else weights["routine_commentary"]


def event_half_life(event_types, config):
    """Longest half-life among the matched types; routine commentary when nothing matched.

    Longest, because the slowest-resolving element of a story is what keeps it live: an
    acquisition rumour attached to an earnings report stays relevant well past the earnings
    number itself.
    """
    half_lives = config["event_half_life_trading_days"]
    matched = [half_lives[kind] for kind in event_types or [] if kind in half_lives]
    return max(matched) if matched else half_lives["routine_commentary"]


def cluster_articles(articles, config):
    """Group syndicated retellings of one story into a single event.

    Two articles belong to the same event when their normalized titles are similar enough
    (the same threshold the sentiment path already uses for de-duplication) and they were
    published within the clustering window of each other. The cluster reports the *earliest*
    publication as the event time - that is when the information reached the market - and the
    highest-quality source seen, so a Reuters original is not represented by the Benzinga
    rewrite that happened to arrive first in the feed.
    """
    threshold = config["cluster_title_similarity"]
    window_hours = config["cluster_window_hours"]
    clusters = []
    ordered = sorted(articles, key=lambda item: item.get("_published") or datetime.max.replace(tzinfo=timezone.utc))
    for article in ordered:
        published = article.get("_published")
        title = normalized_title(article.get("title"))
        target = None
        for cluster in clusters:
            if title_similarity(title, cluster["_title"]) < threshold:
                continue
            if published and cluster["_published"]:
                hours_apart = abs((published - cluster["_published"]).total_seconds()) / 3600.0
                if hours_apart > window_hours:
                    continue
            target = cluster
            break
        if target is None:
            clusters.append({
                "_title": title,
                "_published": published,
                "title": article.get("title"),
                "articles": [article],
            })
            continue
        target["articles"].append(article)
        if published and (target["_published"] is None or published < target["_published"]):
            target["_published"] = published
            target["title"] = article.get("title")
    return clusters


def _best_source(articles, config):
    order = config["source_quality_tier_order"] + [config["source_quality_default_tier"]]
    tiers = {article.get("source_quality_tier") for article in articles}
    for tier in order:
        if tier in tiers:
            best = next(a for a in articles if a.get("source_quality_tier") == tier)
            return tier, float(best.get("source_quality_weight") or 1.0), best.get("source")
    return None, 1.0, None


def _article_direction(article, ticker):
    """Signed sentiment in [-1, 1] for this ticker, or None when the provider gave none."""
    for entity in article.get("ticker_sentiment") or []:
        if str(entity.get("ticker") or "").upper() != str(ticker).upper():
            continue
        try:
            return max(-1.0, min(1.0, float(entity.get("ticker_sentiment_score"))))
        except (TypeError, ValueError):
            return None
    try:
        return max(-1.0, min(1.0, float(article.get("overall_sentiment_score"))))
    except (TypeError, ValueError):
        return None


def build_news_events(articles, ticker, config, *, now=None):
    """Cluster, classify, and decay a company's news into scored events, newest first."""
    now = now or datetime.now(timezone.utc)
    annotated = []
    for raw in articles or []:
        item = annotate_article(raw, config)
        item["_published"] = parse_published_at(raw.get("published_at") or raw.get("published"))
        annotated.append(item)

    events = []
    for cluster in cluster_articles(annotated, config):
        members = cluster["articles"]
        event_types = sorted({kind for article in members for kind in article.get("event_types") or []})
        materiality = event_materiality(event_types, config)
        half_life = event_half_life(event_types, config)
        published = cluster["_published"]
        age = trading_days_between(published, now)
        recency = decay_weight(age, half_life)
        tier, quality_weight, source = _best_source(members, config)
        directions = [d for d in (_article_direction(a, ticker) for a in members) if d is not None]
        direction = sum(directions) / len(directions) if directions else None
        # Independent corroboration, not repetition: distinct sources carrying the same story
        # is mild evidence it is real, capped so volume cannot substitute for materiality.
        distinct_sources = len({str(a.get("source") or "").lower() for a in members if a.get("source")})
        breadth = min(config["max_source_breadth_bonus"],
                      1.0 + config["source_breadth_step"] * max(0, distinct_sources - 1))
        strength = None
        if direction is not None:
            strength = direction * materiality * quality_weight * breadth * recency

        events.append({
            "title": cluster["title"],
            "event_types": event_types or ["routine_commentary"],
            "published_at": published.isoformat() if published else None,
            "age_trading_days": round(age, 2) if age is not None else None,
            "half_life_trading_days": half_life,
            "materiality": materiality,
            "direction": round(direction, 3) if direction is not None else None,
            "source_quality_tier": tier,
            "best_source": source,
            "article_count": len(members),
            "distinct_sources": distinct_sources,
            "recency_weight": round(recency, 4),
            "strength": round(strength, 4) if strength is not None else None,
        })
    events.sort(key=lambda event: (event["published_at"] or ""), reverse=True)
    return events


def news_event_score(events, config):
    """Blend scored events into one 0-100 reading, or None when nothing is scorable.

    Decayed strength is the weight as well as the value, so a fresh material event dominates
    a stale trivial one instead of being averaged down by it. None (not 50) when no event
    carries a direction: an absence of evidence is not a neutral reading, and returning the
    neutral score here is what previously made hundreds of uncovered names look as though
    they had been checked and found unremarkable.
    """
    scorable = [event for event in events if event.get("strength") is not None]
    if not scorable:
        return None, {"available": False, "reason": "no directional news event in the window",
                      "event_count": 0}
    net = sum(event["strength"] for event in scorable)
    if all(abs(event["strength"]) < 1e-9 for event in scorable):
        return None, {"available": False, "reason": "every news event has fully decayed",
                      "event_count": len(scorable)}
    # Saturating sum, not a weighted average of direction. Averaging divides materiality
    # straight back out: a lone "great workplace" award at +0.95 sentiment would land at the
    # same 100 as a guidance raise, because the average of one number is that number however
    # trivial it is. Summing the signed strengths keeps materiality in the magnitude, and
    # tanh bounds the result so a company with heavy coverage cannot run away with the screen.
    score = config["neutral_score"] + 50.0 * math.tanh(net / config["news_saturation"])
    score = max(0.0, min(100.0, score))
    strongest = max(scorable, key=lambda event: abs(event["strength"]))
    return round(score, 1), {
        "available": True,
        "event_count": len(events),
        "scored_event_count": len(scorable),
        "net_strength": round(net, 4),
        "dominant_event": strongest["title"],
        "dominant_event_types": strongest["event_types"],
        "dominant_age_trading_days": strongest["age_trading_days"],
        "dominant_materiality": strongest["materiality"],
        "method": "clustered events, materiality-weighted, per-event-type half-life decay",
    }


# ---------------- insider events ----------------

def build_insider_events(insider_activity, config, *, horizon="catalyst"):
    """Re-decay an already-classified Form 4 summary onto the requested horizon.

    ``insider_signal.summarize`` does the hard part - routine versus opportunistic, cluster
    breadth, pattern confidence. What it cannot do is know which question is being asked: the
    catalyst screen wants "is someone buying right now", the long-term view wants "has
    management been accumulating this year". Same underlying trades, different half-life.
    """
    activity = insider_activity or {}
    if not activity.get("available"):
        return []
    half_life = config["insider_half_life_trading_days"][horizon]
    events = []
    for side, cluster_key, sign in (("purchase", "buy_cluster", 1.0), ("sale", "sell_cluster", -1.0)):
        cluster = activity.get(cluster_key) or {}
        insider_count = cluster.get("insider_count") or 0
        if not insider_count:
            continue
        days_since = cluster.get("days_since_latest")
        age = None if days_since is None else days_since / CALENDAR_TO_TRADING_DAYS
        recency = decay_weight(age, half_life)
        breadth = min(1.0, 0.5 + 0.25 * (insider_count - 1))
        # Sells are noisier: insiders sell for diversification, tax and houses, and buy for
        # one reason. The asymmetry is applied here rather than baked into the cluster.
        side_weight = 1.0 if sign > 0 else config["insider_sell_weight"]
        confidence = cluster.get("pattern_confidence")
        confidence = confidence if _finite(confidence) else 1.0
        events.append({
            "side": side,
            "insider_count": insider_count,
            "total_value": cluster.get("total_value"),
            "days_since_latest": days_since,
            "age_trading_days": round(age, 2) if age is not None else None,
            "half_life_trading_days": half_life,
            "horizon": horizon,
            "recency_weight": round(recency, 4),
            "strength": round(sign * breadth * side_weight * confidence * recency, 4),
        })
    return events


def insider_event_score(events, config):
    """0-100 from decayed insider events, or None when there is no open-market activity."""
    if not events:
        return None, {"available": False, "reason": "no open-market Form 4 cluster"}
    net = sum(event["strength"] for event in events)
    score = max(0.0, min(100.0,
                config["neutral_score"] + 50.0 * math.tanh(net / config["insider_saturation"])))
    freshest = min((event for event in events if event["age_trading_days"] is not None),
                   key=lambda event: event["age_trading_days"], default=None)
    return round(score, 1), {
        "available": True,
        "net_strength": round(net, 4),
        "buy_events": sum(1 for event in events if event["side"] == "purchase"),
        "sell_events": sum(1 for event in events if event["side"] == "sale"),
        "freshest_age_trading_days": freshest["age_trading_days"] if freshest else None,
        "method": f"decayed Form 4 clusters, {events[0]['half_life_trading_days']}-trading-day half-life",
    }


# ---------------- expectation change ----------------

def build_expectation_change(row, config):
    """How fast professional expectations are moving, and in which direction.

    This is the leg the catalyst and analyst-conviction models were missing entirely. The
    question is not "do analysts like it" - a static consensus is already in the price - but
    "has the expected number changed recently", which is what tends to still be repricing.

    Every input is optional and the weights renormalize over whatever resolved, so a company
    with revisions but no upgrade history still scores, and one with neither returns None
    rather than a fabricated neutral.
    """
    estimates = row.get("estimate_detail") or {}
    signals = []
    detail = {}

    breadth = estimates.get("revision_breadth_30d")
    if _finite(breadth):
        # Already a -1..1 net-up ratio.
        signals.append((config["neutral_score"] + breadth * 50.0, config["expectation_weights"]["revision_breadth"]))
        detail["revision_breadth_30d"] = breadth

    magnitude = estimates.get("eps_revision_30d_pct")
    if _finite(magnitude):
        signals.append((max(0.0, min(100.0, config["neutral_score"] + magnitude * config["eps_revision_scale"])),
                        config["expectation_weights"]["revision_magnitude"]))
        detail["eps_revision_30d_pct"] = magnitude

    grades = estimates.get("net_upgrades_90d")
    if _finite(grades):
        signals.append((max(0.0, min(100.0, config["neutral_score"] + grades * config["upgrade_scale"])),
                        config["expectation_weights"]["upgrades"]))
        detail["net_upgrades_90d"] = grades

    target_change = estimates.get("target_change_30d_pct")
    if _finite(target_change):
        signals.append((max(0.0, min(100.0, config["neutral_score"] + target_change * config["target_change_scale"])),
                        config["expectation_weights"]["target_change"]))
        detail["target_change_30d_pct"] = target_change

    if not signals:
        return None, {"available": False, "reason": "no estimate revision or rating-change history"}
    total_weight = sum(weight for _, weight in signals)
    score = sum(value * weight for value, weight in signals) / total_weight
    return round(max(0.0, min(100.0, score)), 1), {
        "available": True,
        "inputs_resolved": len(signals),
        "coverage": round(total_weight, 3),
        **detail,
        "method": "revision breadth and magnitude, rating changes, and consensus target drift",
    }


def build_evidence(row, articles, config, *, now=None):
    """The complete evidence block published on a research row.

    Insider events are built twice on purpose - once on the catalyst horizon and once on the
    long-term one - so a consumer never has to guess which decay a published number used.
    """
    events = build_news_events(articles, row.get("ticker"), config, now=now)
    news_score, news_detail = news_event_score(events, config)
    catalyst_insider = build_insider_events(row.get("insider_activity"), config, horizon="catalyst")
    longterm_insider = build_insider_events(row.get("insider_activity"), config, horizon="long_term")
    insider_score, insider_detail = insider_event_score(catalyst_insider, config)
    longterm_insider_score, _ = insider_event_score(longterm_insider, config)
    expectation_score, expectation_detail = build_expectation_change(row, config)
    return {
        "news_events": events[:config["published_event_limit"]],
        "news_score": news_score,
        "news_detail": news_detail,
        "insider_events": catalyst_insider,
        "insider_score": insider_score,
        "insider_score_long_term": longterm_insider_score,
        "insider_detail": insider_detail,
        "expectation_score": expectation_score,
        "expectation_detail": expectation_detail,
    }
