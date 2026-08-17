# Here's what's left — 2026-08-17

Continuation note for the redesign arc that started with `docs/REDESIGN-PLAN.md`
and has been tracked in `docs/REDESIGN-STATUS.md` since. That file has the full
history — every fix, every bug found, every measurement taken — and is
authoritative if the two ever disagree. This file exists so a new session
doesn't have to read all of it just to find the next task: it's a short,
forward-only "start here."

**If you only read one section, read "What's next."**

## What's done (as of today)

Everything through Phase 5's page-by-page pass up to and including
Finances/Planning/Insights/Watchlist/Markets is complete, plus all of Phase 6
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

All of the above is committed to `main` with full verification each time:
`npm run lint && npm test && npm run build`, `design/typefloor.mjs` (11px
floor), `design/a11ycheck.mjs` (keyboard/modal/unnamed-control check), and
live screenshots in both themes wherever the page isn't Firebase-gated.

## What's next

In priority order:

### 1. Phase 5's last four pages: Methodology, Glossary, Settings, Alerts
Same traffic-order pass, same method as everything above: screenshot in both
themes, batch-scan for console errors / `\u`-escape artifacts / horizontal
overflow, read the source if something looks off, fix only what's actually
broken. Given the pattern so far, expect these to be mostly clean — check
before assuming otherwise.

### 2. Empty states — a pass of its own
The original plan calls this out as the last item in the Phase 5 traffic
order, separate from any single page: a sweep across the whole app for empty
states that render nothing useful (a blank table, a bare dash) instead of
explaining why. Two examples already found and fixed this way
(`InstitutionalActivity` turned out to already be fine on inspection — see
above); there may be others. `grep -rn "results.length ? \|!.*\.length &&"
src/pages/` is a reasonable starting point to find candidates, but verify
each one live rather than assuming from the grep.

### 3. Phase 4 remainder — real gaps, not chart-building tasks
Two separate things, both documented in full in `docs/REDESIGN-STATUS.md`'s
Phase 4 section:

- **`StockDetailModal`'s score-history line is a genuine data gap.** No
  per-row time series of the *score* is published anywhere short of the
  31 MB `score-history.json` that was already deleted this session for being
  unread. Needs an actual pipeline change: a small per-row score-history
  series, sized for the browser, added to `report_snapshot()` or similar in
  `pipeline/fetch_advisor.py`. This is Python/pipeline work, not frontend.
- **14 of `SignalMetricsPanel`'s 40 metrics still show no bullet chart,
  correctly** — `pipeline/signal_metrics.py`'s `metric()` already has the
  `kill_threshold_value`/`comparison` mechanism (added this session for the
  other 9), these 14 just don't have a valid same-scale pair yet. They split
  into three real categories, not one to-do:
  - `per_leg_ic`/`leg_correlation`/`drop_one_leg` compare a *count* against
    an implicit zero — needs a semantic decision about what to republish,
    not just extraction.
  - `rolling_beta_60d`/`sector_active_weights` compare a quantity that isn't
    `value` at all — needs a structural field change.
  - `quantile_spread`/`alpha_cost_crossover`/`breakeven_gross_alpha` have no
    numeric comparator today; `breakeven_gross_alpha`'s ("IC-implied expected
    return") isn't computed anywhere in the codebase — a methodology gap.
  - `live_vs_backtest_ic`/`live_vs_backtest_divergence` have a computable
    bound one line away but are lower priority while the live sample is
    young.

  **Do not fake or approximate any of these** — that rule is stated in
  `metric()`'s own docstring and was followed strictly the first time.

### 4. Smaller
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
