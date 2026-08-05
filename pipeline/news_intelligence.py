"""Deterministic article filtering, novelty, and weighting for research sentiment."""

import math
import re
from datetime import datetime, timezone
from difflib import SequenceMatcher


def parse_published_at(value):
    """Parse either Alpha Vantage compact timestamps or provider ISO timestamps."""
    if not value:
        return None
    text = str(value)
    for parse in (
        lambda stamp: datetime.strptime(stamp[:15], "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc),
        lambda stamp: datetime.fromisoformat(stamp.replace("Z", "+00:00")),
    ):
        try:
            parsed = parse(text)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            continue
    return None


def normalized_title(value):
    """Normalize punctuation and publisher suffixes before syndicated-story comparison."""
    text = str(value or "").lower()
    text = re.sub(r"\s+[|:\-]\s+[^|:\-]+$", "", text)
    return " ".join(re.findall(r"[a-z0-9]+", text))


def title_similarity(left, right):
    left_title = normalized_title(left)
    right_title = normalized_title(right)
    if not left_title or not right_title:
        return 0.0
    return SequenceMatcher(None, left_title, right_title).ratio()


def deduplicate_articles(items, threshold):
    """Keep the newest copy of each story for each primary ticker."""
    ordered = sorted(items, key=lambda item: item.get("published_at") or "", reverse=True)
    kept = []
    identities = set()
    for item in ordered:
        ticker = str(item.get("ticker") or "").upper()
        url = str(item.get("url") or "").strip().lower()
        title = normalized_title(item.get("title"))
        exact_identity = (ticker, url) if url else (ticker, title)
        if exact_identity in identities:
            continue
        if title and any(
            str(existing.get("ticker") or "").upper() == ticker
            and title_similarity(title, existing.get("title")) >= threshold
            for existing in kept
        ):
            continue
        identities.add(exact_identity)
        kept.append(item)
    return kept


def content_type(item, config):
    haystack = " ".join(str(item.get(key) or "") for key in ("source", "url", "title")).lower()
    return "filing" if any(marker.lower() in haystack for marker in config["filing_markers"]) else "commentary"


def source_quality(item, config):
    haystack = " ".join(str(item.get(key) or "") for key in ("source", "url")).lower()
    tiers = config["source_quality"]
    for tier_name in config["source_quality_tier_order"]:
        tier = tiers[tier_name]
        if any(marker.lower() in haystack for marker in tier["matches"]):
            return tier_name, float(tier["weight"])
    default = tiers[config["source_quality_default_tier"]]
    return config["source_quality_default_tier"], float(default["weight"])


def annotate_article(item, config):
    tier, quality_weight = source_quality(item, config)
    kind = content_type(item, config)
    return {
        **item,
        "content_type": kind,
        "source_quality_tier": tier,
        "source_quality_weight": quality_weight,
    }


def _entity_signal(item, ticker, config):
    for entity in item.get("ticker_sentiment", []):
        if str(entity.get("ticker") or "").upper() != ticker.upper():
            continue
        try:
            score = float(entity.get("ticker_sentiment_score"))
        except (TypeError, ValueError):
            continue
        raw_confidence = entity.get("relevance_score", item.get("entity_confidence"))
        try:
            confidence = float(raw_confidence)
        except (TypeError, ValueError):
            confidence = float(config["entity_confidence_default"])
        if confidence > config["entity_confidence_fraction_max"]:
            confidence /= config["entity_confidence_percent_divisor"]
        return score, max(0.0, min(1.0, confidence))
    return None, None


def weighted_sentiment(news_items, ticker, config, *, now=None):
    """Return a weighted 0 to 100 score and an auditable aggregation detail block."""
    now = now or datetime.now(timezone.utc)
    eligible = []
    outside_window = 0
    low_confidence = 0
    for raw in news_items:
        published = parse_published_at(raw.get("published_at"))
        if published and published < now - config["window_delta"]:
            outside_window += 1
            continue
        score, confidence = _entity_signal(raw, ticker, config)
        if score is None or confidence is None:
            continue
        if confidence < config["entity_confidence_minimum"]:
            low_confidence += 1
            continue
        eligible.append({**annotate_article(raw, config), "_sentiment": score,
                         "entity_confidence": confidence, "_published": published})

    unique = deduplicate_articles(eligible, config["title_similarity_threshold"])
    articles = []
    weighted_total = 0.0
    total_weight = 0.0
    for item in unique:
        published = item.pop("_published")
        if published:
            age_days = max(0.0, (now - published).total_seconds() / config["seconds_per_day"])
            recency_weight = math.exp(-math.log(2) * age_days / config["recency_half_life_days"])
        else:
            age_days = None
            recency_weight = config["undated_recency_weight"]
        kind_weight = config["content_type_weights"][item["content_type"]]
        weight = recency_weight * item["source_quality_weight"] * kind_weight * item["entity_confidence"]
        weighted_total += item["_sentiment"] * weight
        total_weight += weight
        articles.append({
            "title": item.get("title"),
            "source": item.get("source"),
            "published_at": item.get("published_at"),
            "content_type": item["content_type"],
            "source_quality_tier": item["source_quality_tier"],
            "entity_confidence": round(item["entity_confidence"], 3),
            "recency_weight": round(recency_weight, 4),
            "composite_weight": round(weight, 4),
            "age_days": round(age_days, 2) if age_days is not None else None,
        })

    if not articles or total_weight <= 0:
        return float(config["neutral_score"]), {
            "article_count": 0,
            "raw_article_count": len(news_items),
            "average": None,
            "weighted_average": None,
            "coverage": 0.0,
            "window_days": config["window_days"],
            "full_coverage_article_count": config["full_coverage_article_count"],
            "discarded_low_confidence": low_confidence,
            "discarded_outside_window": outside_window,
            "syndicated_copies_removed": max(0, len(eligible) - len(unique)),
            "articles": [],
            "weighting_method": "recency_source_filing_entity_novelty",
        }

    average = weighted_total / total_weight
    score = max(config["score_minimum"], min(config["score_maximum"],
                config["neutral_score"] + average * config["sentiment_score_scale"]))
    return round(score, 1), {
        "article_count": len(articles),
        "raw_article_count": len(news_items),
        "average": round(average, 3),
        "weighted_average": round(average, 3),
        "coverage": min(1.0, len(articles) / config["full_coverage_article_count"]),
        "window_days": config["window_days"],
        "recency_half_life_days": config["recency_half_life_days"],
        "full_coverage_article_count": config["full_coverage_article_count"],
        "discarded_low_confidence": low_confidence,
        "discarded_outside_window": outside_window,
        "syndicated_copies_removed": max(0, len(eligible) - len(unique)),
        "filing_count": sum(item["content_type"] == "filing" for item in articles),
        "commentary_count": sum(item["content_type"] == "commentary" for item in articles),
        "articles": articles,
        "weighting_method": "recency_source_filing_entity_novelty",
    }
