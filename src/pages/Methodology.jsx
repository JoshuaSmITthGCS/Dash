import { useState } from 'react'
import { useData } from '../lib/useData'
import Icon from '../components/Icons.jsx'
import appBreakdownMd from '../../APP-COMPLETE-BREAKDOWN.md?raw'
import masterMethodologyMd from '../../docs/MASTER-METHODOLOGY.md?raw'

const STATUS_TIMEOUT_MS = 2500

function downloadFile(filename, content, mime) {
  const blob = new Blob([content], { type: mime })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}

const CATEGORIES = {
  valuation: ['Valuation', 'EV/EBITDA and EV/EBIT carry this bucket. The enterprise multiple is the best-validated single value measure in the published research, and enterprise multiples are capital-structure neutral, so a levered company cannot look cheap purely because debt flatters its equity ratios. PEG is now a minor sanity check rather than the largest input. Both book-value multiples are trimmed because book value systematically mismeasures intangible-heavy businesses.'],
  profitability: ['Profitability + cash', 'ROIC leads rather than ROE because leverage inflates return on equity but cannot inflate return on invested capital. Gross profits over assets adds information a value screen cannot. Cash conversion tests whether reported earnings arrive as money.'],
  financial_health: ['Financial health', 'Interest coverage and net debt to EBITDA answer the question debt-to-equity cannot: can this business comfortably service its debt at current rates? The Altman Z-score uses the variant fitted for the filer’s sector and is suppressed for financials, where it has no meaning.'],
  accounting_quality: ['Accounting quality', 'The Piotroski F-score leads this bucket. The accruals ratio remains at a smaller weight because its predictive power has decayed in recent US data. Receivable and inventory day trends round out the check.'],
  growth: ['Growth', 'Revenue and earnings year over year, three-year free-cash-flow growth, the direction of operating margin, and earnings surprise against expectations. Trailing growth on its own predicts forward returns weakly. The surprise component is the part that carries drift.'],
  capital_allocation: ['Capital allocation', 'Net buyback yield after dilution, stock compensation as a share of revenue, capex against depreciation, and total asset growth. Aggressive expansion and under-investment can both weaken future returns, so both tails are penalized.'],
}

const MODIFIERS = [
  ['sector_valuation_percentile', 'Sector-relative valuation', 'Being cheap for a utility and being cheap outright are different claims. A percentile against sector peers separates them.'],
  ['short_interest', 'Short interest', 'Crowded shorts are not automatically bearish, but unusually high and low short interest can carry useful cross-sectional information.'],
  ['insider_activity', 'Insider activity', 'SEC Form 4 open-market trades are split into routine and opportunistic. Scheduled trades score zero. Fresh clusters of irregular open-market buying score positively and decay over time.'],
  ['liquidity', 'Liquidity', 'A name you cannot exit without moving the price carries a real cost that fundamentals never show.'],
  ['expectations', 'Analyst expectations', 'Consensus is used only when the published minimum analyst coverage is present.'],
  ['macro_regime', 'Macro regime', 'FRED rates, inflation, labor, and yield-curve conditions are weighted by sector sensitivity and never replace company evidence.'],
  ['institutional_13f', 'Institutional 13F', 'A curated set of publicly traded, actively managed 13F filers – index funds and private-equity managers are excluded, since their position changes track index membership or take-private deals rather than conviction. Decayed by filing lag: a position disclosed 45+ days ago carries less weight than a fresh one.'],
  ['congressional_buying', 'Congressional buying', 'Reward-only. Disclosed Congressional stock purchases score a mild positive; a member’s first-ever trade in a company under a $2B market cap scores an additional bonus. Sales and non-buying never penalize.'],
  ['customer_concentration_risk', 'Customer concentration (shadow only)', 'ASC 280 customer-concentration disclosures, penalty-only. Not yet part of the published score – shown here, and in the challenger comparison, while tagging coverage across the scored universe is being measured.'],
  ['geographic_concentration', 'Geographic concentration (shadow only)', 'Revenue concentrated in a single non-domestic country, penalty-only. Not yet part of the published score, for the same reason as customer concentration – coverage and tag accuracy are still being checked against real filings.'],
]

const percent = (value) => typeof value === 'number' ? Math.round(value * 100) : null

const componentLabel = (key) => ({
  fundamentals: 'fundamentals', market_behavior: 'behaviour', news_sentiment: 'news',
})[key] || key.replace(/_/g, ' ')

function modifierRange(config = {}) {
  const positive = config.max_points
  const negative = config.max_penalty
  if (typeof positive === 'number' && typeof negative === 'number') return `+${positive} / -${negative} points. `
  if (typeof positive === 'number') return `Up to +${positive} points. `
  if (typeof negative === 'number') return `Up to -${negative} points. `
  return ''
}

export default function Methodology() {
  const [downloadStatus, setDownloadStatus] = useState(null)
  const { data } = useData('advisor.json')
  const published = data?.research?.length
  // Read the blend from the snapshot so this page cannot drift from the config that
  // produced the scores it is describing.
  const blend = data?.methodology?.weights
  const blendEntries = Object.entries(blend || {}).filter(([, value]) => typeof value === 'number')
  const categoryWeights = data?.methodology?.fundamental_weights || {}
  const modifierConfig = data?.methodology?.modifiers || {}
  const version = data?.model_metadata
  const capabilities = data?.capability_status || {
    form4_insider_transactions: { status: 'available_next_refresh', source: 'SEC EDGAR', note: 'Free Form 4 parser is included in the pipeline.' },
    implied_vs_realized_volatility: { status: 'opt_in', source: 'Option chains + calculated returns', note: 'Enable options requests in the pipeline.' },
    analyst_revision_trends: { status: 'provider_required', note: 'Point-in-time estimate history is not supplied by the current providers.' },
    guidance_beat_miss_history: { status: 'provider_required', note: 'Requires contemporaneous consensus snapshots.' },
    backlog_growth: { status: 'available', source: 'SEC EDGAR XBRL', note: 'Remaining performance obligation, read from dimensional XBRL contexts.' },
    institutional_13f_changes: { status: 'available', source: 'SEC EDGAR Form 13F-HR + OpenFIGI', note: 'Curated, publicly traded, actively managed filers only; decayed by filing lag.' },
    congressional_buying: { status: 'available', source: 'STOCK Act disclosures', note: 'Reward-only; disclosed purchases, with a bonus for a first-ever trade in a small company.' },
    customer_concentration_risk: { status: 'shadow_only', source: 'SEC EDGAR XBRL', note: 'ASC 280 customer concentration. Challenger-only pending tagging-coverage measurement.' },
    fx_exposure: { status: 'shadow_only', source: 'SEC EDGAR XBRL', note: 'Single-country revenue concentration. Challenger-only pending measurement.' },
  }
  const handleDownloadDocs = () => {
    try {
      downloadFile('APP-COMPLETE-BREAKDOWN.md', appBreakdownMd, 'text/markdown')
      downloadFile('MASTER-METHODOLOGY.md', masterMethodologyMd, 'text/markdown')
      setDownloadStatus('Download started')
    } catch {
      setDownloadStatus('Download failed')
    }
    setTimeout(() => setDownloadStatus(null), STATUS_TIMEOUT_MS)
  }

  return <>
    <div className="page-head">
      <div>
        <h1 className="page-title">How the <span className="accent">score works</span></h1>
        <p className="page-sub">Transparent weights, consistent inputs, and an explicit penalty for missing evidence.</p>
      </div>
      <div>
        <button type="button" className="secondary-button compact" onClick={handleDownloadDocs}>
          <Icon name="download" size={17} />Download full docs (.md)
        </button>
        {downloadStatus && <p className="export-metrics-status" role="status">{downloadStatus}</p>}
      </div>
    </div>
    <p className="body-copy body-copy--gap">
      Downloads the complete, unedited source: the app's full functional/calculation breakdown
      (<code>APP-COMPLETE-BREAKDOWN.md</code>) and the master methodology reference
      (<code>MASTER-METHODOLOGY.md</code>) — every metric, weight, data source, and screen this
      page summarizes, with file:line citations back to the code that computes them.
    </p>

    <div className="grid grid-2">
      <section className="card card-pad">
        <div className="sec-label">Overall research score</div>
        {blendEntries.length ? <div className="weight-stack">
          {blendEntries.map(([key, value]) => {
            const pct = percent(value)
            const label = componentLabel(key)
            return <div key={key} style={{ width: `${pct}%` }} title={`${pct}% ${label}`}>{pct >= 10 ? `${pct}% ${label}` : `${pct}%`}</div>
          })}
        </div> : <p className="body-copy">The scoring blend will appear after the first published research refresh.</p>}
        <p className="body-copy">
          Fundamentals dominate. Market behaviour is measured with the same arithmetic the ETF
          screen uses – 12-month momentum skipping the most recent month (to avoid the
          short-term reversal that runs against it), Sortino and Sharpe ratios on the stock’s
          own returns, relative strength versus SPY, one-year maximum drawdown, and whether
          advances carry heavier volume than declines. Low beta is rewarded rather than
          volatility punished. News sentiment is a small tilt, not a component. Articles
          decay with age, low-confidence entity matches are discarded, syndicated copies
          count once, and source-of-record filings are labelled separately from commentary.
        </p>
        <p className="body-copy">
          Acceleration versus the market is measured on every name and shown on the company
          detail view, but it is deliberately not part of the blend above. It asks whether a
          stock’s lead over the index is widening rather than how large that lead is, and it
          subtracts the move the stock’s own beta says the market handed it – without that
          adjustment, a “relative” reading is only the raw return wearing a different label.
          It stays unweighted until prospective evidence shows it predicts something; a signal
          earning weight on a plausible story alone is the mistake this model has already made
          once.
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

    <div className="grid grid-2 methodology-section-gap">
      <section className="card card-pad">
        <div className="sec-label">Theme exposure is a separate screen</div>
        <p className="body-copy">
          Structural-trend exposure answers a different question from everything above: how
          exposed is this company to a multi-year demand driver? It is published as its own
          leaderboard and never folded into the research score – blending a forward-looking
          thematic bet into the fundamentals score would make that score impossible to read,
          because you could no longer tell whether a name ranked well for being cheap and
          profitable or for carrying a fashionable tag.
        </p>
        <ul className="method-list">
          <li>Exposure comes from segment revenue, the trend in how a company describes itself in its own filings, disclosed customer ties to confirmed spenders, and the capex plans of the companies writing the cheques.</li>
          <li>Share-price momentum contributes exactly zero, enforced in code and re-checked when the data is validated. Specialised thematic funds have a documented history of launching near hype peaks and losing heavily from there; reading price into a theme score is how that happens.</li>
          <li>Companies already priced in the top valuation decile of their sector are flagged, not promoted. The screen exists to find real exposure that is not yet euphoric.</li>
          <li>At least two independent signals must resolve. Segment reporting granularity is set by management and varies wildly between filers, so no single source carries a theme alone.</li>
          <li>Twenty themes are currently tracked: aging demographics, AI infrastructure, automation and robotics, battery storage, critical minerals, cybersecurity, data center cooling, defense and rearmament, digital payments, energy security, grid electrification, nuclear SMRs, obesity-care supply chain, OT and industrial cybersecurity, reshoring of industrial capacity, semiconductor-capital equipment, shipbuilding and naval, space and satellite, surgical robotics, and water infrastructure.</li>
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
          <li>Universe membership is snapshotted on every run, additions and removals recorded, so that in time a backtest cannot quietly run on survivors only. <strong>That protection is not yet in force.</strong> The log holds eight days and has recorded no removals, so any backtest run today still runs on the companies that exist today, and its returns are biased upward by an amount not yet measured. Companies that delisted before the log started cannot be recovered from it at all.</li>
          <li>Results are deflated for the number of configurations tried. Test enough weightings and one looks good by construction, so the bar rises with the count: a deflated Sharpe ratio corrects for selection across trials and for non-normal returns, and the significance hurdle is a t-statistic of 3 rather than 2.</li>
          <li>A change ships only if it improves out-of-sample performance after that deflation, regardless of how good it looks in sample. The harness runs on every build and grades only scores recorded before their forward returns existed — it never reconstructs history from today’s fundamentals. It currently reports <em>accumulating</em> at every horizon, short of the 24 periods it requires, so it has not yet had the evidence to pass or fail anything.</li>
        </ul>
      </section>
    </div>

    <div className="sec-label sec-label--section">Fundamental framework</div>
    <div className="grid grid-2">
      {Object.entries(CATEGORIES).map(([key, [title, body]]) => (
        <section className="card card-pad" key={key}>
          <h2 className="method-title">{title}{percent(categoryWeights[key]) != null ? ` · ${percent(categoryWeights[key])}%` : ''}</h2>
          <p className="body-copy">{body}</p>
        </section>
      ))}
    </div>

    <div className="sec-label sec-label--section">Sector context</div>
    <section className="card card-pad">
      <p className="body-copy body-copy--gap">
        Three separate mechanisms adjust for sector, each answering a different question. None of
        them change what a name has to earn – they change what counts as cheap, safe, or normal
        while it earns it.
      </p>
      <ul className="method-list">
        <li>
          <b>Sector-specific valuation bands.</b> Forward P/E and the sales multiples (EV/Sales,
          P/S) are scored against thresholds set per sector rather than one universal cutoff – a
          “cheap” forward P/E means a different number for a utility than for a software company.
          The Altman Z-score uses the variant fitted for the filer’s sector and is suppressed
          outright for financials, where the ratio has no meaning. Price-to-tangible-book is
          scored only where book value is economically meaningful, and leaves the coverage
          denominator elsewhere rather than count as missing evidence.
        </li>
        <li>
          <b>Sector-relative valuation modifier.</b> Separately from the bands above, each name’s
          full valuation score is ranked against peers – grouped by business profile (bank,
          insurer, REIT, utility, commodity producer) where one applies, by sector otherwise – and
          placed in a cheapest, middle, or most expensive third. A group needs at least 30 members
          before a claim publishes; below that the modifier scores zero rather than let a handful
          of names decide a percentile. This is what turns “cheap for the sector” into a scored,
          capped input rather than a label.
        </li>
        <li>
          <b>Macro regime, weighted by sector sensitivity.</b> Rate, inflation, labor, and
          yield-curve conditions move different sectors differently – real estate is weighted
          toward rates, financials toward the yield curve – so the same macro backdrop produces a
          different modifier depending on what the company does.
        </li>
        <li>
          <b>Business-profile classification, underneath sector.</b> Each name is also classified
          into one of roughly eighty business profiles – bank, reinsurer, SaaS, railroad, tobacco,
          pre-profit biotechnology, and so on – read from its disclosed industry, not just its
          broader sector. That classification decides which metrics apply to a name at all (price
          to book is suppressed for asset-light software, tangible book value only counts where it
          is economically meaningful) and, where a profile has enough members, it is tried first
          as the peer group for the valuation modifier above, sector only as the fallback.
        </li>
      </ul>
      <p className="body-copy">
        What doesn’t vary by sector: the weights in the fundamental framework above. Sector-specific
        weighting was tested and rejected – none of eleven sectors beat the uniform weights on the
        available data, which is evidence the uniform weights are adequate here, not evidence that
        sector economics are identical. A more thorough version of sector-relative scoring – ranking
        every fundamental metric within sector, not just the three above – runs as an unpublished
        challenger while it earns the same out-of-sample validation every change requires (see
        Validating a change to any of this, above).
      </p>
    </section>

    <div className="sec-label sec-label--section">Modifiers</div>
    <section className="card card-pad">
      <p className="body-copy body-copy--gap">
        Applied after the published blend and reported on every company. They refine a ranking,
        they are capped so they can never outweigh the fundamental evidence behind it.
      </p>
      <ul className="method-list">
        {MODIFIERS.map(([key, title, body]) => <li key={key}><b>{title}</b>: {modifierRange(modifierConfig[key])}{body}</li>)}
      </ul>
    </section>

    <div className="sec-label sec-label--section">ETF watchlist</div>
    <section className="card card-pad">
      <p className="body-copy body-copy--gap">
        The roughly 125-fund ETF watchlist runs on a different model from the one above – funds
        don’t file the statements the fundamental framework reads, so there is no fundamentals-first
        score to compute for them. Instead each fund gets its own 0–100 composite built from five
        weighted buckets: performance (28%, percentile of trailing one-month-to-three-year returns),
        risk (27%, Sortino, Sharpe, one-year max drawdown, and beta – low beta rewarded rather than
        volatility punished, same as the equity score), cost (17%, expense ratio plus the fund’s own
        tracking difference against its index plus premium or discount to NAV, deliberately more than
        expense ratio alone), liquidity (16%, AUM, dollar volume, and bid-ask spread), and quality
        (12%, an issuer-reputation estimate adjusted down for leverage, synthetic replication, and
        aggressive securities lending – a stand-in for the paid analyst ratings this pipeline doesn’t
        have).
      </p>
      <ul className="method-list">
        <li>Every metric is percentile-ranked against peers in the same category – broad market, growth, value, dividend, small cap, international, sector, thematic, bonds, commodity, crypto – so a bond fund’s Sharpe ratio is never compared against a leveraged sector fund’s.</li>
        <li>A category with fewer than four members is pooled with a related one and flagged as a cross-asset-class comparison rather than shown as apples-to-apples.</li>
        <li>Separately from the composite score, every fund has its own benchmark-comparison detail – beta, correlation, Sharpe and Sortino, up and down capture, tracking error, and drawdowns against a declared benchmark across windows from one month to the fund’s full history.</li>
      </ul>
    </section>

    <div className="sec-label sec-label--section">Other screens</div>
    <section className="card card-pad">
      <p className="body-copy body-copy--gap">
        The research score above is the foundation the rest of the product is built on, but several
        narrower screens run their own scoring logic for a more specific question than “is this a
        good business.” None of them feed back into the published research score.
      </p>
      <ul className="method-list">
        <li><b>Momentum, quality-value, pre-breakout, earnings timeliness, structural-tactical.</b> Five factor and tactical screens, each with its own weighted composite: exact skip-month 12-1 momentum with hysteresis-based membership so names don’t flicker in and out; a blend of own-history cheapness, sector-relative cheapness, business quality, and forward estimate revisions; fundamental inflection plus momentum plus insider and short-interest flow, explicitly graded by tier with no out-of-sample record published yet; and revision agreement, magnitude, acceleration, and dispersion trend for earnings-driven names.</li>
        <li><b>Swing screen.</b> A two-day-to-eight-week horizon screen, with a decay haircut on each signal leg reflecting how quickly that kind of edge is known to fade in the published research.</li>
        <li><b>Options screens.</b> A directional screen (buy call or put) plus seven strategy screens – short-term trades, covered calls, cash-secured puts, protective puts, collars, vertical spreads, and a broader advanced-strategies view – each ranking candidates for one specific options structure rather than the underlying stock.</li>
        <li><b>Congressional trading and institutional 13F screens.</b> The full disclosure feeds behind the congressional-buying and institutional-13F modifiers above, published here as their own ranked screens rather than folded into a single number.</li>
        <li><b>Inside Information.</b> Runs no new scoring – it combines the same two audited functions behind the congressional and institutional modifiers, then applies a notability filter on top: cluster accumulation or distribution across multiple curated managers, or, on the congressional side, an extraordinary buy, three or more representatives trading the same symbol, or a buy-then-sell round trip inside sixty days. It is explicitly not a claim that any of this activity was informed or improper.</li>
        <li><b>Filings feed.</b> A straight read of SEC EDGAR 10-K, 10-Q, DEF 14A, and 8-K filings – a feed, not a ranked screen.</li>
        <li><b>Shadow portfolios.</b> Dated, immutable snapshots of alternative strategies tracked forward alongside the live portfolio, so a challenger’s real performance is visible before it is ever promoted.</li>
        <li><b>Fast-growth screens.</b> “Breakout in progress” and “Emerging growth” are computed client-side from the same published research score, using different sort and filter rules rather than a separate pipeline model.</li>
      </ul>
    </section>

    <div className="sec-label sec-label--section">Published model version</div>
    <section className="card card-pad model-version-card">
      <dl>
        <div><dt>Semantic version</dt><dd>{version?.semantic_version || data?.model_version || 'Pending refresh'}</dd></div>
        <div><dt>Git commit</dt><dd>{version?.git_commit_sha?.slice(0, 12) || 'Pending refresh'}</dd></div>
        <div><dt>Config hash</dt><dd>{version?.config_hash?.slice(0, 12) || 'Pending refresh'}</dd></div>
        <div><dt>Generated</dt><dd>{version?.generated_at ? new Date(version.generated_at).toLocaleString() : 'Pending refresh'}</dd></div>
      </dl>
    </section>

    <div className="sec-label sec-label--section">Active guidance and shadow policy</div>
    <section className="card card-pad">
      <p className="body-copy body-copy--gap">
        The active legacy policy requires agreement across business fundamentals, market behaviour,
        and positioning or sentiment before it trims or sells. Its fixed factor-count sizing remains
        visible while the replacement policy is evaluated.
      </p>
      <p className="body-copy">
        The shadow policy keeps the company thesis, one-to-three-month timeliness, portfolio fit,
        and user position rules separate. A stop can trigger a position exit without turning the
        company into a thesis sell. Company scores are shrunk toward neutral when confidence is low,
        and trim size reflects severity, confidence, concentration, liquidity, tax friction, and
        minimum economic trade size. Shadow results do not control production actions.
      </p>
    </section>

    <div className="sec-label sec-label--section">Benchmark comparison</div>
    <section className="card card-pad">
      <p className="body-copy">
        Every hypothetical return is measured against the same dollars invested in the S&P 500 over
        the same window, because the honest question is not “did this go up” but “did this beat the
        index I could have bought instead”. Portfolio positions bought before the published
        benchmark window are shown as unavailable rather than compared against the wrong entry price.
      </p>
    </section>

    <div className="sec-label sec-label--section">Provider and parser coverage</div>
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
