# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

ValueSignal (repo name `Dash`) is a static React research dashboard backed by a Python batch
pipeline. The pipeline scores a ~910-name US equity universe on a 0–100 "research score"
(fundamentals-first, then market behavior and news sentiment), plus a separately-modeled ~125-fund
ETF watchlist and several thematic/factor screens. There is no application server or database:
`public/data/*.json` (committed to the repo) is the entire product surface. The pipeline runs on a
GitHub Actions schedule (`refresh-advisor.yml`) and commits its own output back to `main`. Firebase
handles auth, portfolio, and watchlist storage; three Netlify Functions handle the few things that
need a server (dispatching a manual refresh, proxying live quotes, pushing alerts).

Read `docs/SYSTEM-SETUP.md` first for a full architecture and data-flow walkthrough, and
`README.md` for the scoring model in prose. `docs/DEPLOYMENT.md` is the deployment runbook.
`docs/MODEL-CARD.md` and `docs/LIMITATIONS.md` state what the score does and does not mean —
read before changing anything that affects ranking, confidence, or published claims.

**`docs/` is authoritative. Root-level `*.md` files other than `README.md`, `MIGRATION.md`, and
`TODO.md` (e.g. anything under `APP-COMPLETE-BREAKDOWN.md`-style audit reports) are historical
snapshots from earlier phases and may be stale — several say so explicitly in their own text.**

## Commands

### JavaScript / React (repo root)

```bash
npm ci                  # install
npm run dev              # vite dev server
npm run build             # production build (also validates rolldown chunking in vite.config.js)
npm run lint               # eslint .
npm test                    # vitest run — runs *.test.{js,jsx} across src/, tests/functions/, netlify/
npm test -- src/lib/scoreBands.test.js       # single file
npm test -- -t "some test name"                # single test by name
npm run docs:breakdown                          # regenerate APP-COMPLETE-BREAKDOWN.md from source
```

Tests are colocated with source (`Foo.jsx` + `Foo.test.jsx`), except `netlify/functions/*.mjs`
(tested from `tests/functions/`).

### Python pipeline (`pipeline/`)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r pipeline/requirements.txt
cp .env.example .env.local   # fill in ALPHA_VANTAGE_API_KEY, MARKETAUX_API_TOKEN, FRED_API_KEY

PYTHONPATH=pipeline python -m pytest pipeline/tests -q                       # full suite
PYTHONPATH=pipeline python -m pytest pipeline/tests/test_scorer.py -q         # single file
PYTHONPATH=pipeline python -m pytest pipeline/tests/test_scorer.py::test_band_score -q  # single test

python pipeline/check_ui_weights.py                    # weights in settings.json vs README claims
python pipeline/validation/ic_harness.py --snapshot public/data/advisor.json  # rank-IC / ICIR check
python pipeline/validate_data.py                        # JSON Schema + cross-file contract checks
PYTHONPATH=pipeline python pipeline/validate_documentation_claims.py           # fails CI if docs claim unsupported validation

python pipeline/fetch_advisor.py         # full scoring run (network + writes public/data/advisor.json)
python pipeline/fetch_news.py
python pipeline/build_etf_comparisons.py
```

CI (`.github/workflows/ci.yml`) runs, in this order: `compileall`, `check_ui_weights.py`,
`pytest pipeline/tests`, `ic_harness.py`, `validate_data.py`, `validate_documentation_claims.py`
for the `python` job; `lint`, `test`, `build` for the `site` job. Run the matching subset locally
before pushing.

## Architecture

### Data flow

```
pipeline/fetch_advisor.py (orchestrator)
  → Yahoo/Alpha Vantage/Marketaux/FRED/SEC EDGAR providers (pipeline/*.py, cached in pipeline/data/)
  → sleeves/ + scorer.py + advisor_engine.py (scoring)
  → validate_data.py (schema + invariant checks against pipeline/schemas/*.schema.json)
  → public/data/*.json (committed — this is what the browser fetches; no API)
  → pipeline/pit_store/*.jsonl (point-in-time metric log, append-only, committed)
  → pipeline/shadow_store/ (shadow-strategy NAV history for challengers, committed)
```

The frontend (`src/`) fetches these committed JSON files directly as static assets — there is no
runtime data API to call. `src/App.jsx` is the route table; pages lazy-load except `Dashboard`
(the cold-open landing route). Firebase (`src/lib/firebase.js`, `FirebaseAuthContext.jsx`) is the
only live backend and covers auth + the user's portfolio/watchlist in Firestore; everything else
on screen is precomputed by the pipeline.

### The one non-obvious architectural fact

The pipeline does **not** compute full fundamentals for the whole universe. It computes a cheap
preliminary score for all ~910 names (price-based multiples only), ranks by that, then only
fetches financial statements (the metrics carrying most of the model's stated weight — EV/EBITDA,
ROIC, interest coverage, Piotroski F, etc.) for a shortlist of the top-ranked ~150
(`select_enrichment_priority()` in `pipeline/fetch_advisor.py`, seeded with the prior top 20 +
5 new challengers + portfolio symbols). A name that never makes the preliminary shortlist never
gets its best metrics computed, and today's ranking is partly a function of yesterday's ranking.
See `docs/SYSTEM-SETUP.md` §4.1 for the measured consequences before changing selection, enrichment
limits, or coverage/confidence logic.

### Config-driven, not code-driven

Nearly every tunable lives in `pipeline/config/*.json` (18 files; `settings.json` holds the
scoring weights) or `pipeline/themes/*.yaml` (thematic exposure declarations — adding a theme is a
new YAML file, not new code). Changing the model is usually a config edit; `check_ui_weights.py`
and `validate_documentation_claims.py` both fail CI if README/docs prose drifts from what
`settings.json` and the code actually do, so update both together.

### Contracts

`pipeline/schemas/*.schema.json` (JSON Schema draft 2020-12) define every file under `public/data/`.
`pipeline/validate_data.py` enforces both these schemas and cross-file invariants that schemas
can't express — notably the theme-screen anti-hype guardrails (price momentum must contribute
exactly zero to thematic exposure; every row must declare pass/fail). Any change to a published
JSON shape needs a matching schema update or `validate_data.py`/CI will fail.

### Validation, not backtesting

`pipeline/validation/ic_harness.py` and `pipeline/evaluation.py` measure whether a score predicts
forward returns cross-sectionally (rank information coefficient, ICIR, quantile spread), deflated
for the number of configurations tried, rather than reading a single equity curve. A scoring change
ships only if it improves out-of-sample IC after deflation — see `docs/VALIDATION-METHODOLOGY.md`.

### Netlify Functions (`netlify/functions/`, 3 total)

Each is independently authenticated — see `docs/DEPLOYMENT.md` for the exact scheme per function:
`refresh-data.mjs` (Firebase ID token + email allowlist, dispatches the GitHub Actions refresh),
`portfolio-prices.mjs` (Firebase ID token, proxies live Yahoo quotes so the browser never calls
Yahoo directly), `alert-push.mjs` (shared-secret webhook the pipeline calls post-refresh, uses
`firebase-admin` to bypass `firestore.rules` server-side by design).

### Environment variables

`VITE_*`-prefixed vars are bundled into the client build and are not secrets (Firebase web config
is meant to be public; access control is `firestore.rules`, not key secrecy). Everything else in
`.env.example` is server-only (Netlify Functions or GitHub Actions) — never add a `VITE_` prefix to
a real secret, since that would ship it to the browser.
