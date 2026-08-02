import { useData } from '../lib/useData'

const CATEGORIES = [
  ['Valuation · 28%', 'EV/EBITDA and EV/EBIT carry this bucket. The enterprise multiple is the best-validated single value measure in the published research, and enterprise multiples are capital-structure neutral, so a levered company cannot look cheap purely because debt flatters its equity ratios. PEG is now a minor sanity check rather than the largest input: it ignores the time value of money, risk, and the cost of capital. Both book-value multiples are trimmed, because book value systematically mismeasures intangible-heavy businesses, and price-to-tangible-book is scored only in the sectors it describes.'],
  ['Profitability + cash · 26%', 'ROIC leads rather than ROE: leverage inflates return on equity but cannot inflate return on invested capital. Gross profits over assets sits alongside it — measured above the line where accounting discretion operates, it has been about as predictive as book-to-market and adds information a value screen cannot. Cash conversion tests whether reported earnings arrive as money, weighted down slightly because it measures nearly the same thing as the accruals ratio.'],
  ['Financial health · 15%', 'Interest coverage and net debt to EBITDA answer the question debt-to-equity cannot: can this business comfortably service its debt at current rates? The Altman Z-score is computed with the variant fitted for the filer’s sector — the original 1968 model for manufacturers, Altman’s non-manufacturer revision otherwise — and suppressed entirely for financials, where it has no meaning.'],
  ['Accounting quality · 10%', 'The Piotroski F-score leads this bucket. The accruals ratio remains, at a much smaller weight: it is the most-studied earnings-quality flag in the literature, but its predictive power has largely decayed in US data since the early 2000s. Receivable and inventory day trends round out the check.'],
  ['Growth · 11%', 'Revenue and earnings year over year, three-year free-cash-flow growth, the direction of operating margin, and earnings surprise against expectations. Trailing growth on its own predicts forward returns weakly; the surprise component is the part that carries drift.'],
  ['Capital allocation · 10%', 'Net buyback yield after dilution, stock compensation as a share of revenue, capex against depreciation, and total asset growth. Aggressive balance-sheet expansion has historically preceded weak returns, and under-investment flatters near-term cash flow while quietly eroding competitiveness — so both tails are penalised.'],
]

const MODIFIERS = [
  ['Sector-relative valuation', '±3 points. Being cheap for a utility and being cheap outright are different claims; a percentile against sector peers separates them.'],
  ['Short interest', 'Up to −6 points. Crowded shorts are not automatically bearish, but heavily shorted stocks have underperformed lightly shorted ones by a wide margin over the following month, so the penalty is larger than a token adjustment.'],
  ['Insider activity', '+5 / −3 points. SEC Form 4 open-market trades are split into routine and opportunistic: an executive who sells every March is on a schedule, and scheduled trades have historically carried no information at all, so they score zero. Fresh clusters of irregular open-market buying score positively and decay over one to three months. Buys count for more than sells, which have many innocent explanations.'],
  ['Liquidity', 'Up to −3 points. A name you cannot exit without moving the price carries a real cost that fundamentals never show.'],
  ['Analyst expectations', '±3 points, and only where at least three analysts cover the name.'],
  ['Macro regime', '±3 points. FRED rates, inflation, labor, and yield-curve conditions are weighted by sector sensitivity and never replace company evidence. Regime timing is genuinely contested, which is why the cap is small.'],
]

const percent = (value, fallback) =>
  Math.round((typeof value === 'number' ? value : fallback) * 100)

export default function Methodology() {
  const { data } = useData('advisor.json')
  const published = data?.research?.length
  // Read the blend from the snapshot so this page cannot drift from the config that
  // produced the scores it is describing.
  const blend = data?.methodology?.weights
  const fundamentalsPct = percent(blend?.fundamentals, 0.78)
  const behaviourPct = percent(blend?.market_behavior, 0.18)
  const newsPct = percent(blend?.news_sentiment, 0.04)
  const capabilities = data?.capability_status || {
    form4_insider_transactions: { status: 'available_next_refresh', source: 'SEC EDGAR', note: 'Free Form 4 parser is included in the pipeline.' },
    implied_vs_realized_volatility: { status: 'opt_in', source: 'Option chains + calculated returns', note: 'Enable options requests in the pipeline.' },
    analyst_revision_trends: { status: 'provider_required', note: 'Point-in-time estimate history is not supplied by the current providers.' },
    guidance_beat_miss_history: { status: 'provider_required', note: 'Requires contemporaneous consensus snapshots.' },
    backlog_growth: { status: 'filing_parser_required', note: 'Backlog is issuer-specific and non-GAAP.' },
    institutional_13f_changes: { status: 'mapping_required', source: 'SEC EDGAR', note: 'Reliable CUSIP-to-ticker mapping is still required.' },
    fx_exposure: { status: 'filing_parser_required', source: 'SEC filings', note: 'Requires issuer-specific filing text normalization.' },
  }
  return <>
    <div className="page-head"><div>
      <h1 className="page-title">How the <span className="accent">score works</span></h1>
      <p className="page-sub">Transparent weights, consistent inputs, and an explicit penalty for missing evidence.</p>
    </div></div>

    <div className="grid grid-2">
      <section className="card card-pad">
        <div className="sec-label">Overall research score</div>
        <div className="weight-stack">
          <div style={{ width: `${fundamentalsPct}%` }}>{fundamentalsPct}% fundamentals</div>
          <div style={{ width: `${behaviourPct}%` }}>{behaviourPct}% behaviour</div>
          <div style={{ width: `${newsPct}%` }}>{newsPct}% news</div>
        </div>
        <p className="body-copy">
          Fundamentals dominate. Market behaviour is measured with the same arithmetic the ETF
          screen uses — 12-month momentum skipping the most recent month (to avoid the
          short-term reversal that runs against it), Sortino and Sharpe ratios on the stock’s
          own returns, relative strength versus SPY, one-year maximum drawdown, and whether
          advances carry heavier volume than declines. Low beta is rewarded rather than
          volatility punished. News sentiment is a small tilt, not a component: headline
          sentiment largely mean-reverts within days, so it is aggregated over a week and
          capped well below the other inputs.
        </p>
      </section>
      <section className="card card-pad">
        <div className="sec-label">Guardrails</div>
        <ul className="method-list">
          <li>Weights follow the strength of the published evidence for each signal, not the convenience of the data.</li>
          <li>Industry context beats universal P/E or P/S thresholds.</li>
          <li>Coverage is weighted, so a missing headline input costs far more confidence than a missing minor one.</li>
          <li>Bank balance sheets skip the industrial-company cutoffs entirely rather than failing them, and metrics that do not apply leave the coverage denominator instead of counting as missing evidence.</li>
          <li>Every published factor premium is a historical, in-sample estimate. They indicate which signals have mattered, not what any of them will return next.</li>
          <li>The top {published || 'ranked names'} come from {data?.universe_count || 'the configured'} candidates; scores do not forecast returns.</li>
        </ul>
      </section>
    </div>

    <div className="grid grid-2" style={{ marginTop: 18 }}>
      <section className="card card-pad">
        <div className="sec-label">Theme exposure is a separate screen</div>
        <p className="body-copy">
          Structural-trend exposure answers a different question from everything above: how
          exposed is this company to a multi-year demand driver? It is published as its own
          leaderboard and never folded into the research score — blending a forward-looking
          thematic bet into the fundamentals score would make that score impossible to read,
          because you could no longer tell whether a name ranked well for being cheap and
          profitable or for carrying a fashionable tag.
        </p>
        <ul className="method-list">
          <li>Exposure comes from segment revenue, the trend in how a company describes itself in its own filings, disclosed customer ties to confirmed spenders, and the capex plans of the companies writing the cheques.</li>
          <li>Share-price momentum contributes exactly zero, enforced in code and re-checked when the data is validated. Specialised thematic funds have a documented history of launching near hype peaks and losing heavily from there; reading price into a theme score is how that happens.</li>
          <li>Companies already priced in the top valuation decile of their sector are flagged, not promoted. The screen exists to find real exposure that is not yet euphoric.</li>
          <li>At least two independent signals must resolve. Segment reporting granularity is set by management and varies wildly between filers, so no single source carries a theme alone.</li>
        </ul>
      </section>
      <section className="card card-pad">
        <div className="sec-label">Validating a change to any of this</div>
        <p className="body-copy">
          A scoring change is judged on whether the score predicts forward returns across the
          universe, not on whether one backtest’s equity curve looks good. The measure is rank
          correlation between score and subsequent return, period by period, together with the
          spread between top and bottom quantiles and whether the quantiles line up in order.
        </p>
        <ul className="method-list">
          <li>Fundamentals are recorded point-in-time on every run, with restatements kept in a separate revision log, so future backtests can score on what was actually known at the time.</li>
          <li>Universe membership is snapshotted too, delisted names included, so a backtest cannot quietly run on survivors only.</li>
          <li>Results are deflated for the number of configurations tried. Test enough weightings and one looks good by construction; the significance bar is raised to account for that.</li>
          <li>A change ships only if it improves out-of-sample performance after that deflation, regardless of how good it looks in sample.</li>
        </ul>
      </section>
    </div>

    <div className="sec-label" style={{ marginTop: 28 }}>Fundamental framework</div>
    <div className="grid grid-2">
      {CATEGORIES.map(([title, body]) => (
        <section className="card card-pad" key={title}>
          <h2 className="method-title">{title}</h2>
          <p className="body-copy">{body}</p>
        </section>
      ))}
    </div>

    <div className="sec-label" style={{ marginTop: 28 }}>Modifiers</div>
    <section className="card card-pad">
      <p className="body-copy" style={{ marginBottom: 12 }}>
        Applied after the 75/15/10 blend and reported on every company. They refine a ranking;
        they are capped so they can never outweigh the fundamental evidence behind it.
      </p>
      <ul className="method-list">
        {MODIFIERS.map(([title, body]) => <li key={title}><b>{title}</b> — {body}</li>)}
      </ul>
    </section>

    <div className="sec-label" style={{ marginTop: 28 }}>Sell, trim, and watch guidance</div>
    <section className="card card-pad">
      <p className="body-copy">
        Guidance never leaves Hold on price action alone, and never on a single headline. Two of
        three independent factors have to agree first: deteriorating business fundamentals, broken
        market behaviour, and persistent negative sentiment or crowded positioning. Two agreeing
        factors produce a Trim with a suggested percentage of the position; two agreeing factors on
        a company that has also fallen below the evidence threshold produce a Sell. One factor alone
        is a Watch — a reason to look closer, not to act.
      </p>
    </section>

    <div className="sec-label" style={{ marginTop: 28 }}>Benchmark comparison</div>
    <section className="card card-pad">
      <p className="body-copy">
        Every hypothetical return is measured against the same dollars invested in the S&P 500 over
        the same window, because the honest question is not “did this go up” but “did this beat the
        index I could have bought instead”. Portfolio positions bought before the published
        benchmark window are shown as unavailable rather than compared against the wrong entry price.
      </p>
    </section>

    <div className="sec-label" style={{ marginTop: 28 }}>Provider and parser coverage</div>
    <section className="capability-grid" aria-label="Metric availability">
      {Object.entries(capabilities).map(([key, capability]) => (
        <article className="capability-card" key={key}>
          <span className={`capability-status ${capability.status}`}>{capability.status.replace(/_/g, ' ')}</span>
          <h2>{key.replace(/_/g, ' ')}</h2>
          {capability.source && <b>{capability.source}</b>}
          <p>{capability.note}</p>
        </article>
      ))}
    </section>

    <div className="disclaimer">{data?.disclaimer || 'General research only. Not individualized investment advice.'}</div>
  </>
}
