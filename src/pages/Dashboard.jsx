import { useData, fmtDate } from '../lib/useData'
import { Tier, Move, Loading, Empty } from '../components/Bits.jsx'

function Macro({ label, point, suffix = '' }) {
  return <div className="card kpi"><div className="kpi-label">{label}</div><div className="kpi-value">{point?.value ?? '—'}{point?.value != null ? suffix : ''}</div><div className="kpi-note">{point?.date || 'unavailable'}</div></div>
}

export default function Dashboard() {
  const { data, loading } = useData('advisor.json')
  if (loading) return <Loading />
  if (!data?.research?.length) return <Empty note="No advisor dataset yet — run python pipeline/fetch_advisor.py." />
  const top = data.research.slice(0, 20)
  const macro = data.market?.macro || {}
  return <>
    <div className="page-head"><div>
      <h1 className="page-title">Top 20 <span className="accent">stocks to research</span></h1>
      <p className="page-sub">The highest-ranked companies from a diversified {data.universe_count || data.universe?.length}-stock universe, using valuation, profitability, cash flow, balance-sheet risk, growth, price behavior, and news sentiment.</p>
    </div><div className="stamp">updated<br />{fmtDate(data.generated_at)}</div></div>

    <div className="callout"><strong>Ranking formula:</strong> 75% fundamentals, 15% market behavior, 10% news. Valuation is built from PEG, sector-aware forward P/E and P/S, and P/B; missing evidence lowers confidence.</div>

    <div className="sec-label">Macro backdrop</div>
    <div className="grid grid-3" style={{ marginBottom: 28 }}>
      <Macro label="10Y Treasury" point={macro.treasury_10y} suffix="%" />
      <Macro label="Fed funds rate" point={macro.federal_funds_rate} suffix="%" />
      <Macro label="Inflation" point={macro.inflation} suffix="%" />
    </div>

    <div className="sec-label">Ranked 1–20</div>
    <div className="card card-pad table-wrap">
      <table><thead><tr><th>#</th><th>Company</th><th>View</th><th className="num">Score</th><th className="num">Fund.</th><th className="num">PEG</th><th className="num">Fwd P/E</th><th className="num">P/S</th><th className="num">20d</th><th className="num">Confidence</th></tr></thead>
        <tbody>{top.map((row, index) => <tr key={row.ticker}><td className="rank">{String(index + 1).padStart(2, '0')}</td><td><div className="tick-cell">{row.ticker}</div><div className="sig-name">{row.name} · {row.sector || '—'}</div></td><td><Tier label={row.stance} /></td><td className="mono num score-cell">{row.score}</td><td className="mono num">{row.components?.fundamentals == null ? '—' : Math.round(row.components.fundamentals)}</td><td className="mono num">{row.peg ?? '—'}</td><td className="mono num">{row.forward_pe ?? '—'}</td><td className="mono num">{row.price_to_sales ?? '—'}</td><td className="num"><Move pct={row.technical_detail?.return_20d} /></td><td className="mono num">{Math.round(row.confidence * 100)}%</td></tr>)}</tbody>
      </table>
    </div>
    <div className="disclaimer">{data.disclaimer} Rankings are relative to this configured universe and can change as prices, estimates, and financial statements update.</div>
  </>
}
