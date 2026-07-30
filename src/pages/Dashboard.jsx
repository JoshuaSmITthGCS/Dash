import { useState } from 'react'
import { useData, fmtDate } from '../lib/useData'
import { Tier, Move, Loading, Empty } from '../components/Bits.jsx'
import { ActionPill } from '../components/ActionGuidance.jsx'
import StockDetailModal from '../components/StockDetailModal.jsx'
import { getRecommendation } from '../lib/recommendation'

function Macro({ label, point, suffix = '' }) {
  return <div className="card kpi"><div className="kpi-label">{label}</div><div className="kpi-value">{point?.value ?? '—'}{point?.value != null ? suffix : ''}</div><div className="kpi-note">{point?.date || 'unavailable'}</div></div>
}

export default function Dashboard() {
  const { data, loading } = useData('advisor.json')
  const [selectedStock, setSelectedStock] = useState(null)

  if (loading) return <Loading />
  if (!data?.research?.length) return <Empty note="No advisor dataset yet — run python pipeline/fetch_advisor.py." />
  const rows = data.research
  const macro = data.market?.macro || {}
  const universeSize = data.universe_count || data.universe?.length
  return <>
    <div className="page-head"><div>
      <h1 className="page-title">Top {rows.length} <span className="accent">stocks to research</span></h1>
      <p className="page-sub">The highest-ranked companies from a diversified {universeSize}-stock universe, scored on valuation, profitability and capital returns, cash quality, balance-sheet risk, capital allocation, accounting integrity, growth, price behaviour, and news sentiment.</p>
    </div><div className="stamp">updated<br />{fmtDate(data.generated_at)}</div></div>

    <div className="callout"><strong>Ranking formula:</strong> 75% fundamentals, 15% market behaviour, 10% news, then bounded modifiers for sector-relative valuation, short interest, liquidity, and analyst expectations. Missing evidence lowers confidence and the score with it.</div>

    <div className="sec-label">Macro backdrop</div>
    <div className="grid grid-3" style={{ marginBottom: 28 }}>
      <Macro label="10Y Treasury" point={macro.treasury_10y} suffix="%" />
      <Macro label="Fed funds rate" point={macro.federal_funds_rate} suffix="%" />
      <Macro label="Inflation" point={macro.inflation} suffix="%" />
    </div>

    <div className="sec-label">Ranked 1–{rows.length}</div>
    <div className="card card-pad table-wrap">
      <table><thead><tr><th>#</th><th>Company</th><th>View</th><th>Signal</th><th className="num">Score</th><th className="num">Fund.</th><th className="num">ROIC</th><th className="num">EV/EBITDA</th><th className="num">Int. cov.</th><th className="num">20d</th><th className="num">Conf.</th><th>Action</th></tr></thead>
        <tbody>{rows.map((row, index) => <tr key={row.ticker}>
          <td className="rank">{String(index + 1).padStart(2, '0')}</td>
          <td><div className="tick-cell">{row.ticker}</div><div className="sig-name">{row.name} · {row.sector || '—'}</div></td>
          <td><Tier label={row.stance} /></td>
          <td><ActionPill recommendation={getRecommendation(row)} /></td>
          <td className="mono num score-cell">{row.score}</td>
          <td className="mono num">{row.components?.fundamentals == null ? '—' : Math.round(row.components.fundamentals)}</td>
          <td className="mono num">{row.return_on_invested_capital == null ? '—' : `${(row.return_on_invested_capital * 100).toFixed(1)}%`}</td>
          <td className="mono num">{row.ev_to_ebitda ?? '—'}</td>
          <td className="mono num">{row.interest_coverage == null ? '—' : `${row.interest_coverage.toFixed(1)}×`}</td>
          <td className="num"><Move pct={row.technical_detail?.return_20d} /></td>
          <td className="mono num">{Math.round(row.confidence * 100)}%</td>
          <td><button className="chip button-chip" onClick={() => setSelectedStock(row)}>Details</button></td>
        </tr>)}</tbody>
      </table>
    </div>
    <div className="disclaimer">{data.disclaimer} Rankings are relative to this configured universe and can change as prices, estimates, and financial statements update.</div>
    {selectedStock && <StockDetailModal stock={selectedStock} benchmarkHistory={data.benchmark_history} onClose={() => setSelectedStock(null)} />}
  </>
}
