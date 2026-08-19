# Enrichment Pipeline Audit — Phase 1 (Investigate)

**Status: read-only investigation, no code changes in this document's commit.**
**Scope:** statement enrichment (the Yahoo-statement-derived `capital_allocation` /
`accounting_quality` / `quality` legs), why per-name data availability flips refresh-to-refresh,
and whether that flicker explains WO-5's 96.7% figure and A3's INCONCLUSIVE verdict.

---

## 0. Read this first: three premises in the work order do not match the repository

Before the 18 answers below, three things the work order states as background turned out, on
inspection of the actual code, to be either wrong or unverifiable. Each is expanded on and cited
in the relevant section, and all three are carried into `docs/QUESTIONS-FOR-OWNER.md` because they
change how later phases should be read, not because Phase 1 is blocked by them — Phase 1 was
completed against the code as it actually exists.

1. **§1 says "Yahoo primary, Alpha Vantage fallback" for statement enrichment. That path does not
   exist.** Statement enrichment (`enrich()` → `yahoo_extended()`,
   `pipeline/fetch_advisor.py:611-658`) is Yahoo-only, with **SEC EDGAR** — not Alpha Vantage — as
   its fallback (`merge_edgar_fallback`, `pipeline/edgar_enrichment.py:309-339`). Alpha Vantage
   never receives a `BALANCE_SHEET` / `INCOME_STATEMENT` / `CASH_FLOW` / `EARNINGS` request
   anywhere in this codebase (verified by grep across `pipeline/*.py`). AV is real and does run
   inside `fetch_advisor.py`, but for a different purpose, on a different 5-symbols/day shortlist,
   and — where it overlaps Yahoo at all — AV is the *primary* and Yahoo the *fallback*, the
   opposite of the work order's framing. See §A.7-8 below.
2. **§D asks about `evidence_resolution_pct` and `coverage_tier` fields, and cites "85–89%" /
   "39–45%" theme-screen numbers. Neither field exists anywhere in this repository** (`grep -rn
   "evidence_resolution_pct\|coverage_tier"` across `pipeline/`, `src/`, `public/data/`, `docs/`
   returns nothing). See §D below for what the closest real fields are and why they don't match.
3. **The work order says to read `valuesignal-round7-amendment-b.md` "first."** No file with that
   name (or `*round7*`) exists anywhere on disk. This blocks nothing in Phase 1, but it does block
   the Phase 4 cadence decision, which the work order says depends on that document's ladder/retry
   design.

None of this is a reason to stop investigating — the actual code is real, reachable, and answers
every one of the 18 questions below. It is a reason the owner needs to see before Phase 4's cadence
recommendation is written against a document that was never found. See
`docs/QUESTIONS-FOR-OWNER.md` Q1-Q3.

---

## A. Call topology

### A.1 — Entry point and trace

`pipeline/fetch_advisor.py:run()` (starts at `fetch_advisor.py:1484`) orchestrates the whole
refresh. The enrichment-specific chain is:

```
run()
  → collect() for every symbol in the refresh              (fetch_advisor.py:1118-1198)
      cheap pass: quote snapshot, 2y price history, opportunistic AV OVERVIEW/news for 5 symbols
  → select_enrichment_priority(...)                         (fetch_advisor.py:1391-1429, called at 1664)
      → enrichment_rotation(...)                             (fetch_advisor.py:1360-1388)
  → enrich(contexts, effective_extended_limit, delay, statement_priority)  (fetch_advisor.py:1201-1254, called at 1671)
      → yahoo_extended(symbol, ticker_obj, snapshot, history, diagnostics)  (fetch_advisor.py:611-658)
          → extended_inputs(ticker_obj)                       (fundamentals_extended.py:90-110)
          → ticker_obj.info
          → derive_extended(...)                              (fundamentals_extended.py:604-679)
          → merge_edgar_fallback(...)                         (edgar_enrichment.py:309-339)
```

### A.2 — Names per refresh, and how that count is set

Statement enrichment (`enrich()`'s `limit` argument) is capped at `effective_extended_limit`
(`fetch_advisor.py:1670`):

- Normal path: `extended_limit = UNIVERSE.get("extended_limit", PUBLISH_LIMIT * 3)`
  (`fetch_advisor.py:69`), where `PUBLISH_LIMIT = UNIVERSE.get("publish_limit", 20)`
  (`fetch_advisor.py:61`). `pipeline/config/settings.json`'s `universe` key is currently `{}`
  (verified), so both fall through to the code defaults: **60 names/refresh** (20 × 3).
- `FULL_UNIVERSE_RESEARCH=True` (the A3 override): every preliminary candidate, i.e. the whole
  polled universe (`fetch_advisor.py:1670`, `1410-1412`).

Within that budget of 60, `select_enrichment_priority` (`fetch_advisor.py:1391-1429`) orders who
goes first:

1. `focus_symbols` — an explicit re-rank request (`ADVISOR_FOCUS_SYMBOLS`), always first.
2. `incumbents` — the prior refresh's top 20 (`INCUMBENT_ENRICH_LIMIT = 20`, `fetch_advisor.py:71`),
   read from `previous_ranked_symbols()` (`fetch_advisor.py:1279-1286`, itself reading
   `public/data/advisor.json`'s prior `research` array).
3. `challengers` — 5 preliminary-score leaders not already incumbents
   (`CHALLENGER_ENRICH_LIMIT = 5`, `fetch_advisor.py:72`).
4. `rotation` — up to `ENRICHMENT_ROTATION_SIZE` (default 15, `ADVISOR_ENRICHMENT_ROTATION_SIZE`
   env override, `fetch_advisor.py:76`) statement-starved names, oldest-enriched-first
   (`enrichment_rotation`, `fetch_advisor.py:1360-1388`).
5. `portfolio_symbols` — user holdings, always included.

**This rotation slice already exists and is live in production** (added in commit `cd711d0c`,
2026-08-16 — after A3 was declared INCONCLUSIVE on 2026-08-07). It is a partial, already-shipped
mitigation for A3's "closed loop" concern: a name outside the top-20/5-challenger set is no longer
permanently excluded from enrichment, it just waits its turn. At 15/refresh against a ~910-name
universe, full-universe coverage takes on the order of 60 refreshes to cycle once — see
`docs/QUESTIONS-FOR-OWNER.md` Q4 for why this changes the A3 close-out recommendation.

Anything past the 60-name budget (incumbents + challengers + rotation + portfolio, then filled out
by preliminary-score rank, `enrich()`'s `ranked` list at `fetch_advisor.py:1215-1219`) is simply
not attempted this refresh — logged as `diagnostics["attempted"]` staying below `len(contexts)`,
but not itemized per skipped symbol (this is the gap the work order's `not_attempted` instrumentation
requirement closes).

### A.3 — Endpoints per name, request cost

For a name selected into the 60-name statement shortlist, `yahoo_extended` issues, via the
`yfinance` `Ticker` object:

- `ticker_obj.income_stmt`, `.balance_sheet`, `.cashflow` (annual only by default;
  `extended_inputs(ticker_obj, quarterly=False)` — quarterly triples this and is opt-in,
  `fundamentals_extended.py:90-95`) — **3 requests**
- `ticker_obj.info` — **1 request**
- `fetch_earnings_surprises` — **0 requests** unless `ENABLE_EARNINGS_SURPRISE=1`
  (`fetch_advisor.py:582`, off by default)
- `yahoo_options_volatility` — **0 requests** unless `ENABLE_OPTIONS_VOLATILITY=1`
  (`fetch_advisor.py:655`, off by default)

So **4 Yahoo requests per statement-enriched name** by default (3 statement frames + `.info`), on
top of the 2 requests every polled name already pays in `collect()` (quote snapshot, price
history — `fetch_advisor.py:1126-1127`).

Separately, the ~5 names/day in `alpha_symbols` (`fetch_advisor.py:1535`, computed from
`ALPHA_ENRICH_LIMIT` hard-capped at 5, `fetch_advisor.py:1530`) each cost up to 4 Alpha Vantage
calls in `collect()` — `OVERVIEW`, `TIME_SERIES_DAILY`, `NEWS_SENTIMENT` (only if Marketaux failed
or is unconfigured), `INSIDER_TRANSACTIONS` (`fetch_advisor.py:1139-1163`) — plus 1 for the SPY
benchmark (`fetch_advisor.py:1572`). 5 × 4 + 1 = 21 requests/day, under AV's ~25/day free-tier cap
with some margin; this shortlist is unrelated to the 60-name statement shortlist (§A.7-8).

### A.4 — Sequential or concurrent; rate limiter, backoff, sleep

**`enrich()` is sequential** (`for context in ranked[:limit]:`, `fetch_advisor.py:1224`), with a
plain `time.sleep(delay)` after each name (`fetch_advisor.py:1251`; `delay` defaults to 0 — it's
`ALPHA_VANTAGE_CALL_DELAY`, `fetch_advisor.py:1541`, actually irrelevant to the Yahoo statement
calls it's applied after). **No rate limiter and no retry wrap it.** Contrast this with the earlier
`collect()`-phase Yahoo calls:

- `yahoo_snapshot` — cached (`cache.get("quote", ...)`), retried up to 2 attempts with a 0.5s
  gap (`fetch_advisor.py:527-541`).
- `yahoo_history` — cached via `DiskCache.fetch`, with `PIPELINE_CACHE_DISABLE` opt-out
  (`fetch_advisor.py:461-486`).
- `prefetch_snapshots`/`prefetch_histories` — batched and paced through `limiter_for("yahoo")`
  (`cache.py:111-117`, a 240/min token bucket) and `retry_with_backoff` (`cache.py:347-362`,
  4 attempts, 2/4/8/16s).

**Statement enrichment (`yahoo_extended`/`extended_inputs`) uses none of this.** It calls
`ticker_obj.income_stmt` etc. directly, with no `limiter_for("yahoo").acquire()`, no
`DiskCache.fetch`, and no `retry_with_backoff`. This is the single most consequential asymmetry in
the pipeline: the data that carries most of the model's stated weight (§ "the one non-obvious
architectural fact" in `CLAUDE.md`) is fetched with the *least* resilience of any provider call in
the system, while ordinary price/quote data gets caching, batching, retry, and rate limiting. See
the flicker verdict in §F.

### A.5 — Caching, and does a failed pull overwrite a cached good value?

**Flagged prominently: statement enrichment has no cache to overwrite, and that is itself a
problem, not a mitigation.**

- `DiskCache.fetch` (`cache.py:225-245`) — the mechanism used everywhere else in the pipeline —
  is provably overwrite-safe: it only calls `self.set(...)` when `producer()` returned a
  non-`None` value (`cache.py:243-244`), and a raising producer falls back to a stale cached
  value rather than clearing it (`cache.py:236-242`). **No overwrite-on-failure defect exists in
  `DiskCache` itself.**
- `AlphaVantageClient.query` (`alpha_vantage.py:52-80`) has its own, separate, file-mtime-based
  cache (`alpha_vantage.py:14, 54-58`). It only writes the cache file after a successful,
  validated response (`alpha_vantage.py:77-79`) — a raise happens before the write
  (`alpha_vantage.py:70-76`). **Also overwrite-safe.**
- **`yahoo_extended`/`extended_inputs` do not go through either cache.** Every refresh, for every
  name in that refresh's 60-name shortlist, the 3 statement frames and `.info` are fetched fresh
  from Yahoo with **no persistence between refreshes at all**. A transient Yahoo failure this
  refresh does not "overwrite" anything — there was never a cached value to overwrite — but it
  also means a name's `coverage_tier`-equivalent state (whether `extended_coverage` resolved) is
  **entirely re-decided by whatever Yahoo does in the next few seconds**, independent of whether
  it succeeded a moment ago. That is a stronger, not weaker, flicker mechanism than a
  cache-overwrite bug would have been: a cache overwrite requires a failure to actively destroy a
  good value; this requires nothing except two consecutive independent coin-flips to disagree.

## B. Failure handling

### B.6 — Every `except` clause at the Yahoo statement call site, verbatim

```python
# fetch_advisor.py:626-633 (extended_inputs)
    try:
        inputs = extended_inputs(ticker_obj)
    except Exception as exc:  # noqa: BLE001 - extended_inputs already guards each statement call
        LOG.warn(f"{symbol}: statement frames unavailable ({type(exc).__name__}: {exc})")
        if diagnostics is not None:
            diagnostics["statement_fetch_failed"] += 1
        return merge_edgar_fallback(symbol, {}, snapshot, as_of=as_of_today, diagnostics=diagnostics)

# fetch_advisor.py:634-641 (.info)
    try:
        info = ticker_obj.info or {}
    except Exception as exc:  # noqa: BLE001
        LOG.warn(f"{symbol}: Yahoo quote-summary (.info) unavailable ({type(exc).__name__}: {exc}); "
                 "continuing with statement-only metrics")
        if diagnostics is not None:
            diagnostics["info_fetch_failed"] += 1
        info = {}

# fetch_advisor.py:642-654 (derive_extended)
    try:
        result = derive_extended(...)
    except Exception as exc:  # noqa: BLE001
        LOG.warn(f"{symbol}: extended fundamentals derivation failed ({type(exc).__name__}: {exc})")
        if diagnostics is not None:
            diagnostics["derivation_failed"] += 1
        return merge_edgar_fallback(symbol, {}, snapshot, as_of=as_of_today, diagnostics=diagnostics)

# fundamentals_extended.py:96-100 (inside extended_inputs, per statement frame)
    def frame(attr):
        try:
            return statement_series(getattr(ticker_obj, attr))
        except Exception:  # noqa: BLE001 - a missing statement must not sink the symbol
            return {"periods": [], "rows": {}}
```

Every one of these catches bare `Exception`. The outer three log a warning and increment a
diagnostics counter — reasonably well-instrumented. **The inner one
(`fundamentals_extended.py:96-100`) does neither.** If `income_stmt` succeeds and `balance_sheet`
raises, the symbol silently gets an empty balance sheet with zero log line and zero diagnostic
signal anywhere — the outer `extended_inputs` call still returns normally (it never re-raises), so
`diagnostics["statement_fetch_failed"]` never increments either. This is a confirmed instance of
"failures that are never logged anywhere" and directly muddies the coverage-flicker investigation
this work order exists to run: a name showing `extended_coverage > 0` but from only 2 of 3 statement
frames is indistinguishable, downstream, from a name that genuinely lacks a balance sheet. See the
defect table (§G, defect 1).

### B.7 — Is the Alpha Vantage fallback actually wired for statement enrichment?

**No.** Confirmed by direct trace and by grep: no call site in this repository sends
`BALANCE_SHEET`, `INCOME_STATEMENT`, `CASH_FLOW`, or `EARNINGS` to Alpha Vantage. The statement
enrichment fallback is SEC EDGAR (`merge_edgar_fallback`, called from all three failure branches
in `yahoo_extended`, `fetch_advisor.py:624-625, 632-633, 653-654, 657-658`), which fills only keys
that are still `None` after the Yahoo attempt, never overwrites a resolved value, and can be
switched off with `DISABLE_EDGAR_ENRICHMENT=1` (`edgar_enrichment.py:309-339`, especially 313,
315-316, 330).

What Alpha Vantage *is* wired to, inside `collect()` (`fetch_advisor.py:1118-1198`, gated by
`symbol in alpha_symbols`, i.e. the ≤5-name/day shortlist at `fetch_advisor.py:1535`):

- `OVERVIEW` → basic multiples (`forward_pe`, `peg`, `price_to_book`, `revenue_growth`, etc. —
  `overview_snapshot`, `fetch_advisor.py:694-745`). Here **AV is primary and Yahoo's snapshot is
  the fallback** (`merge_snapshots(primary, fallback)`, `fetch_advisor.py:1170-1171`,
  `merge_snapshots` at `748-761` only fills what `primary` left `None`/`""`) — the reverse of the
  work order's framing.
- `TIME_SERIES_DAILY` → price history, only used if it's longer than what Yahoo already returned
  (`fetch_advisor.py:1164-1167`, AV only returns 100 sessions vs Yahoo's 2 years, so this branch is
  close to unreachable in practice).
- `NEWS_SENTIMENT` → fallback news, only if Marketaux is unconfigured or failed
  (`fetch_advisor.py:1158-1161`).
- `INSIDER_TRANSACTIONS` → insider activity summary (`fetch_advisor.py:1163`).

None of these feed the `capital_allocation`/`accounting_quality`/`quality` metric families that
carry the model's stated weight and that WO-5/A3 are about. What triggers the AV branch: simple
membership in `alpha_symbols`, not a Yahoo failure — AV is attempted unconditionally for its 5
names regardless of whether Yahoo's own snapshot for that name succeeded.

### B.8 — Is 429/quota exhaustion distinguished from "no data"?

**No, confirmed on both providers that could see it, for different reasons:**

- **Alpha Vantage** (`alpha_vantage.py:63-76`): a successful HTTP 200 response is inspected for
  three keys — `"Error Message"` (bad symbol/params), `"Note"` (the classic free-tier
  rate-limit-exceeded message), and `"Information"` (AV's newer quota-exhaustion wording) — and
  **all three raise the identical `AlphaVantageError`** (`alpha_vantage.py:72-74`). An empty
  payload raises the same error type too (`alpha_vantage.py:75-76`). Every one of these is then
  caught by `fetch_optional` (`fetch_advisor.py:1094-1099`) with `except (AlphaVantageError,
  OSError, ValueError)` and turned into `{}` — quota exhaustion, an invalid ticker, and a genuinely
  empty dataset are the same outcome by the time anything downstream sees it. This is exactly the
  §2 "HTTP 429 / quota exhaustion landing in the same branch as 'no data returned'" pattern, and it
  is autonomously fixable: add a `AlphaVantageQuotaError` subclass raised only for the `Note`/
  `Information` keys, and have `fetch_optional`/diagnostics record it distinctly. See defect table,
  defect 2.
- **Yahoo (statement path)**: `yfinance` does not surface HTTP status codes to
  `yahoo_extended`/`extended_inputs` at all — every failure mode (real 429, malformed response,
  network timeout, a genuinely delisted ticker) arrives as some `Exception` subtype and is caught
  identically (§B.6). There is no status-code-level distinction to make here without changing what
  `yfinance` exposes, but the *exception type* is at least available and currently discarded beyond
  `type(exc).__name__` in a log line — it is never written to a structured diagnostic. The
  `enrichment_attempts.jsonl` instrumentation (§4 of the work order) is the correct fix for this
  side; there is no narrower autonomous fix available today.

### B.9 — Is a partial response handled differently from total failure?

**Yes, and this part is good.** `derive_extended` and every `derive_*` helper it calls
(`fundamentals_extended.py`) return `None` per-metric when that metric's specific inputs are
missing (module docstring, `fundamentals_extended.py:8-10`: "Every metric returns None when its
inputs are missing or nonsensical"), so a company with an income statement but no cash-flow
statement gets partial metrics rather than an all-or-nothing result. `enrich()` explicitly checks
`extended.get("extended_coverage")` (`fetch_advisor.py:1228`) to require *at least one* metric
resolved before counting the name as enriched — the docstring at `fetch_advisor.py:1207-1210`
documents that this used to be a bug ("`derive_extended` always returns every key, so an all-None
dict from total data starvation used to count as 'enriched'") that has since been fixed. This is a
correctly-closed prior defect, not a live one.

### B.10 — On failure, what does the scorer receive?

`None`, both by design and in practice. `fundamentals_extended.py:8-10` states the contract
explicitly and `weighted_available`/`weighted_coverage` (`scorer.py:159-163, 496-512`) are written
against `metrics.get(metric) is not None` as the coverage test. The one exception found in this
audit: `effective_tax_rate` (`fundamentals_extended.py:161-165`) returns a **statutory 0.21
constant**, not `None`, whenever the computed rate is missing *or* outside `[0.0, 0.6]`:

```python
def effective_tax_rate(income):
    rate = ratio(at(line(income, "tax_provision")), at(line(income, "pretax_income")))
    if rate is None or not 0.0 <= rate <= 0.6:
        return 0.21  # statutory federal fallback keeps NOPAT comparable across filers
    return rate
```

This feeds `derive_roic` (`fundamentals_extended.py:168-180`) as an input to NOPAT, not as a
publishable metric on its own — `return_on_invested_capital` itself still returns `None` when EBIT
is missing (line 171-172), so this specific default does not create a fake `None`→confident-value
flip at the top level the way A1-NEWS-NEUTRAL did. It does conflate two different situations
(missing tax data vs. an implausible-but-present tax rate) into one silent assumption embedded in
every ROIC figure. See §C.11 and defect table, defect 5 (instrumentation-only fix recommended;
changing the substitution itself would move a scored metric's value and is out of the autonomous
lane per §2 of the work order).

## C. The neutral-score pattern

### C.11 — Search for the A1-NEWS-NEUTRAL pattern in statement enrichment

`news_intelligence.py::weighted_sentiment` (`news_intelligence.py:129-210`) is **already fixed** —
the zero-coverage branch returns `"coverage": 0.0` explicitly (`news_intelligence.py:188`) with a
comment documenting the original 373/374 defect (`news_intelligence.py:178-182`). No live
neutral-substitution bug remains there.

Searching statement enrichment and its immediate neighbors (`fundamentals_extended.py`,
`edgar_enrichment.py`, `canonical_metrics.py`, `scorer.py`) for the same shape (`grep` for numeric
`.get(..., N)` defaults, bare `return <constant>`, and `NEUTRAL`/`neutral` identifiers) turns up
one instance inside statement enrichment and one adjacent but out-of-scope instance:

1. **`effective_tax_rate`, `fundamentals_extended.py:161-165`** — covered in §B.10 above.
2. **`_cheapness`/`opportunity_score`, `pipeline/themes.py:578-581, 590-591`** (theme screen, not
   statement enrichment) — `cheapness = 50.0 if valuation_percentile is None else 100.0 -
   valuation_percentile`. The comment at line 578-579 ("An unknown percentile scores neutral
   rather than optimistic") shows this is an intentional design choice, not an oversight, and
   `valuation_percentile is None` is itself downstream of whatever this audit finds about
   statement-enrichment coverage. Flagged for visibility since it is the same *shape* as A1, but
   it is a theme-screen concern, not an enrichment-pipeline one, and is out of this audit's scope
   per the work order's own framing (§1: "statement enrichment"). Not added to the defect table.

No other occurrence of a numeric constant standing in for a missing statement-enrichment value was
found.

### C.12 — Does the scorer separate missing-because-failed from missing-because-inapplicable?

**Yes, and C6 (cited in the work order's §7) is already closed.** `scorer.py:166-179` (the
"Retired" block) documents the fix directly: `FINANCIAL_EXEMPT`-style sector-string heuristics that
used to decide applicability independently of, and inconsistently with,
`pipeline/config/applicability_matrix.json` were removed. The comment states: "Applicability now
has exactly one authority, read by this path and the v2 path alike:
`canonical_metrics.suppressed_metrics` / `required_for_score`." In `_band_valuation_score`
(`scorer.py:565-651`), a metric the applicability registry suppresses for a given profile is forced
to `None` and **excluded from both the coverage numerator and denominator**
(`scorer.py:632-634, category_coverage` at 515-539); a metric that is merely absent (pull failed or
never attempted) stays `None` but **remains in the denominator**, correctly counting against
coverage. This is the mechanism that keeps a suppressed metric from inflating measured coverage the
way the old THG example did (`scorer.py:171` cites a Value score of 95.7 with 13/33 metrics
missing under the retired logic). No live defect found here.

### C.13 — Within-block renormalization: can less coverage score higher than full coverage?

**Yes, confirmed, and already measured by a prior audit round — this is not a new finding, but it
is worth restating precisely because the work order asks for it.** In the production default
(`normalization_mode: "bands"`, `pipeline/config/settings.json:10`), `_band_valuation_score`
(`scorer.py:565-651`) computes each category via `weighted_available` (`scorer.py:159-163`), which
renormalizes weight over whichever metrics resolved:

```python
def weighted_available(scores, weights):
    available = [(scores[k], weights[k]) for k in weights if scores.get(k) is not None]
    if not available:
        return None
    return sum(score * weight for score, weight in available) / sum(weight for _, weight in available)
```

then multiplies the category blend by `confidence_multiplier = 0.65 + (0.35 * coverage)`
(`scorer.py:642-643`). Because the multiplier only spans a 0.65–1.0 range while the renormalized
average can move much further than that when a weak metric drops out of the denominator, a name
missing its worst-scoring metrics can out-score an otherwise-identical name that has all of them.
The codebase already documents a measured instance of this: `_fixed_feature_valuation_score`'s
docstring (`scorer.py:705-722`) states "Round 4 measured Spearman(coverage, final score) at +0.44
even after statement enrichment restored 82% mean coverage, which fired the pre-committed decision
rule" and cites the resulting design of an imputation-based challenger mode
(`normalization_mode: "fixed_feature"`) that scores every name on the same metric vector and
imputes missing-but-applicable metrics at the neutral percentile instead of renormalizing. That
mode exists and is unit-tested (`scorer.py:705-782`) but **is not the production default** — see
`pipeline/config/settings.json:10, 14` (`"normalization_mode": "bands"` at top level;
`"cross_sectional"` only appears nested under a challenger config block).

**Concrete constructed example**, using the `debt_to_equity`/`interest_coverage` pair (arbitrary
two-metric illustration of the mechanism, not a real ticker):

- Company A: `debt_to_equity` scores 20/100 (highly levered — bad), `interest_coverage` resolves
  and scores 40/100 (weak coverage), both weight 1.0 → category = (20+40)/2 = **30**.
- Company B: identical business, but this refresh `interest_coverage`'s pull failed
  (`derive_extended` returned `None` for it — a genuine possibility given §A.5's finding that
  statement calls are uncached and unretried). `debt_to_equity` still scores 20/100 → category =
  20/1.0 = **20** raw, but that 20 is *not* diluted by the weak `interest_coverage` reading the way
  Company A's was. If the missing metric would have scored *below* the metrics that did resolve,
  the coverage-confidence discount (0.65 + 0.35×coverage) can still leave the less-complete company
  ahead: swap the numbers — Company A resolves both at (20, 90) → category 55, `confidence≈1.0` →
  contribution 55; Company B resolves only `debt_to_equity`=20, `interest_coverage` missing →
  category 20, coverage drops by one metric's weight share, e.g. `confidence≈0.85` → contribution
  17. That direction shows the discount working as intended. But when the *dragged-down* metric is
  the one that fails to resolve (as in the first pairing), the renormalization effect exceeds the
  confidence discount, and Company B (less coverage) scores higher than Company A (full coverage)
  on an identical underlying business. This is exactly what a coverage flicker (§A.5) would
  produce refresh-to-refresh for the same company, not just across different companies.

This is a scoring-semantics finding, not a code defect with an autonomous fix — the fix is a mode
switch the work order's §2.1 and §9 both name as requiring the owner's sign-off. Flagged for
`docs/QUESTIONS-FOR-OWNER.md` Q5, not attempted here.

## D. Coverage accounting

**Caveat repeated from §0: the field names this section's questions use
(`evidence_resolution_pct`, `coverage_tier`) do not exist in this codebase.** What follows maps the
questions onto the closest real mechanisms found, and states plainly where no equivalent exists.

### D.14 — What computes `evidence_resolution_pct` / `coverage`, and from what denominator?

No field named `evidence_resolution_pct` exists. The closest real, analogous fields:

- **`coverage`** (fundamentals-only, per row) — `weighted_coverage` (`scorer.py:496-512`): weighted
  share of *applicable* metric weight (`exempt`-filtered, i.e. suppressed metrics leave the
  denominator per §C.12) that resolved to a non-`None` value. Attempted-and-applicable is the
  denominator; a metric that was never attempted this refresh (outside the 60-name shortlist, see
  §A.2) is indistinguishable in this field from one that was attempted and failed — both are simply
  absent from `metrics`.
- **`data_coverage`** (row-level scalar blending three legs) —
  `advisor_engine.py:933-935`: `0.65 * fundamentals_coverage + 0.25 * market_behavior_coverage +
  0.10 * news_sentiment_coverage`.
- **`completeness_component`** (`data_coverage.py:43-51`) — an additive, non-scoring-affecting
  breakdown of the same blend, published for explainability (`data_coverage.py:17-19` states this
  module never changes the score, only explains it).

None of these separate "attempted and failed" from "never attempted" (§A.2's rotation-budget gap),
which is precisely the ambiguity the work order's `not_attempted` instrumentation requirement (§4)
is designed to close, and precisely why this question cannot be answered more specifically without
that instrumentation existing.

### D.15 — What sets `coverage_tier` (statements vs price_multiples)? Stored or recomputed?

No field named `coverage_tier` exists, and no two-valued `statements`/`price_multiples`
classification exists anywhere in the codebase (`grep` confirmed, §0). The nearest real signal is
`statement_source` (`edgar_enrichment.py:334-335`, set inside `merge_edgar_fallback`), a
free-text-ish field taking values `"yahoo"` (implicit, when nothing needed backfilling — not
explicitly set to this string, see below), `"yahoo+sec_edgar_pit"`, or `"sec_edgar_pit"`, plus
`derive_extended` itself setting `result["statement_source"] = "sec_edgar_pit"` at
`edgar_enrichment.py:305` when EDGAR alone resolves a name. **This is recomputed fresh every
refresh** (there's no stored/carried-forward version — `yahoo_extended` runs unconditionally for
every name inside the 60-name budget every time), which is consistent with the flicker
this work order is chasing: whatever the nearest real analogue to `coverage_tier` is, it cannot be
stable across refreshes by construction, since nothing caches or carries it forward.

### D.16 — Confirm the 39–45% cluster is "never enriched" vs "enrichment attempted and failed"

Cannot be confirmed or rejected: the 85–89%/39–45% figures do not correspond to any field this
audit could locate (§0, §D.14). If the owner can point to where those numbers were read from — a
different branch, a manual calculation, a mock-up — this can be re-run against the real thing. As
things stand today, the only way to answer this question is the same instrumentation gap noted in
D.14: `not_attempted` (outside the 60-name budget) is not currently distinguished from `attempted,
failed` anywhere in the published data or logs.

## E. Historical evidence

### E.17 — Existing logs/artifacts of past pull outcomes; preliminary failure rate

`pipeline/pit_store/*.jsonl` is the one artifact that exists today (13 daily files,
`2026-08-05.jsonl` through `2026-08-19.jsonl`, 59 total refresh snapshots after excluding 2
non-standard early refresh_ids). It is a **row-level, whole-refresh snapshot log** — it does not
record individual provider pull attempts (no `enrichment_attempts.jsonl`-equivalent exists yet;
this is exactly what the work order's §4 instrumentation adds). What it *does* let you compute,
because two consecutive refreshes' `normalized_metric_scores` can be diffed, is which metrics
flipped between present and missing for a shared ticker — this is `decompose_score_delta`
(`stability_report.py:105-131`), already built and already used once for WO-5.

Re-running the exact script WO-5 used
(`pipeline/p0_q2_turnover_attribution.py`) against the full 59-refresh pit_store (WO-5 itself only
had 2 days / 4 transitions available) gives:

```
$ PYTHONPATH=pipeline python3 pipeline/p0_q2_turnover_attribution.py
{
  "band_crossing_unchanged_value": 0.0078,
  "genuine_input_change": 0.0335,
  "availability_flicker": 0.9587
}
```

Full output at `pipeline/reports/turnover_attribution.json` (`refreshes_observed: 59`, per-transition
breakdown included). **This reconfirms WO-5's 96.7% figure almost exactly (95.87% over ~14× the
sample) — the flicker signature is not a small-sample artifact.** Per-transition detail shows real
variance (individual transitions range from 65.7% to 96.5%+ flicker share), but every single
transition has availability flicker as the dominant bucket; band-crossing never exceeds a few
percent in any transition inspected.

### E.18 — Score autocorrelation 0.891 vs. 50.8% monthly backtest turnover: how much of the gap is coverage flipping?

The 0.891/50.8% pair is from the backtest (5-year historical, monthly rebalance) — a different,
longer-horizon measurement than the pit_store's live intraday refreshes, and one this session
cannot directly re-run (the backtest needs 5 years of historical Yahoo price+statement data that,
per `pipeline/p0_q2_turnover_attribution.py`'s own docstring, is not committed to disk and cannot
be re-fetched under this session's network policy — the same constraint WO-5 hit and documented).
What can be said from what *is* measurable (§E.17): live refresh-to-refresh churn is
availability-flicker-dominated at ~96%, essentially unrelated to genuine input change (~3%) or band
quantization (~1%). If the same mechanism operates at the monthly-backtest horizon — plausible,
since nothing about `yahoo_extended`'s lack of caching/retry is specific to live refreshes — most of
the autocorrelation/turnover gap would be explained by coverage flipping rather than genuine signal
change, but this is inference from the live-refresh proxy, not a direct measurement of the backtest
series. Treat as a strong hypothesis, not a settled number, until the backtest itself can be run
with this instrumentation.

## F. Flicker verdict

**SUPPORTED**, with a mechanism, not just a correlation. Every piece of evidence in this audit
points at the same root cause:

- Statement enrichment (`yahoo_extended`) is the only Yahoo call path in the entire pipeline with
  **no cache** (§A.5) and **no retry** (§A.4), while every other Yahoo call path
  (`yahoo_snapshot`, `yahoo_history`, batch history) has both.
- A per-statement-frame failure inside that path is **silently absorbed with no log line and no
  diagnostic counter** (`fundamentals_extended.py:96-100`, §B.6), so a partial resolve this
  refresh is invisible even to the pipeline's own operators.
- Whatever resolves or doesn't resolve is **recomputed from nothing every single refresh** — there
  is no stored `coverage_tier`-equivalent state to persist (§D.15) — so two consecutive refreshes
  of the same company, with the same underlying business, can and do disagree.
- Under the production `bands` normalization mode, **less coverage can score higher than full
  coverage** (§C.13, already measured by a prior audit round at Spearman +0.44), which converts
  every one of those coverage flips into a rank-moving score change, not just a confidence-label
  change.
- Re-running WO-5's own measurement against 14× more data reconfirms its number almost exactly
  (95.87% vs. 96.7%, §E.17) — this is not a small-sample fluke.

**What would further settle it:** the `enrichment_attempts.jsonl` instrumentation from Phase 2,
run across the 5-day Phase 3 measurement window, would let §E.16/D.14/D.16-style questions be
answered directly (attempted-and-failed vs. never-attempted, per-endpoint failure rate, whether
failures cluster by research-rank decile) instead of inferred from `decompose_score_delta`'s
before/after diff. Nothing in Phase 1 found evidence *against* the working hypothesis; everything
found strengthens it.

## G. Confirmed defects

| # | Defect | Location | Severity | Proposed fix | Autonomous / escalate |
|---|--------|----------|----------|---------------|------------------------|
| 1 | Per-statement-frame failure inside `extended_inputs` is caught and silently returns an empty frame with no log line and no diagnostics counter — a partial resolve (e.g. balance_sheet fails, income_stmt succeeds) is invisible to every downstream consumer, including the diagnostics this very investigation relies on. | `fundamentals_extended.py:96-100` | High | Log a warning per failed frame (mirroring the pattern already used at the three call sites one level up, `fetch_advisor.py:626-654`) and pass a `diagnostics` dict through so a `statement_frame_partial_failure` counter (or per-frame counters) can be incremented. | **Autonomous** — only makes a distinction the code currently fails to make; adds no new behavior beyond visibility. |
| 2 | Alpha Vantage quota exhaustion (`"Note"`/`"Information"` keys) and a genuinely invalid/empty response both raise the same `AlphaVantageError`, then both collapse to `{}` in `fetch_optional` — indistinguishable from real "no data." | `alpha_vantage.py:72-76`, `fetch_advisor.py:1094-1099` | High | Add a distinct `AlphaVantageQuotaError(AlphaVantageError)` raised only for `Note`/`Information`; have `fetch_optional` catch it separately and record a `quota_exhausted` outcome rather than treating it identically to a data-absence. | **Autonomous** — this is exactly the §2 "HTTP 429/quota exhaustion landing in the same branch as no-data" example. |
| 3 | Statement enrichment (`yahoo_extended`/`extended_inputs`) has no on-disk cache, unlike every other Yahoo call path in the pipeline. This is the primary flicker mechanism (§F), not merely a missing optimization: a transient failure this refresh cannot be bridged by yesterday's known-good value the way `yahoo_snapshot`/`yahoo_history` bridge theirs. | `fundamentals_extended.py:90-110`, `fetch_advisor.py:611-658` | High | Wrap each statement-frame fetch (and `.info`) through `DiskCache.fetch`, matching the pattern already used for price history (`fetch_advisor.py:461-486`) and quotes (`fetch_advisor.py:527-541`), with a TTL appropriate to how often filings actually change (the existing `"statements"` cache namespace, `cache.py:55`, already exists and is unused by this path — it currently only serves `earnings_surprise`/`earnings_calendar`, `fetch_advisor.py:601`, `options_common.py:334`). | **Escalate candidate, leaning autonomous** — technically "only adds a distinction the code fails to make" (successful pull vs. no attempt this refresh), and the mechanism (`DiskCache.fetch`) already exists and is proven safe (§A.5). But it changes *when* a name's statement coverage updates (a stale-but-cached value could now be served instead of a fresh failure), which brushes against coverage-handling semantics named in §2.1. Recommend the owner confirm the TTL choice explicitly rather than picking one unilaterally — see `docs/QUESTIONS-FOR-OWNER.md` Q6. |
| 4 | No retry on transient Yahoo statement failures — a single exception ends the attempt for that name this refresh, with no backoff/retry the way `retry_with_backoff` (`cache.py:347-362`) provides for batch price history. | `fetch_advisor.py:611-658` | Medium | Wrap the `extended_inputs`/`.info` calls in `retry_with_backoff` (already exists, already used elsewhere, `cache.py:347-362`), same 4-attempt/2-4-8-16s pattern. | **Autonomous** — "missing retry on transient failure," directly named in §2. |
| 5 | `effective_tax_rate` silently substitutes a statutory 0.21 constant whenever the computed rate is missing *or* implausible, with no flag distinguishing "no tax data" from "data present but out of range," and no signal that a downstream ROIC figure rests on an assumption rather than a measurement. | `fundamentals_extended.py:161-165` | Low | Log/count when the fallback fires (an `assumed_effective_tax_rate` diagnostic), without changing the substitution itself. | **Autonomous for the logging only.** Changing what value ROIC computes to (e.g. returning `None` instead) would change a scored metric's value for names currently relying on this fallback — that is a scoring-semantics change per §2.1/§9 and is not attempted here. |

Defects 1, 2, 4, and 5 (logging-only) are implemented in Phase 2 in that order, one commit each,
per the work order's priority list. Defect 3 and the substitution-logic half of defect 5 are held
for the owner per `docs/QUESTIONS-FOR-OWNER.md`.

## Cross-reference: registry entries

- **WO-5** (`pipeline/reports/experiment_registry.json`, id `WO-5`): reconfirmed, not contradicted.
  Its 96.7%/0.4% figures reproduce at 95.87%/0.78% on 14× the data (§E.17). Its stated open
  question — "why does per-name data availability flip refresh-to-refresh?" — is answered by §F:
  the statement-enrichment path is the only uncached, unretried Yahoo call path in the system, and
  nothing persists a name's resolved/unresolved state between refreshes.
- **A3-FULL-UNIVERSE-ENRICHMENT** (same file, id `A3-FULL-UNIVERSE-ENRICHMENT`): its INCONCLUSIVE
  verdict predates a partial fix (`enrichment_rotation`, commit `cd711d0c`, 2026-08-16) that is
  already live in production and already gives every name a bounded, predictable path into
  enrichment instead of a permanently closed loop. See `docs/QUESTIONS-FOR-OWNER.md` Q4 for the
  recommended close-out.
