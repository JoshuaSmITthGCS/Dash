"""Triple-barrier labels, overlap weights, and purged embargoed cross-validation.

Three pieces of machinery that exist for one reason: a 2-to-10-session holding window means
every label overlaps its neighbours, and overlapping labels break the independence assumption
that every standard evaluation quietly relies on.

**Triple-barrier labeling.** A forward outcome is not a return at a fixed horizon. It is
whichever of three barriers the path touches first: an upper barrier at a multiple of the
name's own ATR, a lower barrier at a multiple of the same ATR, or a vertical barrier at the
maximum holding period. Scaling the barriers by ATR is what makes a label comparable between a
quiet name and a loud one, and taking the first touch is what makes it correspond to a
position anyone could actually have held.

**Overlap weights.** Two labels whose windows overlap carry partly the same information, so
counting both as full observations inflates the effective sample size and every t statistic
computed from it. Each label is therefore weighted by the reciprocal of the number of labels
whose windows overlap it, which is the standard concurrency correction.

**Purged, embargoed cross-validation.** A training set containing a label whose window reaches
into the test period has already seen the test period. Purging drops those labels; the embargo
drops a further band after the test set, because serial correlation in the features leaks in
the same direction even where the windows do not literally touch. Without both, a 2-to-10
session horizon leaks badly and the cross-validated result is optimistic by an amount nobody
can bound after the fact.

Reference: Lopez de Prado, Advances in Financial Machine Learning (Wiley, 2018), chapters 3,
4 and 7.
"""

from __future__ import annotations

import math

DEFAULT_VERTICAL_BARRIER_SESSIONS = 10
DEFAULT_UPPER_ATR_MULTIPLE = 2.0
DEFAULT_LOWER_ATR_MULTIPLE = 2.0
DEFAULT_ATR_WINDOW = 14


def average_true_range(highs, lows, closes, window=DEFAULT_ATR_WINDOW):
    """Wilder's average true range over the last ``window`` sessions, or None.

    True range is the widest of today's range, today's high against yesterday's close, and
    today's low against yesterday's close, so a gap counts as movement rather than being
    invisible. Falls back to close-to-close ranges where highs and lows are unavailable, which
    is the shape the cached daily series in this repository sometimes has, and that fallback
    is narrower than a true ATR rather than wider.
    """
    closes = [float(value) for value in (closes or []) if _finite(value)]
    if len(closes) < 2:
        return None
    if highs and lows and len(highs) == len(lows) == len(closes):
        ranges = []
        for index in range(1, len(closes)):
            high, low, previous = float(highs[index]), float(lows[index]), closes[index - 1]
            ranges.append(max(high - low, abs(high - previous), abs(low - previous)))
    else:
        ranges = [abs(closes[index] - closes[index - 1]) for index in range(1, len(closes))]
    ranges = ranges[-window:]
    return sum(ranges) / len(ranges) if ranges else None


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def triple_barrier_label(closes, entry_index, *, atr,
                         upper_multiple=DEFAULT_UPPER_ATR_MULTIPLE,
                         lower_multiple=DEFAULT_LOWER_ATR_MULTIPLE,
                         vertical_sessions=DEFAULT_VERTICAL_BARRIER_SESSIONS):
    """Label one entry by whichever barrier the forward path touches first.

    Returns the label (+1 upper, -1 lower, 0 vertical), the session the barrier was touched,
    the realized return to that point, and the window the label occupies. The window is what
    the overlap weighting and the purging both read, so it is part of the label rather than
    something a caller reconstructs.

    A path that runs off the end of the available series returns None: a label whose vertical
    barrier has not been reached yet is not a zero, it is not yet known, and treating the two
    the same is how a forward-looking evaluation quietly fills its most recent rows with
    optimistic outcomes.
    """
    closes = [float(value) for value in (closes or []) if _finite(value)]
    if not atr or atr <= 0 or entry_index < 0 or entry_index >= len(closes):
        return None
    entry = closes[entry_index]
    last = entry_index + vertical_sessions
    if last >= len(closes):
        return None
    upper, lower = entry + upper_multiple * atr, entry - lower_multiple * atr
    for offset in range(1, vertical_sessions + 1):
        index = entry_index + offset
        price = closes[index]
        if price >= upper:
            return _label(1, entry_index, index, entry, price, "upper_atr_barrier")
        if price <= lower:
            return _label(-1, entry_index, index, entry, price, "lower_atr_barrier")
    return _label(0, entry_index, last, entry, closes[last], "vertical_barrier")


def _label(value, entry_index, exit_index, entry_price, exit_price, barrier):
    return {
        "label": value,
        "barrier": barrier,
        "entry_index": entry_index,
        "exit_index": exit_index,
        "sessions_held": exit_index - entry_index,
        "return_pct": (exit_price / entry_price - 1) * 100 if entry_price else None,
        "window": (entry_index, exit_index),
    }


def overlap_weights(labels):
    """Weight each label by the reciprocal of how many labels its window overlaps.

    A label whose window is shared with four others carries roughly a fifth of an independent
    observation, and weighting it as one is what turns a hundred overlapping windows into a
    hundred apparent degrees of freedom. Weights are returned aligned with ``labels`` and are
    not normalized to sum to one: their sum is the effective sample size, which is the number
    a t statistic should be computed against and is reported by ``effective_sample_size``.
    """
    windows = [label["window"] for label in labels]
    weights = []
    for start, end in windows:
        concurrent = sum(1 for other_start, other_end in windows
                         if other_start <= end and start <= other_end)
        weights.append(1.0 / concurrent if concurrent else 0.0)
    return weights


def effective_sample_size(labels):
    """The number of independent observations a set of overlapping labels is worth."""
    return sum(overlap_weights(labels))


def purged_embargoed_splits(labels, *, folds=5, embargo_share=.01):
    """Train/test index splits with overlapping training labels purged and an embargo applied.

    Each fold is a contiguous block of labels, in time order. A training label is purged when
    its window overlaps the test block's window at all. The embargo removes a further
    ``embargo_share`` of the sample immediately after the test block, because features are
    serially correlated even where label windows do not literally touch, and that correlation
    leaks in the same direction.

    Yields ``{"fold", "train", "test", "purged", "embargoed"}`` with index lists into
    ``labels``. The purge and embargo counts are returned rather than silently applied, so a
    fold that lost most of its training set is visible rather than merely small.
    """
    count = len(labels)
    if count < folds or folds < 2:
        return []
    order = sorted(range(count), key=lambda index: labels[index]["window"][0])
    edges = [round(index * count / folds) for index in range(folds + 1)]
    embargo = max(1, int(round(embargo_share * count))) if embargo_share else 0

    splits = []
    for fold in range(folds):
        test = order[edges[fold]:edges[fold + 1]]
        if not test:
            continue
        test_start = min(labels[index]["window"][0] for index in test)
        test_end = max(labels[index]["window"][1] for index in test)
        embargo_positions = set(order[edges[fold + 1]:edges[fold + 1] + embargo])

        train, purged, embargoed = [], [], []
        for index in order:
            if index in set(test):
                continue
            start, end = labels[index]["window"]
            if start <= test_end and test_start <= end:
                purged.append(index)
            elif index in embargo_positions:
                embargoed.append(index)
            else:
                train.append(index)
        splits.append({"fold": fold, "train": train, "test": test,
                       "purged": purged, "embargoed": embargoed,
                       "train_size": len(train), "test_size": len(test),
                       "purged_count": len(purged), "embargoed_count": len(embargoed)})
    return splits


def label_summary(labels):
    """Counts, hit rate, and effective sample size for a set of triple-barrier labels."""
    if not labels:
        return {"labels": 0, "effective_sample_size": 0.0}
    weights = overlap_weights(labels)
    upper = sum(1 for label in labels if label["label"] == 1)
    lower = sum(1 for label in labels if label["label"] == -1)
    vertical = sum(1 for label in labels if label["label"] == 0)
    total_weight = sum(weights)
    weighted_return = (sum(weight * (label["return_pct"] or 0.0)
                           for weight, label in zip(weights, labels)) / total_weight
                       if total_weight else None)
    return {
        "labels": len(labels),
        "upper_barrier": upper,
        "lower_barrier": lower,
        "vertical_barrier": vertical,
        "hit_rate": round(upper / len(labels), 4),
        "effective_sample_size": round(total_weight, 4),
        "overlap_inflation": round(len(labels) / total_weight, 4) if total_weight else None,
        "overlap_weighted_mean_return_pct": weighted_return,
        "median_sessions_held": sorted(label["sessions_held"] for label in labels)[len(labels) // 2],
        "note": ("effective_sample_size is what a t statistic should be computed against. "
                 "overlap_inflation is the factor by which counting raw labels would have "
                 "overstated it."),
    }
