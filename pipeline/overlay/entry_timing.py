"""Entry-timing overlay: a gate on names the composite has already selected.

The composite answers **which** names. It does not answer **when**. This overlay tests one
question and only that question: does a momentum-turn filter, applied to names the composite
already selected, improve entry timing by enough to beat its own cost?

It is a timing gate, not a scoring leg. RSI and MACD do not enter the composite, do not
influence rank, and are not read anywhere in pipeline/swing_signals.py. The overlay consumes
the ranked output and returns one of three states per row:

    ENTER_NOW   every enabled gate passes
    DEFER       the composite selected it but the momentum turn has not happened yet
    REJECT      a gate the row cannot recover from inside the defer budget

**Why the toggles are mutually exclusive.** RSI, MACD, and moving-average slope are all
transforms of the same recent price series. Reading a rising RSI and a turning MACD histogram
as two confirmations triple-counts one factor and manufactures confidence that is not there.
``momentum_turn.mode`` therefore accepts exactly one value and there is no additive mode. To
test both is to run two variants, and both consume test budget.

**Why the evidence bar is raised.** Sullivan, Timmermann & White (Journal of Finance 1999)
show that once the full universe of technical trading rules tried is accounted for, the best
in-sample rule's apparent superiority is not significant. Harvey, Liu & Zhu (Review of
Financial Studies 29(1), 2016) put the credibility hurdle for a newly proposed factor at
t > 3.0 rather than 2.0. Both are enforced mechanically here: the variant registry is finite
and declared in advance, every variant is written to the hypothesis log before it runs, and
the acceptance rule in the freeze file requires t > 3.0 on a deflated Sharpe improvement.

**The measurement that matters.** A deferred name is tracked, and what it would have returned
had it been entered immediately is recorded beside what it actually returned. That is the
whole question: does waiting help, or does it just cost the first three days of the move? It
is reported as a distribution, never as a mean, because a filter that improves the average by
clipping a handful of bad entries and a filter that improves it by missing the tail are
different filters and a mean cannot tell them apart.

Everything defaults off. ``enabled: true`` raises unless ``registered_variant_id`` is set and
present in pipeline/validation/harness_freeze.json.
"""

from __future__ import annotations

import copy
import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
PIPELINE = os.path.dirname(HERE)
FREEZE_PATH = os.path.join(PIPELINE, "validation", "harness_freeze.json")
CONFIG_PATH = os.path.join(PIPELINE, "config", "entry_timing_overlay.yaml")

ENTER_NOW = "ENTER_NOW"
DEFER = "DEFER"
REJECT = "REJECT"

# Exactly one momentum-turn mode runs at a time. There is deliberately no mode that evaluates
# RSI and MACD together: they are transforms of the same price series, and treating them as
# independent confirmations is the specific error this overlay exists not to make.
MOMENTUM_MODES = ("off", "rsi_change", "macd_hist_slope")

DEFAULT_CONFIG = {
    "entry_timing_overlay": {
        "enabled": False,
        "registered_variant_id": None,
        "trend_gate": {
            "enabled": False,
            "ema_fast": 10,
            "ema_slope_lookback": 3,
            "require_close_above": 20,
        },
        "momentum_turn": {
            "mode": "off",
            "rsi_period": 14,
            "rsi_change_lookback": 3,
            "rsi_median_lookback": 60,
            "macd_fast": 12,
            "macd_slow": 26,
            "macd_signal": 9,
        },
        "volume_gate": {
            "enabled": False,
            "rvol_lookback": 20,
            "rvol_threshold": 1.5,
        },
        "max_defer_sessions": 3,
    }
}

# The whole ablation. Five cells, declared before anything ran, and this is the entire budget.
# A sixth cell raises the multiple-testing correction applied to all five and makes every one
# of them harder to validate, so adding one means documenting what is being given up.
REGISTERED_VARIANTS = {
    "O-0": {"trend_gate": False, "momentum_mode": "off", "volume_gate": False,
            "label": "control: the composite's own entry, no overlay"},
    "O-1": {"trend_gate": True, "momentum_mode": "off", "volume_gate": False,
            "label": "trend gate only"},
    "O-2": {"trend_gate": True, "momentum_mode": "off", "volume_gate": True,
            "label": "trend gate and volume gate, no momentum mode"},
    "O-3": {"trend_gate": True, "momentum_mode": "rsi_change", "volume_gate": True,
            "label": "trend gate, RSI change and inflection, volume gate"},
    "O-4": {"trend_gate": True, "momentum_mode": "macd_hist_slope", "volume_gate": True,
            "label": "trend gate, MACD histogram slope turn, volume gate"},
}


class OverlayConfigError(ValueError):
    """Raised when the overlay is asked to run in a configuration it must refuse."""


# ---------------------------------------------------------------------------
# Indicators
# ---------------------------------------------------------------------------

def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _series(values):
    return [float(value) for value in (values or []) if _finite(value)]


def ema(values, period):
    """Exponential moving average series, or None when history is shorter than the period.

    Seeded on the simple mean of the first ``period`` observations rather than on the first
    observation alone, so the early values are not dominated by one print.
    """
    series = _series(values)
    if len(series) < period or period < 1:
        return None
    multiplier = 2 / (period + 1)
    average = sum(series[:period]) / period
    output = [average]
    for value in series[period:]:
        average = (value - average) * multiplier + average
        output.append(average)
    return output


def rsi(values, period=14):
    """Wilder's relative strength index series, or None when history is too short.

    Returned as a series rather than a single reading because this overlay scores the *change*
    and the *inflection* of RSI, not its level, and both need history.
    """
    series = _series(values)
    if len(series) < period + 1:
        return None
    gains, losses = [], []
    for index in range(1, len(series)):
        change = series[index] - series[index - 1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))
    average_gain = sum(gains[:period]) / period
    average_loss = sum(losses[:period]) / period
    output = []
    for index in range(period, len(gains) + 1):
        if index > period:
            average_gain = (average_gain * (period - 1) + gains[index - 1]) / period
            average_loss = (average_loss * (period - 1) + losses[index - 1]) / period
        if not average_loss:
            output.append(100.0)
        else:
            strength = average_gain / average_loss
            output.append(100 - 100 / (1 + strength))
    return output


def macd_histogram(values, fast=12, slow=26, signal=9):
    """MACD histogram series (MACD line less its signal line), or None.

    The histogram, not the crossover. The slope of the histogram turns before the signal line
    is crossed, and this overlay's whole hypothesis is that the earlier event is the useful
    one. The crossover is computed too, so the two can be measured against each other rather
    than argued about.
    """
    fast_ema, slow_ema = ema(values, fast), ema(values, slow)
    if not fast_ema or not slow_ema:
        return None
    # The two averages start at different offsets; align them on their common tail.
    length = min(len(fast_ema), len(slow_ema))
    line = [fast_ema[-length + index] - slow_ema[-length + index] for index in range(length)]
    signal_line = ema(line, signal)
    if not signal_line:
        return None
    span = len(signal_line)
    return [line[-span + index] - signal_line[index] for index in range(span)]


def relative_volume(closes, volumes, lookback=20):
    """Today's dollar volume over its own trailing mean. Gervais-Kaniel-Mingelgrin's measure.

    Dollar volume rather than share volume, so a low-priced name's share count does not read
    as unusual activity.
    """
    closes, volumes = _series(closes), _series(volumes)
    if len(closes) != len(volumes) or len(volumes) < lookback + 1:
        return None
    dollars = [close * volume for close, volume in zip(closes, volumes)]
    baseline = sum(dollars[-(lookback + 1):-1]) / lookback
    return dollars[-1] / baseline if baseline else None


# ---------------------------------------------------------------------------
# Gates
# ---------------------------------------------------------------------------

def trend_gate(closes, config):
    """The falling-knife filter: EMA(10) rising over 3 sessions and close above EMA(20).

    This exists because an oversold reading inside a strongly bearish trend is a continuation
    signal, not a reversal signal, and every momentum-turn mode below is evaluated only on
    rows that pass here. Without it the modes spend most of their firing on names that are
    still going down.
    """
    fast = ema(closes, config["ema_fast"])
    slow = ema(closes, config["require_close_above"])
    lookback = config["ema_slope_lookback"]
    if not fast or not slow or len(fast) <= lookback:
        return {"pass": False, "reason": "INSUFFICIENT_HISTORY_FOR_TREND_GATE"}
    slope = fast[-1] - fast[-1 - lookback]
    above = _series(closes)[-1] > slow[-1]
    if slope <= 0:
        return {"pass": False, "reason": "EMA_FAST_NOT_RISING", "ema_slope": slope}
    if not above:
        return {"pass": False, "reason": "CLOSE_BELOW_SLOW_EMA",
                "close": _series(closes)[-1], "slow_ema": slow[-1]}
    return {"pass": True, "reason": "TREND_GATE_PASSED", "ema_slope": slope,
            "slow_ema": slow[-1]}


def rsi_change_turn(closes, config):
    """RSI rising over the lookback AND crossing up through its own trailing median.

    Deliberately not a level rule. No RSI < 25, no RSI < 30, no fixed threshold of any kind is
    the primary trigger. The level-threshold family is the most heavily data-snooped surface in
    the whole indicator literature, and a fixed level is where the overfitting enters: the
    number is chosen on the sample it is then evaluated on.

    The trailing median is the name's own, over ``rsi_median_lookback`` sessions, so the
    reference point is a property of the series rather than a constant somebody picked. The
    trigger is an inflection through that reference, which is an event rather than a state.
    """
    lookback = config["rsi_change_lookback"]
    median_lookback = config["rsi_median_lookback"]
    series = rsi(closes, config["rsi_period"])
    if not series or len(series) <= max(lookback, 2):
        return {"pass": False, "reason": "INSUFFICIENT_HISTORY_FOR_RSI"}
    window = series[-median_lookback:] if len(series) >= median_lookback else series
    if len(window) < 5:
        return {"pass": False, "reason": "INSUFFICIENT_HISTORY_FOR_RSI_MEDIAN"}
    ordered = sorted(window)
    middle = len(ordered) // 2
    median = (ordered[middle] if len(ordered) % 2
              else (ordered[middle - 1] + ordered[middle]) / 2)

    rising = series[-1] > series[-1 - lookback]
    crossed_up = series[-2] <= median < series[-1]
    if not rising:
        return {"pass": False, "reason": "RSI_NOT_RISING",
                "rsi": series[-1], "rsi_change": series[-1] - series[-1 - lookback]}
    if not crossed_up:
        return {"pass": False, "reason": "RSI_HAS_NOT_CROSSED_ITS_TRAILING_MEDIAN",
                "rsi": series[-1], "rsi_trailing_median": median}
    return {"pass": True, "reason": "RSI_CHANGE_TURN", "rsi": series[-1],
            "rsi_change": series[-1] - series[-1 - lookback], "rsi_trailing_median": median}


def macd_hist_slope_turn(closes, config):
    """Histogram slope turning positive while the histogram is still negative.

    Not the signal-line crossover. The crossover happens later by construction, because the
    histogram must climb all the way back through zero to produce one, and the hypothesis
    under test is that the earlier event carries the information. ``sessions_to_crossover``
    on the returned dict is the measurement that settles it: for every fired signal it records
    how many sessions the crossover version would have waited.
    """
    histogram = macd_histogram(closes, config["macd_fast"], config["macd_slow"],
                               config["macd_signal"])
    if not histogram or len(histogram) < 3:
        return {"pass": False, "reason": "INSUFFICIENT_HISTORY_FOR_MACD"}
    latest, previous, older = histogram[-1], histogram[-2], histogram[-3]
    slope_now, slope_before = latest - previous, previous - older
    if latest >= 0:
        return {"pass": False, "reason": "HISTOGRAM_ALREADY_POSITIVE",
                "macd_histogram": latest}
    if not (slope_now > 0 >= slope_before):
        return {"pass": False, "reason": "HISTOGRAM_SLOPE_NOT_TURNING",
                "macd_histogram": latest, "histogram_slope": slope_now}
    return {"pass": True, "reason": "MACD_HISTOGRAM_SLOPE_TURN",
            "macd_histogram": latest, "histogram_slope": slope_now,
            "sessions_to_crossover": _sessions_to_crossover(histogram)}


def _sessions_to_crossover(histogram):
    """Sessions between this histogram-slope turn and the crossover, or None if not yet.

    Measured backwards over the series that has already happened: from the most recent
    slope turn to the first session where the histogram went positive. None means the
    crossover has not arrived, which is itself the finding for that signal.
    """
    turn = None
    for index in range(2, len(histogram)):
        if histogram[index] < 0 and (histogram[index] - histogram[index - 1]) > 0 \
                >= (histogram[index - 1] - histogram[index - 2]):
            turn = index
    if turn is None:
        return None
    for index in range(turn + 1, len(histogram)):
        if histogram[index] >= 0:
            return index - turn
    return None


def volume_gate(closes, volumes, config):
    """Relative volume above the threshold.

    The only overlay component with direct Tier-1 support at this horizon: Gervais, Kaniel &
    Mingelgrin (Journal of Finance 2001) measure high-volume names appreciating over the
    following month. It is therefore testable on its own, which is what variant O-2 is for.
    """
    rvol = relative_volume(closes, volumes, config["rvol_lookback"])
    if rvol is None:
        return {"pass": False, "reason": "INSUFFICIENT_HISTORY_FOR_RVOL"}
    if rvol < config["rvol_threshold"]:
        return {"pass": False, "reason": "RVOL_BELOW_THRESHOLD", "rvol": rvol}
    return {"pass": True, "reason": "RVOL_ABOVE_THRESHOLD", "rvol": rvol}


MOMENTUM_GATES = {"rsi_change": rsi_change_turn, "macd_hist_slope": macd_hist_slope_turn}


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def default_config():
    return copy.deepcopy(DEFAULT_CONFIG)


def _merge(base, override):
    merged = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def registered_variant_ids(*, freeze_path=FREEZE_PATH):
    """Overlay variant ids present in the freeze file.

    Read from the freeze file rather than from REGISTERED_VARIANTS, because the constant in
    this module is what the code can express and the freeze file is what was actually
    registered, with a timestamp, before results existed. Only the second one is evidence.
    """
    try:
        with open(freeze_path, encoding="utf-8") as handle:
            freeze = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return set()
    overlay = (freeze.get("entry_timing_overlay") or {})
    return {variant.get("variant_id") for variant in (overlay.get("variants") or [])
            if variant.get("variant_id")}


def validate_config(config, *, freeze_path=FREEZE_PATH):
    """Raise unless this configuration is one the overlay is allowed to run.

    Three hard rules, all of which exist so that a result can be traced back to a hypothesis
    registered before it:

    1. ``enabled: true`` requires a ``registered_variant_id`` that is present in the freeze
       file. An overlay running under no variant id produces a number nobody can attribute.
    2. ``momentum_turn.mode`` takes exactly one value from MOMENTUM_MODES. There is no mode
       that runs RSI and MACD together, because they are transforms of one price series.
    3. The parameters must match the registered variant's declared gates. Changing a
       parameter after registration creates a new variant, so a config that disagrees with
       its own variant id is refused rather than quietly run.
    """
    block = (config or {}).get("entry_timing_overlay")
    if block is None:
        raise OverlayConfigError("config has no entry_timing_overlay block")

    mode = (block.get("momentum_turn") or {}).get("mode", "off")
    if mode not in MOMENTUM_MODES:
        raise OverlayConfigError(
            f"momentum_turn.mode must be exactly one of {MOMENTUM_MODES}, got {mode!r}. "
            "There is no additive mode: RSI and MACD are transforms of the same price series "
            "and reading them as two confirmations double-counts one factor. Testing both "
            "means registering two variants, and both consume test budget.")

    if not block.get("enabled"):
        return block

    variant_id = block.get("registered_variant_id")
    if not variant_id:
        raise OverlayConfigError(
            "entry_timing_overlay.enabled is true with no registered_variant_id. The overlay "
            "refuses to run unregistered: a result with no variant id cannot be attributed to "
            "a hypothesis that existed before it.")
    registered = registered_variant_ids(freeze_path=freeze_path)
    if variant_id not in registered:
        raise OverlayConfigError(
            f"registered_variant_id {variant_id!r} is not in the freeze file at {freeze_path}. "
            f"Registered overlay variants are {sorted(registered)}.")

    declared = REGISTERED_VARIANTS.get(variant_id)
    if declared:
        actual = {"trend_gate": bool((block.get("trend_gate") or {}).get("enabled")),
                  "momentum_mode": mode,
                  "volume_gate": bool((block.get("volume_gate") or {}).get("enabled"))}
        expected = {key: declared[key] for key in actual}
        if actual != expected:
            raise OverlayConfigError(
                f"config does not match registered variant {variant_id}: expected {expected}, "
                f"got {actual}. A parameter cannot change after its variant is registered. "
                "Changing one creates a new variant id.")
    return block


def load_config(path=CONFIG_PATH, *, overrides=None, freeze_path=FREEZE_PATH):
    """The overlay config: defaults, then the file if present, then explicit overrides."""
    config = default_config()
    if path and os.path.exists(path):
        config = _merge(config, _read_config_file(path))
    if overrides:
        config = _merge(config, overrides)
    validate_config(config, freeze_path=freeze_path)
    return config


def _read_config_file(path):
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    if path.endswith((".yaml", ".yml")):
        import yaml  # noqa: PLC0415 - only needed when a YAML config is actually present

        return yaml.safe_load(text) or {}
    return json.loads(text or "{}")


def config_for_variant(variant_id, *, base=None):
    """A config block wired to one registered ablation cell.

    Used by the ablation runner so the five cells are generated from one declaration rather
    than five hand-written config files that could drift apart from each other.
    """
    if variant_id not in REGISTERED_VARIANTS:
        raise OverlayConfigError(f"unregistered overlay variant: {variant_id!r}. "
                                 f"Registered cells are {sorted(REGISTERED_VARIANTS)}.")
    declared = REGISTERED_VARIANTS[variant_id]
    config = _merge(base or default_config(), {"entry_timing_overlay": {
        "enabled": True,
        "registered_variant_id": variant_id,
        "trend_gate": {"enabled": declared["trend_gate"]},
        "momentum_turn": {"mode": declared["momentum_mode"]},
        "volume_gate": {"enabled": declared["volume_gate"]},
    }})
    return config


# ---------------------------------------------------------------------------
# The overlay
# ---------------------------------------------------------------------------

def evaluate_row(row, series, block):
    """The entry state for one ranked row, plus every gate reading that produced it.

    ``series`` is ``{"closes": [...], "volumes": [...]}`` for the row's ticker. The gates run
    in a fixed order: trend, then the single momentum mode, then volume. Order matters because
    the trend gate is the precondition the momentum modes are evaluated under, and a momentum
    reading taken inside a falling trend is the reading the gate exists to discard.
    """
    gates = {}

    trend_config = block.get("trend_gate") or {}
    if trend_config.get("enabled"):
        gates["trend_gate"] = trend_gate(series.get("closes"), trend_config)
        if not gates["trend_gate"]["pass"]:
            # A bearish trend is not something three sessions of waiting fixes, so this is a
            # rejection rather than a deferral. It is re-evaluated on the next refresh like
            # every other row.
            return _state(REJECT, gates["trend_gate"]["reason"], gates)

    mode = (block.get("momentum_turn") or {}).get("mode", "off")
    if mode != "off":
        gates["momentum_turn"] = MOMENTUM_GATES[mode](series.get("closes"),
                                                      block["momentum_turn"])
        if not gates["momentum_turn"]["pass"]:
            # The turn may still happen, so this is a deferral. The counterfactual of entering
            # anyway is recorded by track_deferral, which is the measurement the whole overlay
            # exists to produce.
            return _state(DEFER, gates["momentum_turn"]["reason"], gates)

    volume_config = block.get("volume_gate") or {}
    if volume_config.get("enabled"):
        gates["volume_gate"] = volume_gate(series.get("closes"), series.get("volumes"),
                                           volume_config)
        if not gates["volume_gate"]["pass"]:
            return _state(DEFER, gates["volume_gate"]["reason"], gates)

    return _state(ENTER_NOW, "ALL_ENABLED_GATES_PASSED", gates)


def _state(entry_state, reason, gates):
    return {"entry_state": entry_state, "reason": reason, "gates": gates}


def apply_overlay(ranked_rows, series_for, config=None, *, deferrals=None,
                  freeze_path=FREEZE_PATH):
    """Attach an entry state to every ranked row. Never reorders and never rescores.

    ``series_for`` maps a ticker to its cached ``{"closes", "volumes"}``. ``deferrals`` is the
    prior run's deferral state, so a row deferred for longer than ``max_defer_sessions`` is
    rejected rather than deferred forever.

    With the overlay off, every row comes back ENTER_NOW with the reason stating that the
    overlay is off. That is the O-0 control, and it is a real cell of the ablation rather than
    an absence of one.
    """
    config = config or default_config()
    block = validate_config(config, freeze_path=freeze_path)
    deferrals = deferrals or {}
    output = []
    for row in ranked_rows:
        ticker = row.get("ticker")
        if not block.get("enabled"):
            output.append({**row, "entry_state": ENTER_NOW,
                           "entry_reason": "OVERLAY_DISABLED",
                           "entry_gates": {}, "sessions_deferred": 0})
            continue
        series = series_for(ticker) or {}
        decision = evaluate_row(row, series, block)
        deferred = int((deferrals.get(ticker) or {}).get("sessions_deferred", 0))
        if decision["entry_state"] == DEFER:
            deferred += 1
            if deferred > block["max_defer_sessions"]:
                decision = _state(REJECT, "DEFER_BUDGET_EXHAUSTED", decision["gates"])
        elif decision["entry_state"] == ENTER_NOW:
            pass
        output.append({**row,
                       "entry_state": decision["entry_state"],
                       "entry_reason": decision["reason"],
                       "entry_gates": decision["gates"],
                       "sessions_deferred": deferred,
                       "overlay_variant_id": block.get("registered_variant_id")})
    return output


def gate_pass_rates(overlaid_rows):
    """Pass rate per gate and the distribution of entry states.

    The trend gate's pass rate in particular has to be logged: a gate that passes everything is
    not filtering, and a gate that passes almost nothing has turned the overlay into a
    different strategy rather than a timing filter on this one.
    """
    total = len(overlaid_rows) or 1
    gates = {}
    for row in overlaid_rows:
        for name, reading in (row.get("entry_gates") or {}).items():
            entry = gates.setdefault(name, {"evaluated": 0, "passed": 0})
            entry["evaluated"] += 1
            entry["passed"] += 1 if reading.get("pass") else 0
    states = {}
    for row in overlaid_rows:
        state = row.get("entry_state")
        states[state] = states.get(state, 0) + 1
    return {
        "rows": len(overlaid_rows),
        "entry_states": states,
        "entry_state_shares": {state: round(count / total, 4)
                               for state, count in states.items()},
        "gates": {name: {**entry,
                         "pass_rate": round(entry["passed"] / entry["evaluated"], 4)
                         if entry["evaluated"] else None}
                  for name, entry in gates.items()},
    }


# ---------------------------------------------------------------------------
# Deferral counterfactual
# ---------------------------------------------------------------------------

def track_deferral(ticker, *, deferred_at_close, entered_at_close, immediate_forward_return_pct,
                   deferred_forward_return_pct, sessions_deferred):
    """One deferral, with what waiting actually cost or saved.

    This is the core measurement of the whole overlay. A filter that defers entries is only
    worth its cost if the entries it eventually takes do better than the entries it would have
    taken immediately, by more than the moves it missed while waiting.
    """
    return {
        "ticker": ticker,
        "sessions_deferred": sessions_deferred,
        "deferred_at_close": deferred_at_close,
        "entered_at_close": entered_at_close,
        "price_drift_while_waiting_pct": ((entered_at_close / deferred_at_close - 1) * 100
                                          if deferred_at_close else None),
        "immediate_forward_return_pct": immediate_forward_return_pct,
        "deferred_forward_return_pct": deferred_forward_return_pct,
        "deferral_benefit_pct": (None if immediate_forward_return_pct is None
                                 or deferred_forward_return_pct is None
                                 else deferred_forward_return_pct - immediate_forward_return_pct),
    }


def deferral_distribution(deferrals):
    """The deferral counterfactual as a distribution, deliberately not as a mean.

    Reported as deciles plus the share of deferrals that helped. A mean cannot distinguish a
    filter that improves outcomes by clipping a few disasters from one that improves them by
    missing the tail, and those two filters have opposite implications for whether the overlay
    should ship. The mean is included, last and labelled, so it cannot be read alone.
    """
    benefits = sorted(entry["deferral_benefit_pct"] for entry in deferrals
                      if entry.get("deferral_benefit_pct") is not None)
    if not benefits:
        return {"deferrals": len(deferrals), "measured": 0, "status": "no_resolved_deferrals"}

    def quantile(share):
        position = share * (len(benefits) - 1)
        low = int(position)
        high = min(low + 1, len(benefits) - 1)
        return benefits[low] + (benefits[high] - benefits[low]) * (position - low)

    helped = sum(1 for value in benefits if value > 0)
    sessions = sorted(entry["sessions_deferred"] for entry in deferrals
                      if entry.get("sessions_deferred") is not None)
    return {
        "deferrals": len(deferrals),
        "measured": len(benefits),
        "deciles": {f"p{int(share * 100)}": round(quantile(share), 4)
                    for share in (.1, .2, .3, .4, .5, .6, .7, .8, .9)},
        "worst": benefits[0],
        "best": benefits[-1],
        "share_where_waiting_helped": round(helped / len(benefits), 4),
        "average_sessions_deferred": (round(sum(sessions) / len(sessions), 3)
                                      if sessions else None),
        "mean_benefit_pct": round(sum(benefits) / len(benefits), 4),
        "reading": ("share_where_waiting_helped is the headline. A mean improvement driven by "
                    "a handful of avoided drops and a mean improvement driven by missing the "
                    "right tail are different findings with opposite implications, and only "
                    "the distribution separates them."),
    }
