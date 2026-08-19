# Questions for the owner — Enrichment Pipeline Investigation, Phase 1

Batched once, per the work order's §2. Full findings and citations are in
`docs/ENRICHMENT-PIPELINE-AUDIT.md`; this file states each decision point, why it needs a human,
the options, and a recommendation. Phase 2 (fixes) is paused pending answers to Q4-Q6; Q1-Q3 don't
block Phase 2 but do block writing an honest Phase 4 report, so they're asked now rather than later.

---

## Q1 — The work order's core premise ("Yahoo primary, Alpha Vantage fallback") doesn't match the code. Which framing should Phase 4 use?

**Finding:** Statement enrichment — the Yahoo-derived `capital_allocation`/`accounting_quality`
metrics WO-5 and A3 are both about — has no Alpha Vantage fallback at all. It's Yahoo-only, with
SEC EDGAR as the fallback (`pipeline/edgar_enrichment.py:309-339`). Alpha Vantage is real and
running, but on an unrelated ≤5-name/day shortlist feeding basic multiples (`forward_pe`, `peg`,
etc.), where — if anything — AV is primary and Yahoo is the fallback, the reverse of the work
order's stated direction. Full detail: audit §0 and §A.7-8.

**Why it needs a decision:** The work order's §6.5 asks for "AV fallback behavior... which names
were denied fallback as a result" as a Phase 4 report section. As written, that section would be
reporting on a mechanism that doesn't exist for the metrics that matter to WO-5/A3.

**Options:**
- **(a) Recommended.** Phase 4 reports on the real mechanism (Yahoo-only statement path, SEC EDGAR
  fallback, uncached/unretried) instead of the AV-fallback framing, and separately reports the real
  AV shortlist's behavior (quota exhaustion, denied names) as its own minor section since it's a
  real, measurable thing, just not the one driving the flicker.
- (b) Treat this as a documentation-only naming mismatch and answer the work order's questions
  as literally asked, substituting "SEC EDGAR" everywhere it says "Alpha Vantage." Risks a report
  that reads as answering a different question than what actually happens.

**Recommendation:** (a). The mechanism, not the vocabulary, is what the cadence decision in Phase 4
needs to be right.

## Q2 — §D's fields (`evidence_resolution_pct`, `coverage_tier`) and the 85–89%/39–45% figures don't exist anywhere in this repository. Where should they come from?

**Finding:** Exhaustive grep across `pipeline/`, `src/`, `public/data/`, `docs/` for
`evidence_resolution_pct` and `coverage_tier` returns zero matches. No `statements`/
`price_multiples` two-valued tier field exists either. Detail: audit §0, §D.14-16.

**Why it needs a decision:** Three of the work order's 18 questions (14-16) are unanswerable as
literally posed. The audit answers them against the closest real fields it could find
(`coverage`, `data_coverage`, `statement_source`), but that's a guess at intent, not a citation of
what was actually meant.

**Options:**
- **(a) Recommended.** Confirm the audit's substitutions (`coverage`/`data_coverage`/
  `statement_source`) are what was meant, so Phase 2/4 build on the right fields.
- (b) These field names belong to a different branch, a design doc, or an in-progress UI feature
  not yet in this repo — if so, point to it and the audit will be re-run against it.
- (c) These were illustrative/hypothetical in the work order and no real equivalent is expected —
  in which case D.16 stays permanently "cannot confirm" and Phase 4 should say so rather than
  invent a number.

**Recommendation:** (a), with the audit's existing mapping, unless the owner has a specific other
source in mind.

## Q3 — `valuesignal-round7-amendment-b.md`, which the work order says to "read first," does not exist anywhere on disk.

**Finding:** No file matching `*round7*` or `*amendment*` exists in the repository (checked
exhaustively, not just an obvious path). Detail: audit §0.

**Why it needs a decision:** The work order states the rotating enrichment ladder, retry queue,
reverse-quota allocation, and — critically — the Phase 4 cadence decision ("5-day/100 or
7-day/140") all depend on that document's design. It genuinely cannot be read; this isn't a search
failure.

**Options:**
- **(a) Recommended.** The owner supplies the document (attach it, paste it, or point to where it
  lives), and Phase 4's cadence work waits for it.
- (b) Proceed without it: Phase 4 derives a cadence recommendation from the measured failure rate
  alone, using its own reasoning rather than Amendment B's retry-queue design, and states plainly
  that it could not reconcile against Amendment B.

**Recommendation:** (a). A cadence number derived without the retry-queue design it's supposed to
fit against is a number that likely needs redoing once the real document surfaces — better to wait
than to produce throwaway work.

## Q4 — A3 already has a partial fix in production. Close it as PROMOTE now, or wait for the full-universe causal test?

**Finding:** `enrichment_rotation` (`pipeline/fetch_advisor.py:1360-1388`, wired into
`select_enrichment_priority` at `1391-1429`) already ships a bounded rotation slice — 15
statement-starved names per refresh by default — that gives every name in the universe a
predictable, non-infinite path into enrichment. It was added in commit `cd711d0c` on 2026-08-16,
**after** A3 was declared INCONCLUSIVE on 2026-08-07, so the registry entry predates the fix. A3's
original blocker — "the causal question (would full-universe enrichment surface different top-40
names) is blocked_network_policy" — is still true; that specific causal test still hasn't run.

**Why it needs a decision:** §2's escalation rule 6 ("a finding contradicts a closed registry
entry") is a near-miss here — A3 isn't closed as PROMOTE/ABANDON yet (it's INCONCLUSIVE), but the
premise it was evaluated against ("the closed loop has no mitigation") is now stale, and the work
order asks Phase 4 to close A3 as PROMOTE or ABANDON.

**Options:**
- **(a) Recommended.** Close A3 as **PROMOTE**: the rotation mechanism is the practical fix for
  the bias A3 identified (a name a weaker prior model never surfaced is no longer permanently
  excluded), it's already live, and the causal "would the top-40 look different" test was always a
  nice-to-have confirmation rather than a prerequisite for shipping the fix. Note in the closure
  that the causal test remains untested and could be revisited later if the owner wants it.
- (b) Keep A3 INCONCLUSIVE / hold PROMOTE until the causal `FULL_UNIVERSE_RESEARCH=true` run
  happens (still blocked by the same network policy that blocked it in August, unless that's
  changed).
- (c) ABANDON — decide the rotation-based mitigation is sufficient and the original hypothesis
  needs no further tracking as an open registry entry at all.

**Recommendation:** (a).

## Q5 — Confirmed: under production scoring, less coverage can score higher than full coverage. No fix proposed — this is out of the autonomous lane by the work order's own rules.

**Finding:** `scorer.py`'s production `bands` mode renormalizes each fundamentals category over
whichever metrics resolved (`weighted_available`, `scorer.py:159-163`) before applying a
0.65-1.0 confidence multiplier. A prior audit round already measured this producing Spearman(coverage,
score) = +0.44 even post-enrichment (cited verbatim in `scorer.py:705-722`), and a constructed
example in the audit (§C.13) shows the mechanism directly. A `fixed_feature` (imputation-based)
challenger mode exists and doesn't have this property, but isn't the production default.

**Why it needs a decision:** §2.1 of the work order names "coverage handling... blend formula" as a
scoring-semantics change requiring the owner's sign-off, explicitly. This is not something Phase 2
touches.

**Options:**
- **(a) Recommended for this work order's scope.** Take no action now — this is real, measured,
  and already has a designed-but-unshipped fix (`fixed_feature` mode), but switching the production
  `normalization_mode` is a scoring change and outside what this investigation is chartered to do.
  Flag it for a separate, dedicated decision outside this work order.
- (b) Ask for explicit authorization to switch `normalization_mode` to `fixed_feature` as part of
  this work order anyway, since it's arguably the single highest-leverage fix for the flicker's
  *score impact* (as opposed to its *cause*, which Phase 2's fixes do address).

**Recommendation:** (a). The work order's own hard constraints (§9: "No scoring changes... if you
find yourself evaluating a choice by its effect on performance, stop") point the same direction.

## Q6 — Should statement enrichment get a cache (defect 3 in the audit)?

**Finding:** Unlike every other Yahoo call path in the pipeline, statement enrichment
(`yahoo_extended`/`extended_inputs`) has no on-disk cache — it's the audit's leading candidate for
the flicker's root mechanism (audit §F). The fix is mechanically simple (the `DiskCache.fetch`
pattern already exists, is already proven overwrite-safe, and already has an unused `"statements"`
namespace with a 7-day TTL sitting ready, `cache.py:55`), but it changes *when* a name's coverage
updates: a transient failure could now be masked by a cached success for up to the TTL, which is
exactly the kind of coverage-handling behavior change §2.1 calls out.

**Why it needs a decision:** Borderline between "the fix only makes a distinction the code
currently fails to make" (autonomous) and "changes score semantics... coverage handling"
(escalate). Leaning escalate because the *effect* on flicker measurement is large by design — this
is the fix most likely to change what Phase 3's 5-day measurement window actually finds.

**Options:**
- **(a) Recommended.** Ship it, using the existing 7-day `"statements"` TTL (already the config
  default for the one thing that does cache statement-adjacent data today, `earnings_surprise`).
  Rationale: filings genuinely don't change intraday or even daily for the overwhelming majority of
  names, so a 7-day cache mirrors reality rather than papering over a real signal — and it is the
  single fix most likely to be the actual root cause per the audit's evidence chain.
- (b) Ship it with a shorter TTL (e.g. 24h) to limit how long a stale-but-cached value can stand in
  for a fresh attempt, at the cost of a smaller flicker reduction.
- (c) Don't ship it in Phase 2 at all — measure Phase 3 against the *uncached* system first (closer
  to "the repaired system" the work order's §4 intends, since defects 1/2/4/5 alone don't touch
  this path), then consider caching as a follow-up work order once the size of the problem without
  it is known.

**Recommendation:** (a) — but this is explicitly the one the owner should pick, not the one Phase 2
should assume.

---

**If Q4-Q6 are answered, Phase 2 proceeds:** defects 1, 2, 4, and 5 (logging-only) from the audit's
table ship regardless, one commit each, each with a failing-then-passing test, as directed by the
work order regardless of these answers (none of them touch scoring, universe membership, or a
without-first-principles threshold). Defect 3 (the cache) and the fixed_feature mode question (Q5)
wait for this batch.
