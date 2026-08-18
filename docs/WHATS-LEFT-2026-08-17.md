# Here's what's left — 2026-08-17

Continuation note for the redesign arc that started with `docs/REDESIGN-PLAN.md`
and has been tracked in `docs/REDESIGN-STATUS.md` since. That file has the full
history — every fix, every bug found, every measurement taken — and is
authoritative if the two ever disagree. This file exists so a new session
doesn't have to read all of it just to find the next task: it's a short,
forward-only "start here."

**If you only read one section, read "What's next."**

## What's done (as of today)

Everything through Phase 5's page-by-page pass — now including the last four
pages, Methodology/Glossary/Settings/Alerts — is complete, plus all of Phase 6
(dead code, payload, motion, rubric rescore — the app scored **18/20**, up
from 12/20). Full breakdown is `docs/REDESIGN-STATUS.md` §1; the short version:

- Dashboard and Portfolio got real rebuilds (duplicated apparatus removed,
  hierarchy fixed, Portfolio decomposed into `src/pages/portfolio/`).
- Picks, SwingScreen, and the rest of the screens family (20 more routes) and
  Finances/Planning/Insights/Watchlist/Markets were **screened, not rebuilt**
  — most were already well-built from earlier phases, and each pass found and
  fixed a small number of real, confirmed bugs rather than restyling working
  pages for its own sake. Worth knowing the pattern, since it'll probably hold
  for what's left too:
  - `DataTable`'s desktop `<table>` had no virtualization at all (only its
    mobile card path did) — found via Picks's 1,002-row default view, fixed
    once at the shared component, verified against 5 pages that actually
    hit the threshold.
  - Two `\u`-escape bugs (`OptionsScreen.jsx`, `CongressTrades.jsx`) where a
    unicode escape was written as bare JSX text instead of inside a string,
    so it rendered as literal backslash-u-four-hex-digits instead of the
    character.
  - A real duplicate-key data bug in `screens/momentum.json` (23 tickers
    scored twice each at different ranks) — deduped defensively in
    `ResearchScreen.jsx`; the pipeline-side root cause is still open.
  - An invalid `<details>`-inside-`<p>` HTML nesting bug in `SwingScreen.jsx`
    that silently split a paragraph and dropped its styling.
  - A hierarchy bug in `Picks.jsx` — a secondary "what-if" tool rendered
    above the primary research list.
  - Two stale doc claims corrected (Picks' metric disclosure, Institutional
    Activity's empty state) — both already fixed in code, the doc just
    hadn't caught up.
  - `Methodology.jsx`'s weight-stack bar clipped the `news_sentiment` label
    mid-word — its 4% segment (fixed in `pipeline/config/settings.json`,
    permanent, not a data artifact) was too narrow for "4% news" to fit on
    one line. Fixed by dropping the label text below a width threshold
    (bare "4%", full label in a `title` tooltip) plus a defensive
    nowrap/ellipsis CSS floor for any future narrow segment.
  - `design/appshot.mjs`, `design/a11ycheck.mjs`, `design/typefloor.mjs` all
    imported Chromium from a hardcoded, machine-specific npx-cache path
    (`/Users/eyerise/.npm/_npx/<hash>/...`) that only existed on the machine
    that first wrote them — the scripts would fail to even import on any
    other machine or cloud session. Switched to `import { chromium } from
    'playwright-core'`, an existing `package.json` devDependency, so `npm ci`
    is all a new environment needs (plus a Chromium binary — see below).
    Re-verified all three against a running dev server after the swap:
    `appshot.mjs`, `a11ycheck.mjs`, and `typefloor.mjs` all ran clean.

All of the above is committed to `main` with full verification each time:
`npm run lint && npm test && npm run build`, `design/typefloor.mjs` (11px
floor), `design/a11ycheck.mjs` (keyboard/modal/unnamed-control check), and
live screenshots in both themes wherever the page isn't Firebase-gated.

## What's next

In priority order. **1 and 2 are both done as of 2026-08-17** — kept here as
the record of what was found and fixed, per this doc's own convention. **3 is
the only item actually left.**

### 1. Empty states — done (2026-08-17), one real bug found and fixed
Swept the app for empty states that render nothing useful (a blank table, a
bare dash) instead of explaining why — the last item in the Phase 5 traffic
order, per the original plan. Full account in `docs/REDESIGN-STATUS.md` §1;
short version: every `DataTable` caller across the screens family, Portfolio,
and the remaining routes was traced by hand (not just grepped) to confirm
each one either can't render zero rows in practice (fixed, config-driven
rosters like `ShadowPortfolios`/`BacktestComparison`) or already guards
`!rows.length` with a contextual `<Empty>`/inline message before reaching
`DataTable`. One real gap: `portfolio/ComparisonTables.jsx`'s `BenchmarkTable`
(the "Vs S&P 500" tab) had no empty-state check at all, while its sibling
`FixedBasisTable` (the "$N Calculator" tab, same file) already guarded
`positionCount === 0` with a "No positions yet" message — an asymmetric fix
from whenever that sibling gap was closed. With zero positions, `BenchmarkTable`
would have rendered a live `DataTable` with column headers and no rows, no
explanation. Fixed by adding the same guard `FixedBasisTable` already had.
Not visually reachable in this sandbox (Portfolio is Firebase-gated and the
dev-only `?portfolioPreview=1` bypass always seeds 4 mock positions, never
zero — see `pipeline/config/settings.json`'s `interface.mobile_preview_positions`),
so verified instead with a unit test mirroring `FixedBasisTable`'s existing
one (`ComparisonTables.test.jsx`), plus a live screenshot confirming no
regression to the populated case. Everything else swept clean — no other
changes made this pass.

### 2. Phase 4 remainder — done as of 2026-08-17, one stale claim corrected, three metrics genuinely still blocked
Full account in `docs/REDESIGN-STATUS.md`'s Phase 4 section. Both things this
item used to list are resolved or reclassified:

- **`StockDetailModal`'s score-history line was NOT a data gap — the doc note
  was stale.** `pipeline/explainability.py`'s `build_score_history()` +
  `attach_explainability()` already publish a small, bounded per-row
  `explainability.score_history` field (built from `pit_store`, the same
  cheap point-in-time source the metrics work below uses — never the deleted
  31 MB file), and `ScoreExplainability.jsx`'s `ScoreHistory` component is
  already wired into `StockDetailModal` reading exactly that field. Confirmed
  live in the browser (Search → CRUS → Explore the evidence → Research score
  over time): it correctly renders "Score history is accumulating — 1 of 6
  stored months" rather than a chart, because production hasn't accumulated
  six distinct calendar months yet — the same self-resolving "young live
  sample" state as `distribution_metrics` and `live_vs_backtest_ic` below,
  not a broken or missing feature. No code changed; this was a doc
  correction only.
- **7 more of `SignalMetricsPanel`'s metrics now carry a real numeric
  threshold**, closing all the mechanically-extractable gaps: `per_leg_ic`,
  `drop_one_leg`, `leg_correlation` and `data_quality_counters` publish a
  *count*, and each already treated "count > 0" as breach — `0` is a real,
  same-scale threshold for a count, just never stated as a number before.
  `factor_betas` and `position_reconciliation` already had a same-scale
  value/threshold pair in the code (a momentum loading vs. `-0.1`, a bps
  figure vs. `10`) that simply hadn't been passed through. `live_vs_backtest_ic`
  now compares the live IC against a *real* backtest-derived 95% confidence
  interval (mean ± `1.96 × standard_error` from the backtest panel's own IC
  series at the matching horizon — same method `ic_harness.py` already uses
  for its own interval, not a new formula) instead of the metric silently
  never setting `breached` at all, which is what it did before this pass.
  `live_vs_backtest_divergence` got a same-scale bps bound too, oriented to
  whichever side of zero the current divergence sits on (`_signed_bound()`)
  so a genuinely two-sided `|z| > threshold` test can still use the
  contract's one-sided `lt`/`gt` pair honestly. `rolling_beta_60d` and
  `sector_active_weights` each gained a **new sibling metric**
  (`rolling_beta_swing`, `sector_classification_coverage`) instead of a pair
  on the original card, because the original's `value` and its own
  `kill_threshold` are different quantities on different scales (a point
  beta vs. a swing; a largest-active-weight percentage vs. a coverage
  fraction) — pairing them would have shown one number crossing a line that
  was never about it. Verified: `pipeline/tests/test_signal_metrics.py` green
  (43 tests, +10 new), `signal_metrics.json` regenerated and confirmed live
  in both themes.
- **3 metrics remain correctly without a bullet — genuine methodology gaps,
  not left undone by oversight:** `quantile_spread`'s threshold is a shape
  condition (monotonic or not), not a magnitude; `alpha_cost_crossover`'s
  `value` is a string horizon label, not a number; `breakeven_gross_alpha`'s
  comparator ("IC-implied expected return") is still not computed anywhere
  in the codebase. **Do not fake or approximate any of these** — that rule
  is stated in `metric()`'s own docstring and was followed strictly again
  this pass.

### 3. Smaller
- `og:image`/`og:url` in `index.html` are root-relative because the deploy
  domain isn't committed to this repo — needs an absolute URL once the
  domain is known. One-line fix, just needs the actual domain.
- `*card*`-family CSS class names grew to 59 during the redesign (from an
  original 31) and would benefit from a naming-consistency pass — flagged in
  the rubric rescore, deliberately deferred, not urgent.

## How to work on this

Same verification loop as everything above — don't skip it:

```bash
npm run lint && npm test && npm run build     # must all pass

npx vite --port 5175 --strictPort              # port all three scripts assume
node design/appshot.mjs                        # ROUTES='[["/path","name"]]' TAG='x-' to target
node design/a11ycheck.mjs                      # keyboard + modal + unnamed-control check
node design/typefloor.mjs                      # 11px floor, DOM *and* scaled SVG
```

### Works unmodified in a cloud/browser Claude Code session (claude.ai/code)
The three `design/*.mjs` scripts used to hardcode a Playwright path unique to
one machine's npm cache — that's fixed (see "what's done" above): they now
import `chromium` from `playwright-core`, an existing `package.json`
devDependency, so `npm ci` alone gets the import working anywhere. The one
extra step a fresh sandbox may need is a Chromium binary if `npm ci` doesn't
already provide one:

```bash
npx playwright install chromium --with-deps    # only if chromium.launch() errors
```

**Two gotchas hit running this in a fresh claude.ai/code sandbox on 2026-08-17,
neither a code bug — both environment setup:**

- **No `.env.local` crashes the whole app, not just the Firebase-gated pages.**
  `src/lib/firebase.js` calls `getAuth(app)` at module load; with no
  `VITE_FIREBASE_API_KEY` at all (undefined, not just a placeholder), Firebase's
  own synchronous format check throws before React ever mounts — `#root` stays
  empty on every route, including ones with no Firebase dependency. `cp
  .env.example .env.local` (per this repo's own setup step above) fixes it: the
  example file's placeholder values are non-empty and colon-free, which is all
  the synchronous check requires — the graceful "Cloud data is offline" gate
  only kicks in once `getAuth` can construct successfully and its actual network
  calls fail. Restart `vite` after creating the file; it doesn't hot-reload env vars.
- **The sandbox's pre-installed Chromium can be a different revision than the
  pinned `playwright-core` expects**, and `npx playwright install chromium`
  hits a proxy-blocked host (`cdn.playwright.dev`, 403) trying to fetch the
  matching one. Symptom: `chromium.launch()` throws
  `Executable doesn't exist at .../chromium_headless_shell-<rev>`. Workaround —
  launch the pre-installed binary directly instead of the one the package
  resolves by default: `chromium.launch({ executablePath:
  '/opt/pw-browsers/chromium', args: ['--no-sandbox', '--disable-dev-shm-usage'] })`.
  The revision mismatch didn't break anything (CDP is compatible across close
  Chrome versions); without `--no-sandbox` as root in a container, Chromium
  silently produced blank white screenshots instead of erroring. This needed
  copying the three `design/*.mjs` scripts to add the override, running them,
  then deleting the copies — don't commit a hardcoded `/opt/pw-browsers` path
  into the tracked scripts, that's exactly the machine-specific-path problem
  the earlier `playwright-core` portability fix (see "what's done" above) removed.

Everything else in this doc — reading source, grepping, running the dev
server on a free port, running lint/test/build, committing, pushing — needs
nothing browser-specific. There's no reason this work can't run end-to-end in
a claude.ai/code session; it was written and last verified from a local CLI
session, but nothing here depends on that specifically.

Firebase is offline in local dev, so Portfolio, Diversification, Finances,
Planning, Insights, and Watchlist all render their "Cloud data is offline"
empty state rather than real content — that's expected, not a bug, and those
empty states have already been confirmed to be real, designed states rather
than blank pages. Two known-failing pipeline tests predate the redesign
entirely (`test_benchmark_suite.py`, `test_themes.py`) — don't chase them as
regressions.

Measure before fixing. Nearly every real bug found this session was found by
actually loading the page and looking — in a browser via Playwright, or by
reading the underlying JSON directly — not by assuming a doc note or an old
audit was still accurate. Several weren't.
