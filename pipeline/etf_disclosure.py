"""Rule 6c-11 ETF disclosure: NAV premium/discount and median 30-day bid-ask spread.

Expense ratio is not the cost of owning an ETF. It is the cost the issuer charges. The two
other components - what you pay above NAV to get in, and how far the fund's return drifts
from the index it claims to track - are both legally required to be published for free.

SEC Rule 6c-11 (the "ETF Rule", compliance date 23 December 2019) requires every ETF
relying on it to post, on a freely accessible public website:

  * the prior business day's NAV, market closing price (or midpoint of the NBBO), and the
    resulting premium or discount;
  * a table and line graph of the number of days the fund traded at a premium or a discount
    for the most recently completed calendar year and each completed quarter since;
  * the fund's **median bid-ask spread over the most recent 30 calendar days**, computed
    from the NBBO midpoint.

That last one is the number the previous model was estimating from a single stale
bid/ask quote. The official figure is better in every way and costs nothing.

Design: parsing is pure and unit-tested; fetching is a thin, pluggable adapter layer.
Issuer sites do not share a format, so rather than pretend one scraper fits all, the
per-fund disclosure endpoint is declared in ``config/universe.json`` and parsed by whichever
adapter its ``format`` names. A fund with no configured endpoint falls back to computing
the premium/discount from the quote payload's NAV, and says so in ``source``.
"""

from statistics import median

from cache import CACHE, cached_json

SOURCE_RULE_6C11 = "issuer Rule 6c-11 disclosure"
SOURCE_QUOTE_NAV = "quote NAV vs market price"


def premium_discount_pct(market_price, nav):
    """Percent premium (positive) or discount (negative) of market price to NAV."""
    if not market_price or not nav or nav <= 0:
        return None
    return round((market_price / nav - 1) * 100, 4)


def spread_pct_from_quote(bid, ask):
    """Bid-ask spread as a percent of the midpoint. The fallback when 6c-11 data is absent."""
    if not bid or not ask or ask < bid or bid <= 0:
        return None
    midpoint = (bid + ask) / 2
    return round((ask - bid) / midpoint * 100, 4) if midpoint else None


def median_spread(spreads):
    """Median of a 30-day spread series, matching the statistic 6c-11 mandates."""
    values = [value for value in spreads if isinstance(value, (int, float))]
    return round(median(values), 4) if values else None


def premium_discount_days(series):
    """Split a premium/discount series into days at a premium, at a discount, and flat.

    Mirrors the table 6c-11 requires. The distribution says more than the latest reading:
    a fund that closes at a discount most days has a structural creation/redemption problem,
    not a one-day anomaly.
    """
    values = [value for value in (series or []) if isinstance(value, (int, float))]
    if not values:
        return None
    premium = sum(1 for value in values if value > 0)
    discount = sum(1 for value in values if value < 0)
    return {
        "days": len(values),
        "days_at_premium": premium,
        "days_at_discount": discount,
        "days_at_nav": len(values) - premium - discount,
        "median_premium_discount_pct": round(median(values), 4),
        "worst_discount_pct": round(min(values), 4),
        "worst_premium_pct": round(max(values), 4),
    }


# ---------------- parsers, one per published shape ----------------

def parse_generic_json(payload, mapping=None):
    """Normalize an issuer JSON payload using a configured field mapping.

    Issuers publish the same three legally-required numbers under entirely different keys.
    Rather than a scraper per issuer, the config names which key holds which value; this
    parser applies that mapping and validates the result.
    """
    if not isinstance(payload, dict):
        return {}
    mapping = mapping or {}
    keys = {
        "nav": mapping.get("nav", "nav"),
        "market_price": mapping.get("market_price", "marketPrice"),
        "premium_discount_pct": mapping.get("premium_discount_pct", "premiumDiscount"),
        "median_bid_ask_spread_pct": mapping.get("median_bid_ask_spread_pct", "medianBidAskSpread"),
        "as_of": mapping.get("as_of", "asOf"),
    }

    def number(key):
        value = payload.get(keys[key])
        try:
            return round(float(value), 6)
        except (TypeError, ValueError):
            return None

    nav, market_price = number("nav"), number("market_price")
    premium = number("premium_discount_pct")
    if premium is None:
        premium = premium_discount_pct(market_price, nav)
    return {
        "nav": nav,
        "market_price": market_price,
        "premium_discount_pct": premium,
        "median_bid_ask_spread_pct": number("median_bid_ask_spread_pct"),
        "as_of": payload.get(keys["as_of"]),
        "source": SOURCE_RULE_6C11,
    }


def parse_premium_discount_series(payload, *, value_key="premiumDiscount", rows_key="items"):
    """Pull the historical premium/discount series out of an issuer payload."""
    rows = payload.get(rows_key) if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        return []
    series = []
    for row in rows:
        value = row.get(value_key) if isinstance(row, dict) else row
        try:
            series.append(float(value))
        except (TypeError, ValueError):
            continue
    return series


PARSERS = {"generic_json": parse_generic_json}


# ---------------- adapters ----------------

def from_quote(snapshot):
    """Premium/discount derived from a quote payload's NAV, with a one-quote spread.

    Strictly worse than the issuer disclosure - one moment's spread is not a 30-day median -
    but it is available for every fund with no configuration at all, and it is labelled so
    nobody mistakes it for the official figure.
    """
    snapshot = snapshot or {}
    nav = snapshot.get("nav") or snapshot.get("nav_price")
    price = snapshot.get("price")
    return {
        "nav": nav,
        "market_price": price,
        "premium_discount_pct": premium_discount_pct(price, nav),
        "median_bid_ask_spread_pct": None,
        "quoted_bid_ask_spread_pct": spread_pct_from_quote(snapshot.get("bid"), snapshot.get("ask")),
        "as_of": None,
        "source": SOURCE_QUOTE_NAV,
    }


def fetch_disclosure(ticker, meta, *, snapshot=None, cache=None):
    """Best available 6c-11 record for one fund, falling back to the quote payload.

    ``meta`` is the fund's ``config/universe.json`` entry. When it declares
    ``disclosure: {url, format, fields}`` the endpoint is fetched (cached for a day, since
    the numbers update once daily) and parsed. Otherwise the quote fallback is used.
    """
    cache = cache or CACHE
    fallback = from_quote(snapshot)
    disclosure = (meta or {}).get("disclosure") or {}
    url = disclosure.get("url")
    if not url:
        return fallback
    parser = PARSERS.get(disclosure.get("format", "generic_json"))
    if parser is None:
        return fallback
    payload = cached_json(url, provider="etf_disclosure", namespace="etf_disclosure", cache=cache)
    if not payload:
        return {**fallback, "disclosure_error": "endpoint unavailable"}
    parsed = parser(payload, disclosure.get("fields"))
    if not parsed.get("premium_discount_pct") and not parsed.get("median_bid_ask_spread_pct"):
        return {**fallback, "disclosure_error": "endpoint returned no usable fields"}
    return {
        **fallback,
        **{key: value for key, value in parsed.items() if value is not None},
        "disclosure_url": url,
        "source": SOURCE_RULE_6C11,
    }


def effective_spread_pct(disclosure):
    """The spread to score on: the mandated 30-day median when present, else the quote."""
    disclosure = disclosure or {}
    official = disclosure.get("median_bid_ask_spread_pct")
    if official is not None:
        return official, "rule_6c11_median_30d"
    quoted = disclosure.get("quoted_bid_ask_spread_pct")
    return (quoted, "quoted_snapshot") if quoted is not None else (None, None)


def total_cost_of_ownership(expense_ratio, tracking_difference_pct, premium_discount_pct_value):
    """A single annualized cost estimate combining the three components an owner actually pays.

    Expense ratio is already inside the fund's return, so a negative tracking difference
    (fund behind index) largely *contains* it; adding them would double-count. The estimate
    therefore takes the worse of the two as the drag, then adds the absolute premium paid at
    entry, which is a separate, real, one-time cost.
    """
    drag = None
    if tracking_difference_pct is not None:
        drag = abs(min(0.0, tracking_difference_pct))
    if expense_ratio is not None:
        drag = expense_ratio if drag is None else max(drag, expense_ratio)
    if drag is None:
        return None
    entry = abs(premium_discount_pct_value) if premium_discount_pct_value is not None else 0.0
    return round(drag + entry, 4)
