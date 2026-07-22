import { useState } from 'react'
import { useData, fmtDate } from '../lib/useData'
import { Tier, ScoreBreakdown, MetricPills, Move, Lag, Loading, Empty } from '../components/Bits.jsx'

export default function Dashboard() {
  const { data, loading } = useData('signals.json')
  const [open, setOpen] = useState(0)

  if (loading) return <Loading />
  if (!data || !data.signals?.length) return <Empty />

  const signals = data.signals
  const top = signals.slice(0, 5)
  const highConv = signals.filter((s) => s.label === 'HIGH CONVICTION').length
  const clusters = signals.filter((s) => s.cluster_size >= 3).length
  const hotSectors = Object.entries(data.hot_sectors || {}).sort((a, b) => b[1] - a[1])

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">Today's <span className="accent">signals</span></h1>
          <p className="page-sub">Congressional buying + policy catalysts, scored and ranked. Every card shows the filing lag — stale signals are meant to look stale.</p>
        </div>
        <div className="stamp">updated<br />{fmtDate(data.generated_at)}</div>
      </div>

      <div className="grid grid-3" style={{ marginBottom: 24 }}>
        <div className="card kpi"><div className="kpi-label">Signals tracked</div><div className="kpi-value">{signals.length}</div></div>
        <div className="card kpi"><div className="kpi-label">High conviction</div><div className="kpi-value lime">{highConv}</div></div>
        <div className="card kpi"><div className="kpi-label">Active clusters (3+)</div><div className="kpi-value">{clusters}</div></div>
      </div>

      {hotSectors.length > 0 && (
        <>
          <div className="sec-label">Policy radar — sectors in the news this week</div>
          <div className="filters" style={{ marginBottom: 26 }}>
            {hotSectors.map(([s, c]) => (
              <span className="chip" key={s}>{s.replace(/_/g, ' ')} <b style={{ color: 'var(--accent)' }}>×{c}</b></span>
            ))}
          </div>
        </>
      )}

      <div className="sec-label">Top 5 — tap to expand the score</div>
      <div className="grid" style={{ gridTemplateColumns: '1fr' }}>
        {top.map((s, i) => (
          <div className="card sig" key={s.ticker} onClick={() => setOpen(open === i ? -1 : i)} style={{ cursor: 'pointer' }}>
            <div className="sig-top">
              <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
                <span className="mono" style={{ color: 'var(--text-faint)', width: 20 }}>{String(i + 1).padStart(2, '0')}</span>
                <div>
                  <div className="sig-tick">{s.ticker}</div>
                  <div className="sig-name">{s.name} · {s.sector || '—'}</div>
                </div>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
                <Move pct={s.pct_30d} />
                <Tier label={s.label} />
                <div style={{ textAlign: 'right' }}>
                  <div className="sig-score">{s.political_score}</div>
                  <div className="mono" style={{ fontSize: 9.5, color: 'var(--text-faint)', letterSpacing: '.1em' }}>SIGNAL</div>
                </div>
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
              <MetricPills {...s} isEtf={s.is_etf} />
              <Lag days={s.filing_lag_days} />
            </div>

            {open === i && (
              <div style={{ borderTop: '1px solid var(--border)', paddingTop: 14, marginTop: 2 }}>
                <ScoreBreakdown breakdown={s.breakdown} />
                <div className="sig-why" style={{ marginTop: 12 }}>
                  {s.cluster_size >= 2 ? `${s.cluster_size} members buying · ` : ''}
                  top buyer: {s.top_buyer} · disclosed {s.amount_range}
                </div>
              </div>
            )}
          </div>
        ))}
      </div>

      {data.cooling?.length > 0 && (
        <>
          <div className="sec-label" style={{ marginTop: 32 }}>Cooling — heavy congressional selling</div>
          <div className="card card-pad">
            <table>
              <thead><tr><th>Ticker</th><th>Sector</th><th className="num">Sellers</th><th className="num">30d</th><th></th></tr></thead>
              <tbody>
                {data.cooling.map((c) => (
                  <tr key={c.ticker}>
                    <td className="tick-cell">{c.ticker}</td>
                    <td style={{ color: 'var(--text-dim)' }}>{c.sector || '—'}</td>
                    <td className="mono num">{c.sellers}</td>
                    <td className="num"><Move pct={c.pct_30d} /></td>
                    <td className="num"><Tier label="COOLING" /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      <div className="disclaimer">
        Informational only. Not financial advice. Congressional STOCK Act disclosures lag the actual trade
        by 30–45 days, so nothing here front-runs anyone — the edge is pattern detection (clusters, committee
        overlap, high-track-record members, policy catalysts), framed as candidates to research, never buy orders.
      </div>
    </>
  )
}
