# Research Prompt — Intraday/day-trading bot: strategies, and the execution stack

A self-contained brief for a research agent, model, or collaborator. Same format and standards as
`docs/RESEARCH-PROMPT.md` (the existing brief on the long-horizon research score) — read that first
if you have not, because several of its conclusions are inputs here.

Copy everything from **§ THE PROMPT** onward if you're handing this to a model.

---

## Why this brief exists

The operator is considering adding an automated intraday / short-horizon trading capability
("TradingView-style bot") to ValueSignal. Two questions need answering before any code is written:

1. **Which short-horizon strategies actually have documented, out-of-sample, net-of-cost edge** —
   and which are folklore that survives because backtests are easy to fool.
2. **What execution stack** — broker API, market-data feed, order router, alert bridge — a single
   retail operator can actually run, and at what cost, latency, and legal footing.

This brief is written to prevent three failure modes: recommending strategies whose published edge
has already been arbitraged away, recommending an execution stack that cannot legally or
practically be run by one person on a retail account, and skipping the question of whether the
whole idea should be built at all.

---

# THE PROMPT

## Your task

Produce two deliverables:

**Deliverable A — Strategy research.** A ranked, evidence-graded survey of short-horizon
(intraday to ~5-day) systematic strategies, with an explicit verdict on which, if any, are worth
building given the constraints in § Constraints. Include the viewpoints/frameworks behind them —
market-microstructure, statistical-arbitrage, event-driven, flow-based, trend/momentum — and be
clear about which viewpoint each strategy inherits its assumptions from.

**Deliverable B — Execution stack research.** A concrete recommendation for the broker API,
market-data source, and orchestration/bridge architecture, with a runner-up and the specific
conditions under which the runner-up wins.

Both must end in a build-or-don't-build recommendation with a stated confidence.

## The system you are attaching to

A static React research dashboard backed by a Python batch pipeline. **There is no application
server and no database.** `public/data/*.json` — committed to git — is the entire product surface.
The pipeline runs on a GitHub Actions schedule three times a trading day and commits its own output
back to `main`. Firebase handles auth and stores the user's portfolio/watchlist. Three Netlify
Functions handle the only server-side work that exists: dispatching a manual refresh, proxying live
Yahoo quotes, and pushing alerts. Full architecture in `docs/SYSTEM-SETUP.md`.

The long-horizon model scores ~910 US equities on a 0–100 research score that is 78% fundamentals,
18% market behavior, 4% news sentiment. **Its 5-year backtest loses to SPY on return, volatility,
drawdown, and Sharpe simultaneously**, at 65% monthly turnover, with zero prospective validation
accumulated. See `docs/RESEARCH-PROMPT.md` and `docs/ALGORITHM-RATING-2026-08-07.md`. Treat that as
the base rate for this operator's ability to find edge with free data and a batch pipeline: it is
not encouraging, and an intraday strategy is a strictly harder problem.

## What already exists in the repo — do not redesign it, extend or replace it

Short-horizon capability is not greenfield here. Inventory it before proposing anything:

| Thing | Where | State |
|---|---|---|
| Swing screen, 2 trading days → 8 weeks | `pipeline/build_swing_screen.py`, `swing_signals.py`, `swing_tiers.py` | **Built and published.** Declares weights, citations, published gross effect sizes, a McLean–Pontiff decay haircut, and per-leg coverage. |
| Swing backtests | `pipeline/backtest_swing.py`, `backtest_swing_portfolio.py` | Built |
| Early-session research (premarket/first-hour) | `pipeline/early_session_research.py`, `pipeline/config/early_session.json` | **Capability-gated and deliberately killed.** `mode: shadow_only`; `premarket_reversal.enabled: false` with reason `NO_EXTENDED_HOURS_OHLCV`; `first_hour_reversal.enabled: false` with reason `NO_SUB_15_MINUTE_BARS`. The module refuses to synthesize intraday observations from daily closes. |
| Intraday/EOD bar collection | `pipeline/collect_marketstack.py` | Collects top-100 published tickers; the early-session module reads its actual depth rather than assuming availability |
| Entry-timing overlay | `pipeline/config/entry_timing_overlay.yaml`, `src/lib/entryTiming.js` | Built |
| Transaction-cost model (half-spread + fees + volatility-scaled impact, optimistic/base/stress) | `pipeline/costs.py`, `docs/TRANSACTION-COSTS.md` | **Built and tested but not wired into validation.** Validation still assumes a flat 10bps. |
| Alert delivery | `netlify/functions/alert-push.mjs`, `src/lib/alertRules.js`, `src/pages/Alerts.jsx` | Built (shared-secret webhook, `firebase-admin` server-side) |
| Live quote proxy | `netlify/functions/portfolio-prices.mjs` | Built (Firebase ID token; browser never calls Yahoo directly) |
| Brokerage connector design | `src/lib/fidelityConnectorStub.js` | **Design only, not implemented.** Already concludes Fidelity has no public retail API and evaluates Plaid Investments as a read-only aggregator. Read this before re-deriving it. |
| Validation machinery (rank IC, ICIR, deflated Sharpe, PBO, walk-forward with purge/embargo) | `pipeline/validation/ic_harness.py`, `pipeline/evaluation.py`, `pipeline/validation_framework.py`, `docs/VALIDATION-METHODOLOGY.md` | Built |

The pattern this repo falls into, stated so you can avoid it: **it builds excellent diagnostic
machinery and never reaches the corrective step.** The early-session module is the cleanest example
— it is honest, well-gated, and produces nothing, because the data it needs was never acquired.
Your recommendations should say what to *turn on*, not what to *specify*.

---

## Part A — Strategy questions

Answer in order. Stop early if an answer invalidates the ones below it.

### A1 — What survives cost and capacity at retail scale?

For every strategy family you consider, the first filter is arithmetic, not statistical.

- State the **gross** edge per trade in basis points, from published evidence, with the citation and
  the sample period.
- Subtract realistic retail costs: half-spread at the liquidity tier actually tradeable, exchange
  and regulatory fees, SEC/TAF fees, borrow cost if short, and slippage on marketable orders. Use
  `pipeline/costs.py`'s scenario structure (optimistic / base / stress) rather than a flat number.
- State the **decay haircut**: McLean & Pontiff (2016) found published anomaly returns decline
  ~58% post-publication. `swing_signals.py` already applies a haircut — use the same convention.
- **A strategy whose net expectancy is negative at retail spreads is dead on arrival. Say so and
  move on.** Do not carry it forward "for completeness."

Report this as a table with a net-expectancy column. Strategies that clear zero net go to A2.

### A2 — Which short-horizon effects have real out-of-sample evidence?

Survey the families below. For each: the viewpoint it comes from, the mechanism claimed, the
strongest peer-reviewed or practitioner evidence, the strongest disconfirming evidence, the data
granularity required, and whether the effect has decayed.

- **Cross-sectional short-term reversal** (1–5 day). Long-documented; heavily arbitraged; is the
  residual edge concentrated in illiquid names where costs eat it?
- **Post-earnings-announcement drift at short horizons** (the repo already scores SUE via
  `pipeline/edgar_sue.py`). Is there an intraday/next-day component distinct from the 60-day drift
  the swing screen already trades?
- **Overnight vs. intraday return decomposition.** The close-to-open / open-to-close split is one
  of the more robust documented asymmetries and — critically — is computable from **daily OHLC
  data the repo already has**. Evaluate this seriously; it may be the only intraday-adjacent
  strategy that needs no new data feed.
- **Opening-range breakout / first-hour reversal.** This is what `early_session.json` specifies and
  has disabled. Is the published evidence strong enough to justify buying the intraday data it
  needs? Be skeptical: this family is heavily represented in retail-education material and lightly
  represented in peer-reviewed literature.
- **Gap continuation vs. gap fade**, conditioned on news, volume, and gap size.
- **Intraday momentum / the "last half-hour predicts" effect** (Gao, Han, Li & Zhou-style
  intraday-momentum results). Does it survive out-of-sample and net of cost?
- **Volume/liquidity-provision strategies** (retail market-making, VWAP-reversion). Assess honestly
  whether a retail participant without a rebate schedule, colocation, or an ISO can compete — the
  answer is probably no, and saying so plainly is worth more than hedging.
- **News/sentiment-triggered momentum.** The repo has Marketaux. The long-horizon model's news
  component is inert (373 of 374 names at neutral 50.0). Does that failure mode transfer?
- **Cross-asset / ETF-vs-constituent statistical arbitrage.** The repo publishes ~125 ETFs and
  `build_etf_comparisons.py`. Capacity and cost realism required.

For each, grade the evidence: **A** (multiple independent out-of-sample replications, survives
costs), **B** (documented, but decayed or cost-marginal), **C** (practitioner folklore, no clean
out-of-sample evidence), **F** (disconfirmed). Be willing to assign C and F liberally.

### A3 — What data granularity is the binding constraint, and what does it cost?

The repo currently has: daily OHLCV (Yahoo, cached in `pipeline/data/`), Alpha Vantage at 25
calls/day, Marketaux free tier, FRED, SEC EDGAR, and whatever `collect_marketstack.py` has
actually collected. It has **no extended-hours OHLCV and no sub-15-minute bars** — those are the
two documented reason codes blocking the early-session screens.

- For each A2 strategy that survived A1, state the **minimum** data granularity that makes it work:
  daily OHLC, 15-minute bars, 1-minute bars, trades-and-quotes, full depth-of-book.
- Price each tier from current retail-accessible vendors. Verify pricing and limits against primary
  documentation, with the access date — do not quote from memory.
- **State the cheapest strategy/data pairing that produces a testable signal**, and whether any
  viable strategy requires no new data at all. That pairing is the recommendation unless something
  materially better justifies its cost.

### A4 — How would this be validated, given the repo's standards?

The repo's validation standard is non-negotiable and is documented in
`docs/VALIDATION-METHODOLOGY.md` and `docs/RESEARCH-CONTRACT.md`. A short-horizon strategy has to
meet it too, and the higher trade count changes the statistics.

- Specify the preregistered target, horizon, and universe — the equivalents of the long-horizon
  contract's 63-session sector-residual return.
- Specify purge and embargo. Overlapping intraday labels are a sharper version of the problem
  `label_overlap_periods()` already solves for the monthly model.
- Higher trade frequency means more configurations get tried, so **deflation matters more, not
  less**. State how deflated Sharpe and PBO (`pipeline/evaluation.py`) apply.
- Name the specific failure modes that destroy intraday backtests and how each is controlled:
  look-ahead via same-bar execution, bid-ask bounce masquerading as reversal alpha, survivorship
  in the intraday universe, and the absence of a same-close execution guard (`RESEARCH-CONTRACT.md`
  §3 documents this gap).
- **State the minimum live paper-trading period before real capital.** The long-horizon model has
  accumulated 0 of 24 required validation periods in its entire life. Whatever you propose must
  come with a realistic time-to-first-statistic.

### A5 — What does the regulatory and account structure actually permit?

Not optional, and not a footnote — this determines whether the strategy is buildable at all.

- **Pattern Day Trader rule**: four or more day trades in five business days in a margin account
  under $25,000 equity triggers restriction. Confirm the current rule text and thresholds against
  FINRA primary sources with an access date. State exactly how it constrains each surviving
  strategy, and what the cash-account alternative costs in settlement friction.
- Reg T margin, good-faith-violation risk in cash accounts, and settlement timing under the current
  US settlement cycle (verify the current cycle — do not assume).
- Wash-sale rules and the tax drag of high-frequency turnover on a taxable account. Quantify it:
  a strategy with 4% gross annual edge and short-term-rate tax treatment is a different proposition
  after tax.
- Whether automated order entry via the recommended broker's API is permitted for retail
  self-directed accounts under that broker's agreement, and any per-second/per-day rate limits.

---

## Part B — Execution stack questions

### B1 — Which broker APIs are actually viable for a single retail operator?

Evaluate at minimum: **Alpaca**, **Interactive Brokers** (both TWS/Gateway API and the Client
Portal Web API), **Tradier**, **TradeStation**, **Charles Schwab** (the post-TD-Ameritrade
developer platform), and **E\*TRADE**. Add any other you judge relevant, and explicitly cover
whether the operator's existing broker relationships (`src/lib/fidelityConnectorStub.js` documents
Fidelity's lack of a retail API, and `Portfolio Positions.pdf` indicates where assets sit today)
change the answer.

For each, verify against primary documentation with an access date:

- **Access**: application/approval process, account minimums, entity vs. individual, geography.
- **Auth**: OAuth vs. API key vs. session-based, token lifetime, and — critically for this repo —
  **whether it can be driven from an ephemeral GitHub Actions runner or a stateless Netlify
  Function**, or whether it requires a persistent process (IBKR's Gateway is the archetype of the
  latter and may disqualify it outright here).
- **Order support**: types, extended hours, bracket/OCO, fractional shares, options.
- **Market data**: what's bundled, real-time vs. delayed, exchange fee pass-through, redistribution
  terms.
- **Paper trading**: does it exist, is it a faithful simulation, does it share the code path?
- **Rate limits, latency, uptime history, and documented outage behavior.**
- **Cost**: commissions, data fees, PFOF/execution-quality considerations (Rule 605/606 reports).
- **Failure semantics**: idempotency of order submission, reconciliation after a dropped
  connection, what happens to open orders if the client dies. This is where automated trading
  actually loses money, and it is usually under-documented — say so if you can't determine it.

Score them in a comparison matrix and pick one, with a runner-up and the switching conditions.

### B2 — What is the right architecture, given this repo has no server?

This is the hard constraint and the most likely place a naive recommendation fails. GitHub Actions
runners are ephemeral, scheduled at coarse granularity, and not latency-guaranteed. Netlify
Functions are stateless and time-limited. Neither is a trading system.

Evaluate and compare at least these shapes:

1. **Batch-only, no intraday execution.** Signals computed by the existing pipeline, orders placed
   at open or close via a scheduled job. Lowest latency requirement, fits the current
   infrastructure, works for the overnight/close-to-open strategies from A2.
2. **TradingView Pine Script alerts → webhook → broker bridge.** This is closest to what was asked
   for. Determine: what Pine Script can and cannot compute, TradingView's alert-webhook reliability
   and rate limits, whether an alert can be delivered to a Netlify Function that places an order,
   and the security model for that endpoint. Note that `alert-push.mjs` already establishes a
   shared-secret webhook pattern in this repo — assess whether it generalizes to order entry, and
   what additional controls order entry demands that alerting does not.
3. **A dedicated always-on process** (small VPS, container host, or a broker-adjacent runtime)
   separate from the static site. State the true operational cost: monthly hosting, monitoring,
   secret rotation, on-call burden when it breaks at 09:31.
4. **An existing framework** rather than bespoke code — QuantConnect/LEAN, NautilusTrader,
   Lumibot, vectorbt, backtrader, zipline-reloaded. For each: does it solve the
   backtest-live-parity problem, what does it lock you into, and does it fit a repo whose
   validation machinery is already written in-house?

For the recommended shape, specify: where secrets live (note that `VITE_`-prefixed vars are bundled
into the client build and **must never** hold a trading credential), how the kill switch works, how
positions are reconciled against the broker as source of truth, what happens on partial fills, and
how the operator finds out when it has stopped working.

### B3 — What are the safety controls, and are they enforceable?

Enumerate the controls a system that can place real orders must have, and for each say **where in
this architecture it is enforced** and whether that enforcement can be bypassed by a bug:

- Per-order, per-day, and per-symbol position limits; max daily loss with automatic halt.
- Duplicate-order prevention and idempotency keys.
- A dry-run / paper mode that is the *same code path*, not a parallel one.
- Staleness gates — `early_session.json` already specifies `max_quote_age_seconds: 30` and
  `max_spread_pct: 1.0`; assess whether those thresholds are right for real execution.
- Manual kill switch reachable from a phone.
- An immutable order/audit log. Note that this repo's "database" is committed JSON, which is
  append-friendly but not suitable for order state — say what is.

### B4 — Read-only first?

There is a materially smaller intermediate product: a bot that generates and tracks intraday
signals, delivers them through the existing alert infrastructure, and records hypothetical fills —
**without ever placing an order.** Assess this seriously as the recommended first phase. It
produces the prospective validation record A4 demands, it carries no regulatory or capital risk,
and it reuses `alert-push.mjs` and the shadow-strategy NAV machinery (`pipeline/shadow_store/`)
that already exist. State what it would take to graduate from it to live execution, as a checklist
with numeric thresholds.

---

## Constraints your recommendations must respect

- **Free-tier or clearly-priced data.** If a recommendation needs paid data, flag it explicitly,
  give the monthly cost, and give the free-tier version alongside it.
- **No persistent compute today.** GitHub Actions (90-minute timeout, ephemeral) and Netlify
  Functions (stateless, time-limited). If your recommendation requires an always-on process, say so
  loudly and price it — do not smuggle it in.
- **Single retail operator, taxable account, no team, no vendor relationships.** Anything requiring
  ongoing manual intervention during market hours is out of scope; the point is automation.
- **Secrets never reach the browser.** `VITE_*` vars are bundled into the client build.
- **Deflation is mandatory.** Any claimed improvement is evaluated after adjusting for the number
  of configurations tried (`pipeline/evaluation.py`).
- **Verify everything against primary sources with an access date.** Broker APIs, data vendor
  pricing, and FINRA/SEC rules all change. Cite the document, not your recollection. Where you
  cannot verify something, mark it `UNVERIFIED` rather than asserting it.

## What a good answer looks like

For each recommendation:

1. **The claim**, stated so it can be falsified.
2. **The test** that would confirm or kill it — which file, which data, which statistic, which
   threshold.
3. **Expected effect size**, net of cost, with reasoning. "Improves performance" is not an answer.
4. **Cost**: engineering hours, monthly dollars, runtime, operational burden.
5. **What it would take to abandon it.**

Rank the full set by expected value per unit of effort. Separate **diagnostic** recommendations
(they tell you something) from **corrective** ones (they change outcomes), and be explicit that
this repo's failure mode is stopping after the diagnostic.

## What not to do

- **Do not recommend a strategy without a net-of-cost expectancy number.** Gross edge is not an
  argument.
- **Do not recommend anything requiring colocation, direct market access, sub-millisecond latency,
  or an exchange rebate schedule.** If your honest conclusion is that the only real intraday edge
  lives there, say that — it is a legitimate and useful finding.
- **Do not recommend machine learning as a direction** without arguing the sample-size case
  explicitly for the specific method and data volume.
- **Do not propose fitting parameters to a single backtest.** That is how this repo would acquire a
  spurious edge it cannot keep.
- **Do not restate the repo's limitations.** `docs/LIMITATIONS.md` enumerates them accurately.
- **Do not treat "TradingView bot" as the settled architecture.** It is the operator's starting
  intuition, not a requirement. If webhook-driven execution is the wrong shape, say so and say why.
- **Do not soften the base rate.** Most retail day-trading systems lose money, and the academic
  evidence on individual day-trader profitability (Barber, Lee, Liu & Odean and successors) is
  consistently negative. Engage with that literature directly rather than routing around it.

## A conclusion worth reaching

State plainly which of these you believe after doing the work:

- **A.** There is a viable net-of-cost short-horizon edge implementable on free or cheap data, with
  a specific execution stack. → Build it, phased, read-only first.
- **B.** There is an edge, but only at a data and infrastructure cost that is not justified at this
  capital base. → State the capital threshold at which it flips.
- **C.** The only defensible short-horizon addition is the overnight/close-to-open or swing-horizon
  work already partly built, and "day trading" proper should be dropped. → Say so, and specify what
  to finish instead.
- **D.** There is no edge available here; the honest move is to build the read-only signal-and-alert
  product and never place an automated order. → Say so cleanly.

**Answer D is a fully acceptable outcome and should not be avoided.** The existing documentation in
this repo is unusually honest about its own null results; a research pass that confirms another one
and says so is worth more than one that manufactures a justification for building a trading bot.

---

## Repo entry points for whoever picks this up

| Question | Start here |
|---|---|
| What the system is | `docs/SYSTEM-SETUP.md` |
| Long-horizon model's measured performance | `docs/ALGORITHM-RATING-2026-08-07.md`, `docs/RESEARCH-PROMPT.md` |
| Validation standard | `docs/VALIDATION-METHODOLOGY.md`, `docs/RESEARCH-CONTRACT.md` |
| Cost model (built, unwired) | `pipeline/costs.py`, `pipeline/cost_sensitivity.py`, `docs/TRANSACTION-COSTS.md` |
| Swing-horizon screen (2d–8w) | `pipeline/build_swing_screen.py`, `pipeline/swing_signals.py`, `pipeline/swing_tiers.py` |
| Swing backtests | `pipeline/backtest_swing.py`, `pipeline/backtest_swing_portfolio.py` |
| Early-session gating + reason codes | `pipeline/early_session_research.py`, `pipeline/config/early_session.json` |
| Intraday/EOD bar collection | `pipeline/collect_marketstack.py` |
| Entry timing | `pipeline/config/entry_timing_overlay.yaml`, `src/lib/entryTiming.js` |
| Existing webhook pattern | `netlify/functions/alert-push.mjs`, `tests/functions/` |
| Live quote proxy pattern | `netlify/functions/portfolio-prices.mjs` |
| Brokerage connector prior art | `src/lib/fidelityConnectorStub.js` |
| Shadow-strategy NAV tracking | `pipeline/shadow_store/`, `pipeline/config/shadow_strategies.json`, `src/pages/ShadowPortfolios.jsx` |
| Deflated Sharpe / PBO / walk-forward | `pipeline/evaluation.py`, `pipeline/validation_framework.py` |
| Published-JSON contracts | `pipeline/schemas/*.schema.json`, `pipeline/validate_data.py` |
| Deployment + auth schemes | `docs/DEPLOYMENT.md` |
