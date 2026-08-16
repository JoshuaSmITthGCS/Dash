# Phase 0 — visual direction drafts

Three standalone mockups of the same three surfaces, built per `docs/REDESIGN-PLAN.md` Phase 0.
Not routed, not imported by `src/`. Open any file directly (`file://`) — the theme button in the
top bar toggles light/dark.

| File | Direction | Positioning |
|---|---|---|
| `A-ledger.html` | **Ledger** — refined incumbent | Same cool-gray and deep green, but every figure sits on a ruled ledger and carries the coverage it was computed from. |
| `B-tape.html` | **Tape** — terminal editorial | A terminal that reads like print. Grays build every structure, one green carries every meaning, and rank becomes a position on an axis. |
| `C-studio.html` | **Studio** — soft-depth analytics | Calmer, lifted, always explaining itself: a persistent evidence rail answers "why that score" for whatever row you touch. |

Each draft shows the same three surfaces: **Dashboard**, a **Picks** table fragment, and
**Diversification as a correlation heatmap**.

## Data

`data.json` / `data.js` are extracted from `public/data/report.json` (generated 2026-08-14,
model 3.2.0). Nothing is invented:

- 40 published research rows — ticker, name, price, sector, industry, score, stance,
  component scores, fundamental-category scores, metric coverage, strengths, 24 published closes.
- Macro regime 64.3 (neutral) with its rates / inflation / labor sub-scores, and the FRED
  risk-free rates (10Y 4.68%, fed funds 3.63%).
- SPY benchmark history, 98 daily closes.
- An 8×8 **Pearson correlation matrix computed here** from the `analytics_history` closes of the
  eight top-ranked names, over their 250 most recent common trading days. The app computes this
  client-side from portfolio positions; the mockups needed a real matrix to draw, so it was
  derived from published history rather than fabricated.

Regenerate with the extraction block in the Phase 0 session, or edit `data.json` and re-emit
`data.js` as `window.VS = <json>;`.

## Screenshots

`shots/` — `<file>-<theme>.png` is the full page, `-fold` is the 1440×1000 first screen,
`frag-*` are the Picks and heatmap fragments. Regenerate:

```bash
node shot.mjs   # requires playwright; path is hardcoded to the npx cache
```

## Decision

The chosen direction (or mix) gets recorded verbatim in `design/direction-approved.md`.
Phases 1–6 read that file plus the `DESIGN.md` written from it.
