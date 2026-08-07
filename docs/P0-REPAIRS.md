# P0 — Repairs (Phase 1)

Three structural fixes made before any diagnostic measurement, because each changes what later
numbers mean. This file is appended to after each work order.

---

## WO-1 — Manifest reported the wrong model

**Defect confirmed.** `pipeline/observability.py:30` built `run_manifest.score_distribution` from
`row["analysis_v2"]["structural"]["effective_score"]` — the shadow v2 canonical-metrics score —
instead of `row["score"]`, the published champion score shown in the UI and used for ranking.

**Fix.** Changed line 30 to read `row.get("score")`. One line.

**Regression test.** `pipeline/tests/test_observability.py`, two cases:
1. A synthetic payload where champion `score` and v2 `effective_score` diverge — asserts the
   manifest's `score_distribution` tracks `score`, not the shadow field.
2. Loads the committed `public/data/advisor.json` and asserts a freshly regenerated manifest's
   `score_distribution` matches the min/max/mean of the published champion `research[].score`
   values within tolerance. `skipTest`s if the artifact isn't present in the checkout.

**Verification.** Regenerated the manifest from the current `public/data/advisor.json`:

| | Before (buggy, as published) | After (fixed, regenerated) | Actual champion `research[].score` |
|---|---:|---:|---:|
| count | 40 | 40 | 40 |
| minimum | 60.0 | 71.4 | 71.4 |
| maximum | 77.8 | 83.4 | 83.4 |
| mean | 68.85 | 75.05 | 75.05 |

The regenerated distribution matches the published champion scores exactly (floating-point
tolerance only). The buggy figures (60.0–77.8, mean 68.85) undershoot the real range by roughly
7–11 points at every quantile — the manifest was certifying a materially different, lower-scoring
model than what shipped.

**Blast radius.** `pipeline/observability.py` was added in commit `cbc38ff` (2026-08-04), the
first commit to construct `run_manifest`. Since then, **23 commits** touched
`public/data/advisor.json`, of which **14** are `chore(data): refresh advisor research` /
`chore(data): rescore published research` commits — i.e. 14 actual pipeline runs that generated
and committed a `run_manifest.score_distribution` under the buggy code. Every one of those 14
committed manifests describes the shadow v2 score distribution, not the champion distribution
that was actually published alongside it. No other field in `run_manifest` depended on this line;
`stale_field_count`, `provider_conflict_count`, and the rest were computed from different paths
and are unaffected.

Quality gates after this fix: `pytest pipeline/tests` — 627 passed (625 pre-existing + 2 new,
0 failed); `validate_data.py` — 9 contracts validated; `npm run lint` — clean. `npm test` /
`npm run build` were not re-run for this commit since it touches no frontend code and were both
verified clean in the Phase 0 pass on this checkout (see `docs/P0-PREMISE-CHECK.md` commit); the
one known pre-existing gap — `src/App.test.jsx` failing to initialize Firebase because this fresh
checkout has no `.env.local` — is unrelated to this change and unaffected by it.

---

## WO-2 — Insider layer is dark

**Defect confirmed.** `SecEdgarClient.available` (`pipeline/sec_edgar.py:96`) is
`bool(self.user_agent)`, and `self.user_agent` reads only `os.getenv("SEC_USER_AGENT", "")`
(`sec_edgar.py:94`). The gate genuinely is the single environment variable — confirmed by reading
the source, not by assumption.

**The "Do" list was already satisfied before this session touched the repo:**
- `.env.example` already documents `SEC_USER_AGENT=YourApp research you@example.com` with an
  explanation of the SEC fair-access requirement.
- `.github/workflows/refresh-advisor.yml:68` already passes `SEC_USER_AGENT: ${{ secrets.SEC_USER_AGENT }}`
  into the scheduled refresh job.
- `docs/SYSTEM-SETUP.md:497` already lists `SEC_USER_AGENT` in the local-reproduction env var list.

No commit was needed for the three "Do" items — they predate this diagnostic pass. What remains
unset is the **secret's actual value**, in two places outside this repository's code: the
`SEC_USER_AGENT` GitHub Actions repository secret, and any local `.env.local`. Neither is something
a commit can fix; both require the repository owner to act in GitHub's repo settings (Settings →
Secrets and variables → Actions) or on their own machine.

**Verification attempted, blocked.** Set `SEC_USER_AGENT` to a real identifying string
(`ValueSignal-Research-Audit jbmsmusic05@gmail.com`) and called `SecEdgarClient.ticker_map()`
directly. Result: `URLError: Tunnel connection failed: 403 Forbidden`. Checked
`$HTTPS_PROXY/__agentproxy/status`: this session's egress policy denies CONNECT to `www.sec.gov`
and `data.sec.gov` outright (`"gateway answered 403 to CONNECT (policy denial or upstream
failure)"`) — the same denial applies to `query1.finance.yahoo.com`, `fred.stlouisfed.org`, and
`www.alphavantage.co`. This is an organization-level network policy for this session, not a defect
in the variable, the client, or a rate limit; per this environment's own operating guidance,
policy denials are reported, not retried or routed around.

**Consequence for the "Run one refresh, report symbol count and distribution" step:** skipped,
stated reason: no external data provider is reachable from this session, so no refresh (SEC-only
or full) can execute here regardless of `SEC_USER_AGENT` being set correctly. This also means the
"does it change any name's rank in the published top 40" question is unanswered.

**What would resolve it:** run `python pipeline/fetch_advisor.py` (or a narrower SEC-only harness)
with `SEC_USER_AGENT` set to a real contact string, from an environment with unrestricted egress —
a local machine, or the existing `refresh-advisor.yml` GitHub Actions workflow once its
`SEC_USER_AGENT` secret is populated. `docs/BASELINE-2026-08-06.md:64` and the current published
`public/data/advisor.json` (`source_status.sec_form4: "unavailable"`) both confirm the layer is
still dark in the last real production run, consistent with the secret being unset there too.

No code changed for this work order; no new commit. Existing quality gates are unaffected since
nothing changed.

---

## WO-3 — Wire the cost model into validation

**Defect confirmed.** `ic_harness.py` and `backtest_monthly.py` both used a flat one-way rate
(10bps) with no reference to `costs.py` anywhere in either file.

**What was wired (code, no network required):**

1. **`pipeline/backtest_monthly.py`** — added `--cost-model {flat,tiered}` and
   `--cost-scenario {optimistic,base,stress}`. `flat` (default) reproduces the exact original
   `value * turnover * transaction_cost_bps / 10000` formula — proved by a regression test that
   reconstructs the pre-cost value from the output and checks the identity holds. `tiered` prices
   every traded name's own leg through `costs.py.estimate_cost_bps()`, using that name's trailing
   60-trading-day median dollar volume and realized volatility computed from the price/volume
   history the backtest already holds in memory (`trailing_liquidity_and_volatility()`,
   look-ahead-safe: only uses data up to and including the rebalance date).
2. **`pipeline/validation/ic_harness.py`** — added `validation.cost_model` /
   `validation.cost_scenario` to `settings.json` (default `"flat"` / `"base"`, preserving the old
   constant exactly — proved by test). When `cost_model="tiered"`, the long/short top-minus-bottom
   quintile spread's cost deduction is computed per period from each top/bottom-bucket name's
   tracked `average_dollar_volume` via `costs.py`, falling back to the flat rate for any name (or
   period) missing that field.
3. **`pipeline/pit_store.py`** — added `average_dollar_volume` to `TRACKED_FIELDS` (bumped
   `validation.snapshot_schema_version` 1 → 2) so the harness's tiered path has a liquidity input
   to read once new snapshots accumulate. No `annualized_volatility` field is tracked yet, so the
   harness's tiered cost currently prices spread + fees only, not volatility-scaled market impact —
   a conservative understatement, not a fabricated volatility number, and called out here rather
   than silently shipped.

**Tests.** `pipeline/tests/test_backtest_monthly.py` (4 new cases: flat-formula equivalence,
stress > optimistic, illiquid > liquid for an equal-size trade, invalid model raises) and
`pipeline/tests/test_ic_harness.py` (3 new cases: flat default reproduces 10.0 exactly, tiered
stress prices an illiquid book above 10.0, tiered gracefully falls back to flat when volume is
untracked). Full suite: 636 passed, 0 failed.

**What could not be done: the three-regime backtest re-run.** `backtest_monthly.py` needs each of
the ~860 usable names' 5-year daily price *and volume* history to compute `tiered` costs, and
turnover/CAGR/vol/drawdown/Sharpe depend on the same history regardless of cost model. No local
price cache is committed (`pipeline/data/backtest_cache/` is empty in this checkout — it appears
the cache was simply never committed after the last real run), and this session's network policy
blocks Yahoo Finance (see WO-2's proxy-status evidence). The same block applies to an
`ic_harness.py` re-run, which is moot anyway: Phase 0 already confirmed 0 of 24 eligible periods,
so no wiring change produces a different published statistic today.

**Reproduction, once run from an environment with real internet access:**
```bash
python pipeline/backtest_monthly.py --cost-model flat   --transaction-cost-bps 10 \
    --out pipeline/reports/backtest_flat.json
python pipeline/backtest_monthly.py --cost-model tiered --cost-scenario base \
    --out pipeline/reports/backtest_tiered_base.json
python pipeline/backtest_monthly.py --cost-model tiered --cost-scenario stress \
    --out pipeline/reports/backtest_tiered_stress.json
```
Each does a fresh ~860-symbol, 10-year Yahoo fetch (`--cache-dir` persists it across retries,
`--workers` parallelizes); expect this to run well past the 90-minute production budget, per the
brief's own allowance for research runs.

**Deliverable status.** `pipeline/reports/cost_regime_comparison.json` is committed with the
wiring verified and a `status: "blocked_network_policy"` marker instead of fabricated regime
numbers — every field a real run would populate is present and `null`, with the exact commands
above to populate them. **The brief's threshold check — whether `costs.py` base wipes out more
than 200bps of annual return relative to flat 10bps at 64.9% monthly turnover — is unresolved**
and is carried into the Phase 3 verdict as the single highest-priority open item, since the brief
itself calls it "the single most important number in this phase."

Quality gates after this work order: `pytest pipeline/tests` — 636 passed, 0 failed;
`validate_data.py` — 9 contracts validated (no schema depends on the changed fields);
`npm run lint` — clean (no frontend files touched).
