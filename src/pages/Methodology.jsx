import { useData } from '../lib/useData'

const METRICS = [
  ['Valuation · 40%', 'PEG, sector-aware forward P/E, sector-aware P/S, and P/B. Very low multiples are screened for value-trap risk.'],
  ['Profitability + cash · 25%', 'ROE, free-cash-flow yield, and profit margin test whether accounting earnings become durable owner value.'],
  ['Financial health · 20%', 'Debt-to-equity and current ratio measure resilience. Bank balance sheets are treated separately.'],
  ['Growth · 15%', 'Year-over-year revenue and earnings growth test whether value has a credible path forward.'],
]
export default function Methodology() {
  const { data } = useData('advisor.json')
  return <><div className="page-head"><div><h1 className="page-title">How the <span className="accent">score works</span></h1><p className="page-sub">Transparent weights, consistent inputs, and an explicit penalty for missing evidence.</p></div></div>
    <div className="grid grid-2"><section className="card card-pad"><div className="sec-label">Overall research score</div><div className="weight-stack"><div style={{ width: '60%' }}>60% fundamentals</div><div style={{ width: '25%' }}>25% behavior</div><div style={{ width: '15%' }}>15% news</div></div><p className="body-copy">Fundamentals lead. Technical behavior measures trend, relative strength versus SPY, volatility, and drawdown. News sentiment is deliberately the smallest input.</p></section>
      <section className="card card-pad"><div className="sec-label">Guardrails</div><ul className="method-list"><li>PEG pairs provider-consistent inputs; it is not reconstructed from mismatched periods.</li><li>Industry context beats universal P/E or P/S thresholds.</li><li>Missing metrics reduce confidence and the final score.</li><li>Scores rank the configured universe; they do not forecast returns.</li></ul></section></div>
    <div className="sec-label" style={{ marginTop: 28 }}>Fundamental framework</div><div className="grid grid-2">{METRICS.map(([title, body]) => <section className="card card-pad" key={title}><h2 className="method-title">{title}</h2><p className="body-copy">{body}</p></section>)}</div>
    <div className="disclaimer">{data?.disclaimer || 'General research only. Not individualized investment advice.'}</div>
  </>
}
