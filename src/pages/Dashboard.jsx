import { useData, fmtDate } from '../lib/useData'
import { Tier, MetricPills, Move, Loading, Empty } from '../components/Bits.jsx'

function Macro({ label, point, suffix = '' }) {
  return <div className="card kpi"><div className="kpi-label">{label}</div><div className="kpi-value">{point?.value ?? '—'}{point?.value != null ? suffix : ''}</div><div className="kpi-note">{point?.date || 'unavailable'}</div></div>
}

export default function Dashboard() {
  const { data, loading } = useData('advisor.json')
  if (loading) return <Loading />
  if (!data?.research?.length) return <Empty note="No advisor dataset yet — run python pipeline/fetch_advisor.py." />
  const top = data.research.slice(0, 3)
  const macro = data.market?.macro || {}
  return <>
    <div className="page-head"><div>
      <h1 className="page-title">Invest with <span className="accent">context</span></h1>
      <p className="page-sub">A fundamentals-first research desk. Valuation, profitability, cash flow, balance-sheet risk, growth, price behavior, and news sentiment—scored without political-trade inputs.</p>
    </div><div className="stamp">updated<br />{fmtDate(data.generated_at)}</div></div>

    <div className="callout"><strong>How to read this:</strong> a high score is a research priority, not a buy order. Confidence falls when important financial data is missing.</div>

    <div className="sec-label">Macro backdrop</div>
    <div className="grid grid-3" style={{ marginBottom: 28 }}>
      <Macro label="10Y Treasury" point={macro.treasury_10y} suffix="%" />
      <Macro label="Fed funds rate" point={macro.federal_funds_rate} suffix="%" />
      <Macro label="Inflation" point={macro.inflation} suffix="%" />
    </div>

    <div className="sec-label">Highest research priority</div>
    <div className="grid">
      {top.map((row, index) => <article className="card sig" key={row.ticker}>
        <div className="sig-top"><div className="company-line"><span className="rank">0{index + 1}</span><div><div className="sig-tick">{row.ticker}</div><div className="sig-name">{row.name} · {row.sector || 'Sector unavailable'}</div></div></div>
          <div className="score-lockup"><Move pct={row.pct_30d} /><Tier label={row.stance} /><div><div className="sig-score">{row.score}</div><div className="score-caption">RESEARCH</div></div></div>
        </div>
        <MetricPills {...row} fundamental_coverage={row.confidence} />
        <div className="evidence-grid"><div><b>Evidence for</b><ul>{row.strengths.map(x => <li key={x}>{x}</li>)}</ul></div><div><b>Risks / gaps</b><ul>{row.risks.map(x => <li key={x}>{x}</li>)}</ul></div></div>
      </article>)}
    </div>
    <div className="disclaimer">{data.disclaimer}</div>
  </>
}
