"""Prospective full-universe information-coefficient validation harness.

The harness only grades scores that were recorded before their forward returns existed.
It never reconstructs earlier score history from current fundamentals. Until a later PIT
snapshot supplies a complete forward horizon, every statistic remains in an accumulating
state and the public artifact reports zero eligible periods.
"""

import argparse
import hashlib
import json
import math
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from statistics import mean, stdev

PIPELINE_DIR = os.path.dirname(os.path.dirname(__file__))
if PIPELINE_DIR not in sys.path:
    sys.path.insert(0, PIPELINE_DIR)

from common import LOG, DATA_DIR, load_json, save_json  # noqa: E402
from costs import estimate_cost_bps  # noqa: E402
from evaluation import deflated_sharpe_ratio, pearson, rank  # noqa: E402
import pit_store as raw_pit_store  # noqa: E402
from validation.trading_calendar import default_calendar  # noqa: E402


SETTINGS = load_json("settings.json", from_config=True) or {}
CONFIG = SETTINGS["validation"]
PIT_ROOT = os.path.join(PIPELINE_DIR, "pit_store")
PUBLIC_NAME = "validation/ic_validation.json"


def _config_hash():
    encoded = json.dumps(SETTINGS, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _iso(value=None):
    if isinstance(value, str):
        return value
    return (value or datetime.now(timezone.utc)).isoformat()


def _metric_scores(detail):
    metric_names = {
        metric
        for weights in SETTINGS["fundamentals"]["metric_weights"].values()
        for metric in weights
    }
    return {metric: detail.get(metric) for metric in sorted(metric_names)}


# Maps a modifier field to the provider whose absence makes that modifier unobservable.
# A modifier with no entry here is always computable from data the pipeline already holds.
MODIFIER_SOURCE = {
    "insider_activity": "sec_form4",
    "macro_regime": "fred",
    "customer_concentration_risk": "sec_filing_risk",
    "geographic_concentration": "sec_filing_risk",
    "institutional_13f": "sec_institutional_13f",
}

# Provider statuses that mean "we never got to look", as distinct from "we looked and saw
# nothing". confidence.run_source_reliability draws the same distinction.
_UNAVAILABLE_STATUSES = {"unavailable", "failed", "configuration_required", "opt_in",
                         "disabled_for_intraday_refresh"}


def unavailable_modifiers(source_status=None):
    """Modifier fields whose underlying provider was dark for this refresh.

    ``source_status`` is the published ``advisor.json`` ``source_status`` map, whose values
    are either a bare status string or a ``{"status": ...}`` block.
    """
    source_status = source_status or {}
    dark = set()
    for field, provider in MODIFIER_SOURCE.items():
        entry = source_status.get(provider)
        status = entry.get("status") if isinstance(entry, dict) else entry
        if status is None or status in _UNAVAILABLE_STATUSES:
            dark.add(field)
    return dark


def _modifier_contract(detail, unavailable=()):
    """Keep original detail and add an explicit zero-inclusive modifier point map.

    ``all_points`` records a literal 0.0 for any modifier that did not fire. That is correct
    for a modifier the pipeline evaluated and found neutral, but *wrong* for one whose
    provider was never reachable -- a dark SEC Form 4 layer would otherwise be recorded as
    "we reviewed insider activity and it was neutral" in an immutable validation snapshot,
    and later graded as real evidence. ``availability`` separates the two so unavailable
    coverage can never be counted as an observation.
    """
    detail = dict(detail or {})
    applied = detail.get("applied") or {}
    unavailable = set(unavailable)
    detail["all_points"] = {
        name: applied.get(name, 0.0)
        for name in CONFIG["modifier_fields"]
    }
    detail["availability"] = {
        name: "unavailable" if name in unavailable and name not in applied else "available"
        for name in CONFIG["modifier_fields"]
    }
    return detail


def snapshot_row(row, *, refresh_id, recorded_at, data_as_of, universe, published,
                 model_version, config_hash, dark_modifiers=()):
    """Project one scored row into the immutable validation contract."""
    variants = row.get("score_variants") or {}
    champion = variants.get("champion") or {}
    challenger = variants.get("challenger") or {}
    champion_detail = row.get("fundamental_detail") or {}
    challenger_detail = challenger.get("fundamental_detail") or {}
    raw = {field: row.get(field) for field in raw_pit_store.TRACKED_FIELDS}
    raw = {field: value for field, value in raw.items() if value is not None}
    ticker = str(row.get("ticker") or "").upper()
    missing = []
    if challenger.get("score") is None:
        missing.append("challenger_score_not_available_in_source_snapshot")
    if not challenger_detail and not challenger.get("normalized_metric_scores"):
        missing.append("challenger_metric_scores_not_available_in_source_snapshot")
    return {
        "snapshot_schema_version": CONFIG["snapshot_schema_version"],
        "refresh_id": refresh_id,
        "recorded_at": recorded_at,
        "data_as_of": data_as_of,
        "ticker": ticker,
        "raw_metric_inputs": raw,
        "normalized_metric_scores": {
            "champion": champion.get("normalized_metric_scores") or _metric_scores(champion_detail),
            "challenger": challenger.get("normalized_metric_scores") or _metric_scores(challenger_detail),
        },
        "category_scores": {
            "champion": champion.get("fundamental_categories") or row.get("fundamental_categories") or {},
            "challenger": challenger.get("fundamental_categories") or {},
        },
        "confidence": {
            "champion": champion.get("confidence", row.get("confidence")),
            "challenger": challenger.get("confidence"),
        },
        "modifiers": {
            "champion": _modifier_contract(row.get("modifiers"), dark_modifiers),
            "challenger": _modifier_contract(challenger.get("modifiers"), dark_modifiers),
        },
        "scores": {
            "champion": champion.get("score", row.get("score")),
            "challenger": challenger.get("score"),
        },
        "price": row.get("price"),
        "model_version": model_version,
        "config_hash": config_hash,
        "universe_membership": ticker in universe,
        "published_research": ticker in published,
        "data_integrity": "prospective_point_in_time",
        "quality_flags": missing,
    }


def append_refresh(rows, *, refresh_id, recorded_at=None, data_as_of=None, universe=(),
                   published=(), model_version=None, config_hash=None, root=PIT_ROOT,
                   source_status=None):
    """Append one immutable JSONL row per scored ticker for a refresh.

    An identical ``refresh_id`` is idempotent. Existing records are never changed, and a
    later invocation with a different refresh id only appends.
    """
    recorded_at = _iso(recorded_at)
    data_as_of = _iso(data_as_of or recorded_at)
    universe, published = set(universe), set(published)
    model_version = model_version or (SETTINGS.get("model") or {}).get("semantic_version")
    config_hash = config_hash or _config_hash()
    os.makedirs(root, exist_ok=True)
    path = os.path.join(root, f"{recorded_at[:10]}.jsonl")
    if os.path.exists(path):
        with open(path) as handle:
            if any(json.loads(line).get("refresh_id") == refresh_id for line in handle if line.strip()):
                return {"path": path, "appended": 0, "refresh_id": refresh_id, "idempotent": True}
    unique = {}
    for row in rows:
        ticker = str(row.get("ticker") or "").upper()
        if ticker:
            unique.setdefault(ticker, row)
    dark_modifiers = unavailable_modifiers(source_status)
    snapshots = [snapshot_row(
        row,
        refresh_id=refresh_id,
        recorded_at=recorded_at,
        data_as_of=data_as_of,
        universe=universe,
        published=published,
        model_version=model_version,
        config_hash=config_hash,
        dark_modifiers=dark_modifiers,
    ) for row in unique.values()]
    with open(path, "a") as handle:
        for snapshot in snapshots:
            handle.write(json.dumps(snapshot, sort_keys=True, default=str) + "\n")
    return {"path": path, "appended": len(snapshots), "refresh_id": refresh_id,
            "idempotent": False}


def read_snapshots(root=PIT_ROOT):
    rows = []
    if not os.path.isdir(root):
        return rows
    for name in sorted(os.listdir(root)):
        if not name.endswith(".jsonl"):
            continue
        with open(os.path.join(root, name)) as handle:
            for line in handle:
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    LOG.warn(f"Invalid validation PIT row skipped in {name}")
    return rows


def _refreshes(rows):
    grouped = defaultdict(list)
    metadata = {}
    for row in rows:
        refresh_id = row.get("refresh_id")
        if not refresh_id:
            continue
        grouped[refresh_id].append(row)
        metadata[refresh_id] = row.get("recorded_at")
    return sorted(({"refresh_id": key, "recorded_at": metadata[key], "rows": value}
                   for key, value in grouped.items()), key=lambda item: item["recorded_at"])


def _monthly_refreshes(refreshes):
    """Use the final recorded refresh in each month as one IC observation period."""
    monthly = {}
    for refresh in refreshes:
        monthly[refresh["recorded_at"][:7]] = refresh
    return [monthly[key] for key in sorted(monthly)]


def _forward_periods(refreshes, variant, horizon_days):
    """Secondary diagnostic path: calendar-day horizon, raw (non-residualized) forward
    return. See ``_forward_periods_sessions`` for the preregistered primary target (B1).
    """
    periods = []
    for index, start in enumerate(refreshes):
        start_date = datetime.fromisoformat(start["recorded_at"].replace("Z", "+00:00"))
        target = start_date + timedelta(days=horizon_days)
        end = next((candidate for candidate in refreshes[index + 1:]
                    if datetime.fromisoformat(candidate["recorded_at"].replace("Z", "+00:00")) >= target), None)
        if not end:
            continue
        end_prices = {row["ticker"]: row.get("price") for row in end["rows"]}
        scored = []
        for row in start["rows"]:
            score = (row.get("scores") or {}).get(variant)
            start_price, end_price = row.get("price"), end_prices.get(row.get("ticker"))
            if not isinstance(score, (int, float)) or not start_price or not end_price:
                continue
            scored.append({
                "ticker": row["ticker"],
                "score": score,
                "forward_return": end_price / start_price - 1,
                "average_dollar_volume": (row.get("raw_metric_inputs") or {}).get("average_dollar_volume"),
            })
        if scored:
            periods.append({"date": start["recorded_at"][:10], "rows": scored})
    return periods


def sector_residual_returns(scored_rows, *, minimum_peers=None):
    """Label = stock forward return minus the equal-weight mean forward return of every
    *other* name in the same sector over the same window. Falls back to the equal-weight
    universe mean (still excluding the stock itself) when a sector has fewer than
    ``minimum_peers`` other names -- flagged explicitly via ``sector_residual_fallback``
    rather than silently blending a thin sector into a number that looks the same as a real
    one.
    """
    minimum_peers = CONFIG["sector_residual_minimum_peers"] if minimum_peers is None else minimum_peers
    by_sector = defaultdict(list)
    for row in scored_rows:
        by_sector[row.get("sector") or None].append(row)
    universe_total = sum(row["forward_return"] for row in scored_rows)
    universe_count = len(scored_rows)
    labeled = []
    for row in scored_rows:
        sector = row.get("sector")
        peers = [peer for peer in by_sector.get(sector, ()) if peer is not row] if sector else []
        if sector and len(peers) >= minimum_peers:
            peer_mean = mean(peer["forward_return"] for peer in peers)
            fallback = False
        else:
            other_count = universe_count - 1
            peer_mean = ((universe_total - row["forward_return"]) / other_count) if other_count > 0 else 0.0
            fallback = True
        labeled.append({
            **row,
            "sector_residual_return": row["forward_return"] - peer_mean,
            "sector_residual_fallback": fallback,
            "sector_peer_count": len(peers),
        })
    return labeled


def _forward_periods_sessions(refreshes, variant, horizon_sessions, calendar=None):
    """Preregistered primary target (B1): a real trading-session horizon (not calendar
    days) and a sector-residual label (not raw return) -- see settings.json
    ``validation.horizons_sessions`` / ``primary_horizon``. ``sector`` arrives on every row
    via ``raw_metric_inputs`` (pit_store.TRACKED_FIELDS already tracks it).
    """
    calendar = calendar or default_calendar()
    periods = []
    for index, start in enumerate(refreshes):
        start_date = datetime.fromisoformat(start["recorded_at"].replace("Z", "+00:00")).date()
        target = calendar.add_sessions(start_date, horizon_sessions)
        if target is None:
            continue
        end = next((candidate for candidate in refreshes[index + 1:]
                    if datetime.fromisoformat(candidate["recorded_at"].replace("Z", "+00:00")).date() >= target),
                   None)
        if not end:
            continue
        end_prices = {row["ticker"]: row.get("price") for row in end["rows"]}
        scored = []
        for row in start["rows"]:
            score = (row.get("scores") or {}).get(variant)
            start_price, end_price = row.get("price"), end_prices.get(row.get("ticker"))
            if not isinstance(score, (int, float)) or not start_price or not end_price:
                continue
            scored.append({
                "ticker": row["ticker"],
                "score": score,
                "forward_return": end_price / start_price - 1,
                "sector": (row.get("raw_metric_inputs") or {}).get("sector"),
                "average_dollar_volume": (row.get("raw_metric_inputs") or {}).get("average_dollar_volume"),
            })
        if scored:
            periods.append({"date": start["recorded_at"][:10],
                            "rows": sector_residual_returns(scored)})
    return periods


def research_trial_count():
    """The honest number of configurations tried, for Deflated Sharpe.

    ``settings.json validation.shadow_strategy_trials`` counts only the live shadow
    strategies. Deflation needs the count of everything *searched* across the whole research
    programme -- understating it is the standard way a deflated Sharpe gets quietly
    re-inflated. The experiment registry is the durable record of that, so it is the floor
    here; the configured value wins only if it is somehow larger.
    """
    try:
        from experiment_registry import total_variants_tested
    except ImportError:      # registry not importable in a trimmed checkout
        return CONFIG["shadow_strategy_trials"]
    return max(CONFIG["shadow_strategy_trials"], total_variants_tested())


def _spearman(left, right):
    if len(left) < 3:
        return None
    return pearson(rank(left), rank(right))


def _buckets(rows, count, return_field="forward_return"):
    ordered = sorted(rows, key=lambda row: row["score"])
    buckets = []
    for index in range(count):
        start = round(index * len(ordered) / count)
        end = round((index + 1) * len(ordered) / count)
        chunk = ordered[start:end]
        if chunk:
            buckets.append({
                "bucket": index + 1,
                "count": len(chunk),
                "mean_forward_return": mean(row[return_field] for row in chunk),
            })
    return buckets


def _ic_summary(values):
    n = len(values)
    average = mean(values) if values else None
    deviation = stdev(values) if n > 1 else None
    standard_error = deviation / math.sqrt(n) if deviation is not None else None
    interval = ([average - CONFIG["confidence_interval_z"] * standard_error,
                 average + CONFIG["confidence_interval_z"] * standard_error]
                if standard_error is not None else [None, None])
    eligible = n >= CONFIG["minimum_icir_periods"]
    icir = average / deviation if eligible and deviation else None
    return {
        "periods_accumulated": n,
        "minimum_periods": CONFIG["minimum_icir_periods"],
        "status": "eligible" if eligible else "accumulating",
        "status_message": ("eligible for ICIR" if eligible else
                           f"accumulating, {n} of {CONFIG['minimum_icir_periods']} periods"),
        "mean_rank_ic": average,
        "ic_standard_deviation": deviation,
        "standard_error": standard_error,
        "confidence_interval_95": interval,
        "icir": icir,
        "annualized_icir": icir * math.sqrt(CONFIG["periods_per_year"]) if icir is not None else None,
    }


def _turnover_and_stability(periods):
    turnover, stability = [], []
    for previous, current in zip(periods, periods[1:]):
        before = {row["ticker"]: row["score"] for row in previous["rows"]}
        after = {row["ticker"]: row["score"] for row in current["rows"]}
        common = sorted(set(before) & set(after))
        if len(common) < 3:
            continue
        top_count = max(1, len(common) // CONFIG["quantile_counts"][0])
        top_before = set(sorted(common, key=before.get, reverse=True)[:top_count])
        top_after = set(sorted(common, key=after.get, reverse=True)[:top_count])
        turnover.append(1 - len(top_before & top_after) / top_count)
        stability.append(_spearman([before[ticker] for ticker in common],
                                   [after[ticker] for ticker in common]))
    return {
        "mean_top_quintile_turnover": mean(turnover) if turnover else None,
        "mean_rank_stability": mean(value for value in stability if value is not None)
        if any(value is not None for value in stability) else None,
    }


def _period_cost_bps(rows, count):
    """The flat rate unless ``validation.cost_model`` is "tiered", in which case each
    top/bottom-bucket name is priced through costs.py using its own tracked
    ``average_dollar_volume`` (no annualized-volatility field is point-in-time-tracked yet,
    so this prices spread + fees only, not market impact -- a conservative, labeled
    understatement rather than a fabricated volatility input). Falls back to the flat rate
    for any name missing tracked volume, and for the period as a whole if none have it.
    """
    if CONFIG.get("cost_model", "flat") != "tiered":
        return CONFIG["long_short_cost_bps"]
    ordered = sorted(rows, key=lambda row: row["score"])
    bucket_size = max(1, round(len(ordered) / count))
    scenario = CONFIG.get("cost_scenario", "base")
    bps_values = []
    for row in (*ordered[-bucket_size:], *ordered[:bucket_size]):
        median_dollar_volume_60d = row.get("average_dollar_volume")
        if not median_dollar_volume_60d:
            continue
        bps_values.append(
            estimate_cost_bps(median_dollar_volume_60d=median_dollar_volume_60d,
                              scenario=scenario)["total_bps"]
        )
    return mean(bps_values) if bps_values else CONFIG["long_short_cost_bps"]


def _evaluate_periods(periods, variant, *, return_field="forward_return"):
    ic_values, leaks, bucket_periods, spreads, applied_cost_bps = [], [], defaultdict(list), [], []
    for period in periods:
        rows = period["rows"]
        ic = _spearman([row["score"] for row in rows], [row[return_field] for row in rows])
        if ic is not None:
            ic_values.append(ic)
            if abs(ic) > CONFIG["lookahead_rank_ic_threshold"]:
                leak = {"date": period["date"], "rank_ic": ic,
                        "message": "Probable look-ahead or data leak. Investigate before interpreting."}
                leaks.append(leak)
                LOG.error(f"LOOK-AHEAD WARNING {variant} {period['date']}: rank IC {ic:.3f}")
        for count in CONFIG["quantile_counts"]:
            buckets = _buckets(rows, count, return_field)
            for bucket in buckets:
                bucket_periods[(count, bucket["bucket"])].append(bucket["mean_forward_return"])
            if count == CONFIG["quantile_counts"][0] and len(buckets) == count:
                cost_bps = _period_cost_bps(rows, count)
                applied_cost_bps.append(cost_bps)
                spreads.append(buckets[-1]["mean_forward_return"]
                               - buckets[0]["mean_forward_return"]
                               - cost_bps / 10_000)
    bucket_output = {}
    for count in CONFIG["quantile_counts"]:
        aggregated = [{
            "bucket": index,
            "mean_forward_return": mean(bucket_periods[(count, index)])
            if bucket_periods[(count, index)] else None,
        } for index in range(1, count + 1)]
        present = [item for item in aggregated if item["mean_forward_return"] is not None]
        monotonicity = _spearman(
            [item["bucket"] for item in present],
            [item["mean_forward_return"] for item in present],
        ) if present else None
        bucket_output[str(count)] = {
            "buckets": aggregated,
            "monotonicity_spearman": monotonicity,
            "monotonic": monotonicity is not None and monotonicity > 0,
        }
    spread_sharpe = mean(spreads) / stdev(spreads) if len(spreads) > 1 and stdev(spreads) else None
    fallback_periods = [
        sum(1 for row in period["rows"] if row.get("sector_residual_fallback"))
        for period in periods
    ]
    return {
        **_ic_summary(ic_values),
        "monthly_rank_ic": ic_values,
        "probable_lookahead_flags": leaks,
        "bucket_returns": bucket_output,
        "long_short_top_minus_bottom_quintile": {
            "mean_net_return": mean(spreads) if spreads else None,
            "cost_model": CONFIG.get("cost_model", "flat"),
            "cost_bps": mean(applied_cost_bps) if applied_cost_bps else CONFIG["long_short_cost_bps"],
        },
        "trials_considered": research_trial_count(),
        "deflated_sharpe_probability": deflated_sharpe_ratio(
            spread_sharpe,
            observations=len(spreads),
            trials=research_trial_count(),
        ) if spread_sharpe is not None else None,
        **_turnover_and_stability(periods),
        **({"sector_residual_fallback_rows": sum(fallback_periods)} if return_field == "sector_residual_return" else {}),
    }


def evaluate_variant(refreshes, variant, horizon_days):
    """Secondary diagnostic: calendar-day horizon, raw forward return. Kept for continuity
    with existing published reports; ``evaluate_variant_sessions`` is the primary target.
    """
    periods = _forward_periods(refreshes, variant, horizon_days)
    return _evaluate_periods(periods, variant, return_field="forward_return")


def evaluate_variant_sessions(refreshes, variant, horizon_sessions, calendar=None):
    """Primary target (B1): real trading-session horizon, sector-residual label."""
    periods = _forward_periods_sessions(refreshes, variant, horizon_sessions, calendar)
    return _evaluate_periods(periods, variant, return_field="sector_residual_return")


def build_report(rows=None):
    rows = read_snapshots() if rows is None else rows
    refreshes = _refreshes(rows)
    monthly_refreshes = _monthly_refreshes(refreshes)
    variants = {variant: {} for variant in ("champion", "challenger")}
    for variant in variants:
        for label, days in CONFIG["horizons_days"].items():
            variants[variant][label] = evaluate_variant(monthly_refreshes, variant, days)

    primary_variants = {variant: {} for variant in ("champion", "challenger")}
    try:
        calendar = default_calendar()
    except (FileNotFoundError, ValueError) as exc:
        calendar = None
        LOG.warn(f"Trading calendar unavailable, primary (session-based) IC skipped: {exc}")
    if calendar is not None:
        for variant in primary_variants:
            for label, sessions in CONFIG["horizons_sessions"].items():
                primary_variants[variant][label] = evaluate_variant_sessions(
                    monthly_refreshes, variant, sessions, calendar
                )

    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_integrity": "prospective_point_in_time",
        "reconstructed_history": {
            "included": False,
            "label": "reconstructed, look-ahead contaminated",
        },
        "snapshot_refreshes": len(refreshes),
        "monthly_score_snapshots": len(monthly_refreshes),
        "primary_horizon": CONFIG["primary_horizon"],
        "primary_target": "sector_residual_return_over_trading_sessions",
        "primary_variants": primary_variants,
        "variants": variants,
        "variants_label": "calendar_day_horizon_raw_return_secondary_diagnostic",
        "comparison": {
            label: {
                "champion_mean_rank_ic": variants["champion"][label]["mean_rank_ic"],
                "challenger_mean_rank_ic": variants["challenger"][label]["mean_rank_ic"],
                "eligible": (variants["champion"][label]["status"] == "eligible"
                             and variants["challenger"][label]["status"] == "eligible"),
            }
            for label in CONFIG["horizons_days"]
        },
    }


def write_report(report=None):
    report = report or build_report()
    save_json(PUBLIC_NAME, report)
    return report


def rows_from_advisor(payload):
    """Merge public rows with the latest raw PIT inputs without inventing score history."""
    rows = [*(payload.get("research") or []), *(payload.get("screen_universe") or []),
            *(payload.get("portfolio_coverage") or [])]
    raw = {row["ticker"]: row for row in raw_pit_store.latest_snapshots(payload.get("universe"))}
    return [{**raw.get(row.get("ticker"), {}), **row} for row in rows]


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", default=os.path.join(DATA_DIR, "advisor.json"))
    parser.add_argument("--append-current", action="store_true")
    parser.add_argument("--refresh-id")
    args = parser.parse_args(argv)
    with open(args.snapshot) as handle:
        payload = json.load(handle)
    if args.append_current:
        recorded_at = datetime.now(timezone.utc).isoformat()
        append_refresh(
            rows_from_advisor(payload),
            refresh_id=args.refresh_id or f"initial-{payload.get('generated_at')}",
            recorded_at=recorded_at,
            data_as_of=payload.get("generated_at"),
            universe=payload.get("universe") or [],
            published={row.get("ticker") for row in payload.get("research", [])},
            model_version=payload.get("model_version"),
            config_hash=(payload.get("model_metadata") or {}).get("config_hash"),
        )
    report = write_report()
    print(f"IC harness: {report['snapshot_refreshes']} snapshots, "
          f"{report['variants']['champion']['1M']['periods_accumulated']} eligible 1M periods")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
