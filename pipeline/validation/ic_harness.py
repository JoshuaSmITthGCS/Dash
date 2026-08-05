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
from evaluation import deflated_sharpe_ratio, pearson, rank  # noqa: E402
import pit_store as raw_pit_store  # noqa: E402


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


def _modifier_contract(detail):
    """Keep original detail and add an explicit zero-inclusive modifier point map."""
    detail = dict(detail or {})
    applied = detail.get("applied") or {}
    detail["all_points"] = {
        name: applied.get(name, 0.0)
        for name in CONFIG["modifier_fields"]
    }
    return detail


def snapshot_row(row, *, refresh_id, recorded_at, data_as_of, universe, published,
                 model_version, config_hash):
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
            "champion": _modifier_contract(row.get("modifiers")),
            "challenger": _modifier_contract(challenger.get("modifiers")),
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
                   published=(), model_version=None, config_hash=None, root=PIT_ROOT):
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
    snapshots = [snapshot_row(
        row,
        refresh_id=refresh_id,
        recorded_at=recorded_at,
        data_as_of=data_as_of,
        universe=universe,
        published=published,
        model_version=model_version,
        config_hash=config_hash,
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
            })
        if scored:
            periods.append({"date": start["recorded_at"][:10], "rows": scored})
    return periods


def _spearman(left, right):
    if len(left) < 3:
        return None
    return pearson(rank(left), rank(right))


def _buckets(rows, count):
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
                "mean_forward_return": mean(row["forward_return"] for row in chunk),
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


def evaluate_variant(refreshes, variant, horizon_days):
    periods = _forward_periods(refreshes, variant, horizon_days)
    ic_values, leaks, bucket_periods, spreads = [], [], defaultdict(list), []
    for period in periods:
        rows = period["rows"]
        ic = _spearman([row["score"] for row in rows], [row["forward_return"] for row in rows])
        if ic is not None:
            ic_values.append(ic)
            if abs(ic) > CONFIG["lookahead_rank_ic_threshold"]:
                leak = {"date": period["date"], "rank_ic": ic,
                        "message": "Probable look-ahead or data leak. Investigate before interpreting."}
                leaks.append(leak)
                LOG.error(f"LOOK-AHEAD WARNING {variant} {period['date']}: rank IC {ic:.3f}")
        for count in CONFIG["quantile_counts"]:
            buckets = _buckets(rows, count)
            for bucket in buckets:
                bucket_periods[(count, bucket["bucket"])].append(bucket["mean_forward_return"])
            if count == CONFIG["quantile_counts"][0] and len(buckets) == count:
                spreads.append(buckets[-1]["mean_forward_return"]
                               - buckets[0]["mean_forward_return"]
                               - CONFIG["long_short_cost_bps"] / 10_000)
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
    return {
        **_ic_summary(ic_values),
        "monthly_rank_ic": ic_values,
        "probable_lookahead_flags": leaks,
        "bucket_returns": bucket_output,
        "long_short_top_minus_bottom_quintile": {
            "mean_net_return": mean(spreads) if spreads else None,
            "cost_bps": CONFIG["long_short_cost_bps"],
        },
        "deflated_sharpe_probability": deflated_sharpe_ratio(
            spread_sharpe,
            observations=len(spreads),
            trials=CONFIG["shadow_strategy_trials"],
        ) if spread_sharpe is not None else None,
        **_turnover_and_stability(periods),
    }


def build_report(rows=None):
    rows = read_snapshots() if rows is None else rows
    refreshes = _refreshes(rows)
    monthly_refreshes = _monthly_refreshes(refreshes)
    variants = {variant: {} for variant in ("champion", "challenger")}
    for variant in variants:
        for label, days in CONFIG["horizons_days"].items():
            variants[variant][label] = evaluate_variant(monthly_refreshes, variant, days)
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
        "variants": variants,
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
