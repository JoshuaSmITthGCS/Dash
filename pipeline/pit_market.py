"""Point-in-time market data and universe membership.

**A correction to an earlier assumption in this engagement**, and then a correction to the
correction, because the first one was half right.

I claimed adjusted closes embed future corporate actions and were unusable for a backtest.
That is wrong for *returns*. An adjusted close is ``price[t] x F[t]`` where ``F[t]`` is the
cumulative factor for every action after t, and a return is a ratio::

    adj[t2] / adj[t1] = (price[t2] / price[t1]) x (F[t2] / F[t1])

``F[t2] / F[t1]`` collapses to the actions falling strictly between t1 and t2, all of which
had happened and were known by t2. A return computed from adjusted closes is therefore not
contaminated by anything after t2. Verified against Apple across its 2020 4:1 split.

I then claimed the cache's ``raw_closes`` were prices as actually traded, and that reading
them fixed the level problem. That is also wrong. ``raw_closes`` is Yahoo's ``Close`` with
``auto_adjust=False``, which is **split-adjusted and only dividend-unadjusted**: Apple's
2016-08-08 close reads $27.09 there against roughly $108.37 as it actually traded, exactly a
quarter, because of a split four years in the future. Checked across every split in the
cache -- no split shows as a jump in either series.

So this repository holds two series and neither is a traded price level:

===============  ============  ==============  =========================================
series           splits        dividends       honest use
===============  ============  ==============  =========================================
``closes``       adjusted      adjusted        total return between two dates
``raw_closes``   adjusted      not adjusted    price return; market cap given a share
                                               count on the same split basis
===============  ============  ==============  =========================================

The consequences are handled rather than described:

* **Returns are safe** on either series, and ``total_return`` uses the adjusted one.
* **A market cap is recoverable**, because ``pit_shares`` carries filed share counts onto the
  same split basis using the filers' own restatements. Level in, level out, consistently.
* **A minimum-price screen is not recoverable** and is off by default. On this data it would
  read Apple out of the 2016 universe at $27 and read a company that later reverse-split into
  it at a price it never traded -- and the second direction is the one that admits the
  delisting candidates a price floor exists to exclude. ``minimum_dollar_volume`` does that
  job instead, and does it robustly: a split divides the price and multiplies the volume, so
  their product is untouched.

Two further properties, both enforced rather than documented:

* **Nothing past the as-of date is readable**, whichever series is used.
* **Universe membership is reconstructed, not assumed.** A company belongs to the universe on
  a date only if it was priced, liquid and filing then. The cache holds today's survivors, so
  this narrows an already-survivor-biased set rather than curing it; ``survivorship_note``
  states the residual plainly instead of leaving a reader to discover it.
"""

import json
import os
from bisect import bisect_right
from datetime import date, timedelta

from common import STORE_DIR

CACHE_DIR = os.path.join(STORE_DIR, "backtest_cache")

# A filer that has not filed a periodic report in this long has almost certainly delisted,
# been acquired, or gone dark. Two quarters plus filing lag.
FILING_SILENCE_DAYS = 270

# A single session that changes the price by this factor is not a price move. It is a ticker
# that stopped denoting one security and started denoting another, and the series either side
# of it belongs to two different companies.
#
# Chord Energy is the case in this cache. Oasis Petroleum emerged from Chapter 11 on
# 2020-11-19 with its old equity cancelled and new equity issued; the cache splices both under
# CHRD, so 2020-11-20 reads $0.12 to $31.00 -- a 258-fold session. Carried into a backtest it
# is a +39,130% month, and one such month is enough on its own to put a factor's annualised
# volatility above 500% and its Sortino ratio near 10.
#
# The threshold sits where the two populations separate. The largest genuine single-session
# moves in this cache are 2.7x (Chord itself, at 23 cents, bouncing back the next day) and
# 2.08x (Avis in the 2021 squeeze); the reorganisation is two orders of magnitude beyond
# either. Nothing in the cache falls between 2.7x and 258x.
IDENTITY_BREAK_FACTOR = 4.0


class PriceHistory:
    """One security's price series, with level and return questions answered separately."""

    def __init__(self, ticker, dates, adjusted, split_adjusted, volumes=None):
        self.ticker = ticker
        self.dates = dates
        self.adjusted = adjusted
        # Split-adjusted, dividend-unadjusted. Named for what it is: the cache calls it
        # ``raw_closes``, which invites exactly the mistake documented above.
        self.split_adjusted = split_adjusted
        self.volumes = volumes or []
        self.identity_breaks = self._find_identity_breaks()

    def _find_identity_breaks(self):
        """Sessions where the ticker changed which security it denotes."""
        breaks = []
        for index in range(1, len(self.adjusted)):
            previous, current = self.adjusted[index - 1], self.adjusted[index]
            if not previous or not current:
                continue
            step = current / previous
            if step >= IDENTITY_BREAK_FACTOR or step <= 1 / IDENTITY_BREAK_FACTOR:
                breaks.append(index)
        return breaks

    def _last_break_before(self, index):
        return next((position for position in reversed(self.identity_breaks)
                     if position <= index), None)

    def spans_identity_break(self, first, last):
        """Whether a window from ``first`` to ``last`` crosses a change of security."""
        return any(first < position <= last for position in self.identity_breaks)

    @classmethod
    def load(cls, ticker, directory=None):
        path = os.path.join(directory or CACHE_DIR, f"{ticker}.json")
        if not os.path.exists(path):
            return None
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
        dates = payload.get("dates") or []
        if not dates:
            return None
        return cls(ticker, dates, payload.get("closes") or [],
                   payload.get("raw_closes") or payload.get("closes") or [],
                   payload.get("volumes") or [])

    def _index_at(self, when):
        """Index of the last session on or before ``when``, or None if the series starts later."""
        position = bisect_right(self.dates, str(when)[:10]) - 1
        return position if position >= 0 else None

    def price(self, when):
        """Price on today's split basis, dividends not reinvested.

        Pair it only with a share count on the same basis -- ``pit_shares`` produces one.
        This is *not* the price as it traded on ``when``, and no level threshold should be
        applied to it; see the module docstring.
        """
        index = self._index_at(when)
        return (self.split_adjusted[index]
                if index is not None and index < len(self.split_adjusted) else None)

    def adjusted_price(self, when):
        """Split- and dividend-adjusted. Use this only inside a return calculation."""
        index = self._index_at(when)
        return self.adjusted[index] if index is not None and index < len(self.adjusted) else None

    def total_return(self, start, end):
        """Total return between two dates, dividends reinvested.

        Adjusted closes are correct here: the ratio depends only on corporate actions between
        the two dates, all of which were known by ``end``.
        """
        opening, closing = self._index_at(start), self._index_at(end)
        if opening is None or closing is None or self.spans_identity_break(opening, closing):
            return None
        first, last = self.adjusted[opening], self.adjusted[closing]
        if not first or last is None:
            return None
        return last / first - 1

    def dollar_volume(self, when, *, sessions=60):
        """Median daily dollar volume over the trailing window.

        Split-proof without any correction: a split divides the price series and multiplies
        the volume series by the same factor, so the product each session is the dollar
        volume that actually changed hands.
        """
        index = self._index_at(when)
        if index is None:
            return None
        start = max(0, index - sessions + 1)
        values = [self.split_adjusted[position] * self.volumes[position]
                  for position in range(start, index + 1)
                  if position < len(self.split_adjusted) and position < len(self.volumes)]
        if not values:
            return None
        values.sort()
        return values[len(values) // 2]

    def covers(self, when, *, minimum_sessions=1):
        """Whether ``minimum_sessions`` of *this* security's history precede ``when``.

        History is counted from the last identity break rather than from the start of the
        file. A company that emerged from bankruptcy with new equity has no more trading
        record than one that listed the same day, and must earn the same warm-up before it is
        rankable -- which is also what stops a twelve-month momentum reading from measuring
        the security that the ticker used to mean.
        """
        index = self._index_at(when)
        if index is None:
            return False
        origin = self._last_break_before(index)
        return index + 1 - (origin or 0) >= minimum_sessions


def load_universe_prices(tickers, directory=None):
    histories = {}
    for ticker in tickers:
        history = PriceHistory.load(ticker, directory)
        if history is not None:
            histories[ticker] = history
    return histories


def last_filing_dates(observations):
    """Newest filing date seen per CIK, for detecting a filer that went silent."""
    latest = {}
    for row in observations:
        cik, filed = row.get("cik"), row.get("filed")
        if cik and filed and filed > latest.get(cik, ""):
            latest[cik] = filed
    return latest


def universe_as_of(when, *, prices, cik_by_ticker=None, last_filings=None,
                   minimum_price=None, minimum_dollar_volume=1e6, minimum_sessions=252,
                   filing_silence_days=FILING_SILENCE_DAYS):
    """Securities investable on ``when``, by rules evaluated only on data available then.

    Returns ``(members, diagnostics)``. Every exclusion is counted, because a universe rule
    that quietly removes a third of the names changes a backtest more than most factor
    choices do, and should be visible rather than inferred.

    ``minimum_price`` defaults to off. The available price levels are split-adjusted to
    today, so a floor applied to them excludes and admits the wrong names; the module
    docstring works through why. It remains a parameter so a caller with genuinely
    unadjusted prices can switch it on, and the diagnostics record which way it was set.
    """
    cutoff = str(when)[:10]
    counts = {"no_price_history": 0, "insufficient_history": 0, "below_minimum_price": 0,
              "below_minimum_dollar_volume": 0, "filer_gone_silent": 0}
    members = []
    for ticker, history in prices.items():
        if not history.covers(cutoff):
            counts["no_price_history"] += 1
            continue
        if not history.covers(cutoff, minimum_sessions=minimum_sessions):
            counts["insufficient_history"] += 1
            continue
        if minimum_price:
            price = history.price(cutoff)
            if price is None or price < minimum_price:
                counts["below_minimum_price"] += 1
                continue
        volume = history.dollar_volume(cutoff)
        if minimum_dollar_volume and (volume is None or volume < minimum_dollar_volume):
            counts["below_minimum_dollar_volume"] += 1
            continue
        if last_filings is not None and cik_by_ticker is not None:
            cik = cik_by_ticker.get(ticker)
            newest = last_filings.get(cik)
            if newest and _days_between(newest, cutoff) > filing_silence_days:
                counts["filer_gone_silent"] += 1
                continue
        members.append(ticker)
    return sorted(members), {
        "as_of": cutoff,
        "candidates": len(prices),
        "members": len(members),
        "excluded": counts,
        "rules": {"minimum_price": minimum_price,
                  "minimum_dollar_volume": minimum_dollar_volume,
                  "minimum_sessions": minimum_sessions,
                  "filing_silence_days": filing_silence_days},
        "price_level_note": (
            "Price levels in this cache are split-adjusted to today, so no threshold is "
            "applied to them. Liquidity is screened on dollar volume, which a split leaves "
            "unchanged."),
        "survivorship_note": (
            "Membership is reconstructed from securities present in today's price cache, so "
            "these rules narrow an already-survivor-biased candidate set rather than curing "
            "it. Companies that delisted before the cache was built are absent entirely and "
            "no rule here can recover them. Any performance measured on this universe is "
            "biased upward by an amount this pipeline cannot yet quantify."),
    }


def _days_between(earlier, later):
    try:
        return (date.fromisoformat(str(later)[:10]) - date.fromisoformat(str(earlier)[:10])).days
    except (TypeError, ValueError):
        return 0


def rebalance_dates(start, end, *, every_days=21):
    """Evenly spaced rebalance dates. Approximately monthly at the default spacing."""
    try:
        current = date.fromisoformat(str(start)[:10])
        final = date.fromisoformat(str(end)[:10])
    except (TypeError, ValueError):
        return []
    dates = []
    while current <= final:
        dates.append(current.isoformat())
        current += timedelta(days=every_days)
    return dates
