import { useData } from '../lib/useData'

const CATEGORIES = [
  ['Valuation · 28%', 'PEG, sector-aware forward P/E and P/S, P/B, and price-to-tangible-book for financials, plus EV/EBITDA and EV/FCF. Enterprise multiples are capital-structure neutral, so a levered company cannot look cheap purely because debt flatters its equity ratios.'],
  ['Profitability + cash · 22%', 'ROIC leads here rather than ROE: leverage inflates return on equity but cannot inflate return on invested capital. Cash conversion — free cash flow per dollar of net income — tests whether reported earnings arrive as money.'],
  ['Financial health · 16%', 'Interest coverage and net debt to EBITDA answer the question debt-to-equity cannot: can this business comfortably service its debt at current rates? The Altman Z-score adds a composite solvency read for non-financials.'],
  ['Accounting quality · 12%', 'The accruals ratio is the most-studied earnings-quality red flag in the literature; large gaps between profit and operating cash flow predict underperformance. The Piotroski F-score and receivable and inventory day trends round out the check.'],
  ['Growth · 12%', 'Revenue and earnings year over year, three-year free-cash-flow growth, and the direction of operating margin. A mediocre but improving margin is a different story from the same margin sliding.'],
  ['Capital allocation · 10%', 'Net buyback yield after dilution, stock compensation as a share of revenue, and capex against depreciation. Under-investment flatters near-term cash flow and quietly erodes competitiveness.'],
]

const MODIFIERS = [
  ['Sector-relative valuation', '±3 points. Being cheap for a utility and being cheap outright are different claims; a percentile against sector peers separates them.'],
  ['Short interest', 'Up to −4 points. Crowded shorts are not automatically bearish, but they raise the cost of being wrong.'],
  ['Liquidity', 'Up to −3 points. A name you cannot exit without moving the price carries a real cost that fundamentals never show.'],
  ['Analyst expectations', '±3 points, and only where at least three analysts cover the name.'],
  ['Macro regime', '±3 points. FRED rates, inflation, labor, and yield-curve conditions are weighted by sector sensitivity and never replace company evidence.'],
]

export default function Methodology() {
  const { data } = useData('advisor.json')
  const published = data?.research?.length
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
          <div style={{ width: '75%' }}>75% fundamentals</div>
          <div style={{ width: '15%' }}>15% behaviour</div>
          <div style={{ width: '10%' }}>10% news</div>
        </div>
        <p className="body-copy">Fundamentals dominate. Market behaviour measures trend, relative strength versus SPY, volatility, one-year maximum drawdown, and whether advances carry heavier volume than declines. News sentiment is deliberately the smallest input.</p>
      </section>
      <section className="card card-pad">
        <div className="sec-label">Guardrails</div>
        <ul className="method-list">
          <li>PEG pairs provider-consistent inputs; it is not reconstructed from mismatched periods.</li>
          <li>Industry context beats universal P/E or P/S thresholds.</li>
          <li>Coverage is weighted, so a missing headline input costs far more confidence than a missing minor one.</li>
          <li>Bank balance sheets skip the industrial-company cutoffs entirely rather than failing them.</li>
          <li>The top {published || 'ranked names'} come from {data?.universe_count || 'the configured'} candidates; scores do not forecast returns.</li>
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
