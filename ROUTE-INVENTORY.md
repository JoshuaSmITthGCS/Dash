# ROUTE-INVENTORY.md

Phase 0b/0c deliverable. Behavior and data only — no appearance language. §1 is the full route
census; §2 is the consolidation proposal (the concrete judgment call); §3 is the first-viewport
recommendation (0e).

---

## §1 · Route table

One row per route or redirect currently defined in `src/App.jsx:283-330`.

| route | page | decisionServed | dataDeps | servedElsewhere | disposition | newUrl | notes |
|---|---|---|---|---|---|---|---|
| `/` | Dashboard (eager) | "How is my portfolio doing right now?" | report.json, etfs.json, screens/inside-information.json, benchmark-report.json, Firebase | no | kept | `/` | primary destination |
| `/hud-demo` | HUDDemo (DEV-only) | none — widget gallery on randomized state | none | no | n/a | `/hud-demo` | leave exactly as-is, unlinked, DEV-only (master instruction) |
| `/research` | Picks | "Which stocks should I look at?" | report.json, etfs.json, Firebase | no | kept | `/research` | primary recommendation surface — stays its own destination |
| `/search` | Search | "Find a specific ticker fast" | report.json, Firebase | yes — Research pool already lists everything | demoted→merged | `/research` | `?q=<term>` | becomes 1-tap persistent chrome landing on Research |
| `/news` | PolicyRadar | "What news touches my research?" | advisor.json | no | merged | `/markets` | `?view=news` |
| `/market` | redirect → `/news` today | (see above) | — | yes, `/news` | merged | `/markets` | `?view=news` | chain-collapses to the new URL directly |
| `/markets` | Markets | "What's happening in the broad market right now?" | report.json, etf/{SPY,QQQ,DIA,IWM}.json | no | kept | `/markets` | `?view=indexes` |
| `/portfolio` | Portfolio (view=summary) | "What do I hold and how is it doing?" | report.json, etfs.json, Firebase | no | kept | `/portfolio` | `?view=summary` |
| `/portfolio/performance` | Portfolio (view=performance) | "What is my actual return, TWR vs money-weighted?" | report.json, benchmark-report.json, Firebase | no | merged | `/portfolio` | `?view=performance` |
| `/portfolio/data-overview` | Portfolio (view=data) | "Show me every metric, and let me export them" | report.json, factors/french.json, signal_metrics.json, monte_carlo_projection.json, etf/*.json | no | merged | `/portfolio` | `?view=data` |
| `/portfolio/diversification` | Diversification | "Am I diversified? What's my factor exposure?" | report.json, etfs.json, factors/french.json, benchmark-report.json | no | merged | `/portfolio` | `?view=diversification` |
| `/portfolio/insights` | Insights | "How am I doing vs. the market, in plain language?" | report.json, etf/*.json, benchmark-report.json, etfs.json | no | merged | `/portfolio` | `?view=insights` |
| `/finances` | Finances | "Where does my money go, and how much room do I have?" | report.json, benchmark-report.json, Firebase finances | no | merged | `/portfolio` | `?view=finances` | both money-planning surfaces merge into Portfolio |
| `/planning` | Planning | "Will I retire on time, and what if I change X?" | report.json, benchmark-report.json, Firebase, worker | no | merged | `/portfolio` | `?view=planning` |
| `/screens/swing` | SwingScreen | "What's the best short/medium-horizon swing trade?" | screens/swing.json | no | merged | `/screens` | `?recipe=swing` |
| `/screens/fast-growth` | FastGrowthScreen | "What's breaking out or growing fast?" | report.json (client-ranked) | no | merged | `/screens` | `?recipe=fast-growth` |
| `/screens/options` | OptionsScreen | "What options ideas exist right now?" | screens/options.json | no | merged | `/screens` | `?recipe=options` |
| `/screens/options/{7 ids}` | StrategyScreen | (same, per-strategy) | screens/{strategy}.json + `-backtest.json` | no | merged | `/screens` | `?recipe=options&strategy=<id>` | 7 routes: short-term-trades, covered-call, cash-secured-put, protective-put, collar, vertical-spread, advanced-strategies |
| `/screens/{7 legacy ids}` | redirect → `/screens/options/{id}` today | (same) | — | yes, the /screens/options/{id} routes | merged | `/screens` | `?recipe=options&strategy=<id>` | chain-collapses to the new URL directly |
| `/screens/momentum` | ResearchScreen | "What has price momentum with quality gates?" | screens/momentum.json | no | merged | `/screens` | `?recipe=momentum` |
| `/screens/quality-value` | ResearchScreen | "What's cheap relative to its own history and peers?" | screens/quality-value.json | no | merged | `/screens` | `?recipe=quality-value` |
| `/screens/earnings` | ResearchScreen | "What has favorable near-term earnings evidence?" | screens/earnings-timeliness.json | no | merged | `/screens` | `?recipe=earnings` |
| `/screens/matrix` | ResearchScreen | "Is this durable-good or just timely?" | screens/structural-tactical.json | no | merged | `/screens` | `?recipe=matrix` |
| `/screens/early-session` | EarlySessionResearch | "Is there a validated premarket/first-hour signal?" | screens/early-session.json | no | merged | `/screens` | `?recipe=early-session` | read-only capability report; answer is currently "no, and here's why" |
| `/screens/politics` | PoliticalTrading | "What are elected officials disclosing?" | screens/congress-trades.json | no | merged | `/screens` | `?recipe=politics` |
| `/screens/institutional` | InstitutionalActivity | "What are curated institutional managers doing?" | screens/institutional-13f.json | no | merged | `/screens` | `?recipe=institutional` |
| `/screens/inside-information` | InsideInformation | "Where do political + institutional signals overlap?" | screens/inside-information.json | partially — draws from politics + institutional | merged | `/screens` | `?recipe=inside-information` |
| `/screens/themes` | ThemeExposureScreen | "What's my thematic exposure, and who's the leader?" | advisor.json, theme-peers.json | no | merged | `/screens` | `?recipe=themes` |
| `/screens/backtests` | BacktestComparison | "How do different ranking/trading methods compare retrospectively?" | screens/backtest-comparison.json | no | merged | `/evidence` | `?section=backtests` |
| `/screens/shadow` | ShadowPortfolios | "How are prospective strategies actually performing live?" | screens/shadow-portfolios.json, report.json | no | merged | `/evidence` | `?section=shadow` |
| `/screens/validation` | LiveValidation | "Has any signal been statistically validated yet?" | validation/*.json (all 6) | no | merged | `/evidence` | `?section=validation` | hosts the 64-metric report |
| `/watchlist` | Watchlist | "What am I tracking to potentially buy?" | report.json, Firestore watchlist | no | merged | `/research` | `?view=watchlist` |
| `/methodology` | Methodology | "How exactly does the score work?" | advisor.json methodology block | no | merged | `/evidence` | `?section=methodology` |
| `/glossary` | Glossary | "What does this term mean?" | advisor.json (weights only) | no | merged | `/evidence` | `?section=glossary` |
| `/settings` | Settings | "Change how the app looks/behaves for me" | PreferencesContext only | no | demoted | `/settings` | nav utility slot, 1 tap |
| `/alerts` | Alerts | "Notify me when X happens" | Firestore alerts/{uid}/* | no | demoted | `/alerts` | AlertBadge, 1 tap |
| *(none)* | `CommandCenter.jsx` | n/a — no route, no import anywhere | real data, dead controls | fully duplicates Dashboard's data pipeline | n/a | — | not a route; orphaned file, see NOTES.md |

**33 routed paths + 2 non-route orphans → 6 destinations + 2 demoted-but-live routes + 1
DEV-only unlinked route**, per §2 below.

---

## §2 · Consolidation proposal

### Destinations (six, theme-independent)

Every medium's navigation model presents exactly these six, in whatever material that medium
uses for navigation (bottom bar, top menu, edge legend, etc. — see Phase 1 DESIGN.md).

| # | Destination | Route | Absorbs | Selector scheme |
|---|---|---|---|---|
| 1 | **Home** | `/` | Dashboard | `?customize=1`, `?portfolioPreview=1` (dev) kept as-is |
| 2 | **Research** | `/research` | Picks, Search, Watchlist | `?q=<term>` (fixes the dead Alerts-produced param), `?view=picks\|watchlist` (default `picks`) |
| 3 | **Screens** | `/screens` | swing, fast-growth, momentum, quality-value, earnings, matrix, options (+7 strategies), themes, early-session, politics, institutional, inside-information — 12 ranked-list-with-a-recipe families | `?recipe=<id>`; options keeps its already-consolidated second axis `&strategy=<id>`; per-recipe filters as further params (`&tier=`, `&sector=`, `&cols=`, …) |
| 4 | **Portfolio** | `/portfolio` | summary, performance, data-overview, diversification, insights, **Finances, Planning** | `?view=summary\|performance\|data\|diversification\|insights\|finances\|planning` (default `summary`); full-width scope selector opens a sheet, per the Fidelity carry-over convention |
| 5 | **Markets** | `/markets` | Markets, News | `?view=indexes\|news` (default `indexes`) — resolves the old `/market` (singular) vs `/markets` (plural) confusion by naming both as views of one destination; both capability sets survive whole |
| 6 | **Evidence** | `/evidence` | validation (64-metric report), backtests, shadow, methodology, glossary | `?section=validation\|backtests\|shadow\|methodology\|glossary` (default `validation`) |

**Demoted-but-live** (not destinations; each reachable in exactly one interaction from
persistent chrome — satisfies the interaction budget without consuming a destination slot):

- `/alerts` — opened via the `AlertBadge` already present in global chrome (1 tap from any
  screen). All 7 rule types, quiet hours, and the push offer are unchanged.
- `/settings` — opened from the nav's utility slot. Every medium's manifest is *required* to
  expose a settings affordance (a nav-contract rule, not a per-medium choice) — this is how
  Beige Box's top menu bar, Chalkboard's chalk tray, etc. all still reach Settings in 1 tap.
- `/hud-demo` — **left exactly as-is, unlinked, DEV-only.** Binding it to real data and
  promoting it to a real destination is scope explosion outside this rebuild; the master
  explicitly permits leaving it untouched. See `NOTES.md`.

### Why Research and Evidence are NOT folded into Screens

Research (Picks) stays its own destination rather than becoming `?recipe=composite` because it
carries capabilities no other recipe has — Buy $100, the allocation planner, per-row alert
creation — and it's the primary landing surface for "what should I look at", a different
cognitive mode than a laboratory of ranked-list variants. Folding it in would flatten a real
distinction the master forbids flattening.

Evidence is a new destination name (not folded into Screens) because backtests, shadow,
validation, methodology, and glossary all answer one question — "should I trust this model at
all?" — and none of them is a ranked list of tickers. Putting a trust-audit destination next to a
candidate-discovery destination, both one tap from Home, is itself an epistemic-grammar choice:
the interface admits doubt exists as clearly as it admits candidates exist.

### "Merging never flattens distinctions" — how the ledger enforces it

The `?recipe=` selector on Screens swaps the *entire* per-recipe surface, not just a filter: each
recipe keeps its own filter panel, its own table columns, and its own disclosure set intact —
Swing's frozen-priors/decay/cost-model panel, Fast Growth's "prospective and unvalidated" note,
Early Session's gated capability report, Politics' partial-status alert, Institutional's
success-with-empty-results nuance. `CAPABILITY-LEDGER.md` enforces this mechanically: every
distinguishing row is `merged` with its *exact* selector value named, and the Phase 3 harness
asserts every one of those rows' `data-capability-id`s is present in the DOM at that exact URL —
so a recipe that quietly lost a disclosure fails the automated gate, not just a human review.

### Interaction-budget audit

Steady state = viewing any destination with navigation visible.

| From → to | Interactions | Notes |
|---|---|---|
| Destination → destination | 1 (nav tap) | 0 additional beyond the tap itself |
| Destination → a merged/moved screen inside it | destination (1) + 1 selector | e.g. Home → Screens → `?recipe=swing` = 2 total, same as today's Home → `/screens/swing` |
| Any screen → Alerts / Settings | 1 (chrome tap) | AlertBadge / nav utility slot, present on every screen |
| Any list → Stock Detail Sheet | 1 (ticker tap) | unchanged from today |
| Home → entry page (medium has one) | 1 (first load only) | per-session, not steady state |

**Nothing exceeds one additional interaction from steady state.** Rows in
`CAPABILITY-LEDGER.md` whose consolidation makes them exactly one interaction deeper than today
(every `merged` row reached through a former standalone route, e.g. `/finances` → one tap on
Portfolio's nav + one `?view=finances` selector vs. today's direct nav tap) are marked
`interactions: 1` and are the complete list for the cutover report's "rows deeper by one and
why" requirement — the answer is uniformly "it was consolidated from a former top-level route
into a view selector, exactly as the master's Hick's-Law consolidation instructs."

### Redirect map

Implemented in Phase 2a as `src/routes/redirects.js` (data-driven, consumed by the router, the
Phase 3 no-404 assertion, and a docs-consistency check).

```
/screens/momentum                     → /screens?recipe=momentum
/screens/quality-value                → /screens?recipe=quality-value
/screens/earnings                     → /screens?recipe=earnings
/screens/matrix                       → /screens?recipe=matrix
/screens/swing                        → /screens?recipe=swing
/screens/fast-growth                  → /screens?recipe=fast-growth
/screens/themes                       → /screens?recipe=themes
/screens/early-session                → /screens?recipe=early-session
/screens/politics                     → /screens?recipe=politics
/screens/institutional                → /screens?recipe=institutional
/screens/inside-information           → /screens?recipe=inside-information
/screens/options                      → /screens?recipe=options
/screens/options/<id>                 → /screens?recipe=options&strategy=<id>   (7 ids)
/screens/<7 legacy flat ids>          → /screens?recipe=options&strategy=<id>   (chain-collapse)
/screens/backtests                    → /evidence?section=backtests
/screens/shadow                       → /evidence?section=shadow
/screens/validation                   → /evidence?section=validation
/methodology                          → /evidence?section=methodology
/glossary                             → /evidence?section=glossary
/finances                             → /portfolio?view=finances
/planning                             → /portfolio?view=planning
/portfolio/performance                → /portfolio?view=performance
/portfolio/data-overview              → /portfolio?view=data
/portfolio/diversification            → /portfolio?view=diversification
/portfolio/insights                   → /portfolio?view=insights
/news                                 → /markets?view=news
/market                               → /markets?view=news   (chain-collapse)
/watchlist                            → /research?view=watchlist
/search                               → /research?q=<q>      (param mapped, not dropped)
```

`/`, `/research`, `/markets`, `/portfolio`, `/screens`, `/alerts`, `/settings`, `/hud-demo`
unchanged. Old routes stay live as redirects for one full release (master instruction); the
page *files* are never deleted anywhere in this project — retiring them is a separate later PR.

### URL-addressability rule (satisfies 0c's requirement)

Every selector listed above is read from `useSearchParams` first. Existing localStorage /
sessionStorage keys (`valuesignal.analytics.scope`, `valuesignal.analytics.view`,
`valuesignal.watchlistFilterSort`, etc. — full list in `CAPABILITY-LEDGER.md` §17) become
**default-only**: they supply the value when the URL param is absent, and are updated whenever
the param changes. This is what converts today's thin URL state (`?portfolioPreview=1`,
`?customize=1` were nearly the only two) into genuinely bookmarkable, shareable, back/forward-
correct state for every view and filter that matters.

---

## §3 · First viewport (390px, primary destination = Home)

**Current four** (per `HOMEPAGE-LAYOUT.md`): market summary strip, portfolio hero, performance
chart, multi-gauge score grid.

**Recommended three:**

1. **Portfolio value + today's delta + as-of line.** The number the session exists to answer,
   with the as-of state unambiguous at the moment someone glances at it (Peak–End Rule — the
   as-of state is what the session is judged by).
2. **The TWR-vs-benchmark performance chart, with the opportunity-cost comparison.** The master
   names this explicitly as "the primary performance work" that "stays" from the current build.
   It is also the one chart in the entire app that is guaranteed never to conflate deposits with
   return — the master's one explicit chart-honesty warning — so it is the correct chart to lead
   with, not a chart that needs a caveat to not mislead.
3. **The evidence/status strip** — *N ready · N breached · N days live · model {version}* — read
   live from `signal_metrics.json.summary` + `.live_sample` + `model_metadata`, never hardcoded.
   Tesler's Law: the model's uncertainty is irreducible, so the interface absorbs it by encoding
   it at the point of first contact rather than letting the polish of the rest of the screen imply
   more confidence than the evidence supports (the Aesthetic–Usability hazard the master names as
   "the most dangerous law for this app"). This strip is also the theme-independent seed every
   medium re-expresses in its own material: Cockpit's attribution-strip readout, Blueprint's
   title block, Chalkboard's "DO NOT ERASE" corner, Ticker's session bar — one underlying
   capability (`figure.chrome` provenance + `disclosure.chrome.no-signal-promoted`), twelve
   renderings.

**What's cut, and why it isn't a loss:**

- **Market summary strip** → moves to `/markets` (1 nav tap). It answers "what's happening in
  the market", a different decision than "how am I doing" — Home's whole first viewport should
  answer one decision, not two.
- **Multi-gauge score grid** (Portfolio score / Diversification / Resilience dials) → moves to
  `/research` (1 nav tap, `chart.home.score-gauges` in the ledger). Scores rank *candidate*
  stocks — a discovery decision — not a status decision, and four dials in the first viewport
  independently violates two standing rules: one-primary-work-per-viewport, and Miller's Law
  three-things budget for the first 390px viewport (companion doc, Miller's Law entry).

Both cut items remain fully reachable — nothing is deleted, only relocated to the destination
that actually serves the decision they answer, one tap away.
