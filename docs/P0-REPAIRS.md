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

*(WO-3 to be appended after its commit.)*
