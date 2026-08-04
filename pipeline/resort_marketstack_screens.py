"""Re-sorts two screens from Marketstack's own accumulated closes for the top-100
published universe, after each after-hours/pre-open collection.

Stocks (today's movers) only needs two collected sessions, so it works almost
immediately. Reversal needs roughly a quarter's worth of sessions before a 20-day
return and a 60-day drawdown mean anything - until then it honestly reports
"accumulating" rather than fabricate a screen out of two data points, the same
principle pit_store.py and the Momentum/Quality-Value screens already use.

Deliberately separate from build_momentum_screen.py (which already has two years of
real history from Yahoo and needs no waiting period) and from ETFs (a different
universe Marketstack doesn't collect, to stay inside a 100-calls/month plan).
"""

from datetime import datetime, timezone

from collect_marketstack import daily_closes
from common import LOG, save_json

REVERSAL_MINIMUM_SESSIONS = 60
MOVERS_MINIMUM_SESSIONS = 2


def _pct_change(closes, sessions_back):
    if len(closes) <= sessions_back:
        return None
    start, end = closes[-1 - sessions_back], closes[-1]
    return None if not start else round((end / start - 1) * 100, 4)


def _drawdown(closes, window=60):
    recent = closes[-window:]
    if not recent:
        return None
    peak = max(recent)
    return None if not peak else round((closes[-1] / peak - 1) * 100, 4)


def build_rows():
    """One row per ticker with whatever return/drawdown windows its accumulated
    Marketstack history can support so far."""
    rows = []
    for ticker, series in daily_closes().items():
        closes = series["closes"]
        if len(closes) < MOVERS_MINIMUM_SESSIONS:
            continue
        rows.append({
            "ticker": ticker, "sessions": len(closes), "price": closes[-1],
            "return_1d": _pct_change(closes, 1),
            "return_5d": _pct_change(closes, 5),
            "return_20d": _pct_change(closes, 20),
            "drawdown_60d": _drawdown(closes),
        })
    return rows


def rank_movers(rows, limit=40):
    """Today's biggest movers by the latest session's close-over-close change -
    distinct from Momentum (12-1 skip-month) and Reversal (pullback-then-bounce),
    and the one ranking here that doesn't need weeks of accumulated history."""
    ranked = sorted((row for row in rows if row.get("return_1d") is not None),
                    key=lambda row: abs(row["return_1d"]), reverse=True)
    return ranked[:limit]


def rank_reversal(rows, limit=10):
    """Same short-term reversal factor as the frontend's Yahoo-sourced screen
    (Jegadeesh 1990; Lehmann 1990): pulled back over 20 days, turned up this week."""
    candidates = [row for row in rows
                 if row.get("return_5d") is not None and row.get("return_20d") is not None
                 and row["return_5d"] > 0 and row["return_20d"] < 0]
    candidates.sort(key=lambda row: row["return_5d"] - row["return_20d"], reverse=True)
    return candidates[:limit]


def _screen_payload(model_version, generated_at, minimum_sessions, sessions_collected, results):
    accumulating = sessions_collected < minimum_sessions
    return {
        "schema_version": "1.0.0", "model_version": model_version,
        "generated_at": generated_at,
        "status": "accumulating" if accumulating else "success",
        **({"reason_code": "MARKETSTACK_HISTORY_ACCUMULATING"} if accumulating else {}),
        "minimum_sessions": minimum_sessions, "sessions_collected": sessions_collected,
        "results": [] if accumulating else results,
    }


def run():
    rows = build_rows()
    generated_at = datetime.now(timezone.utc).isoformat()
    sessions_collected = max((row["sessions"] for row in rows), default=0)

    movers = _screen_payload("marketstack-movers-v1.0.0", generated_at,
                             MOVERS_MINIMUM_SESSIONS, sessions_collected, rank_movers(rows))
    reversal = _screen_payload("marketstack-reversal-v1.0.0", generated_at,
                               REVERSAL_MINIMUM_SESSIONS, sessions_collected, rank_reversal(rows))
    save_json("screens/marketstack-movers.json", movers)
    save_json("screens/marketstack-reversal.json", reversal)
    LOG.info(f"Marketstack resort: {sessions_collected} session(s) collected "
             f"(movers {movers['status']}, reversal {reversal['status']})")
    return {"movers": movers, "reversal": reversal}


if __name__ == "__main__":
    run()
