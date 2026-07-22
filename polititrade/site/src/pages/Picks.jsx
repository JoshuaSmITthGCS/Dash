import { useState } from 'react'
import { useData, fmtPct } from '../lib/useData'
import { Tier, Move, Loading, Empty } from '../components/Bits.jsx'

const BUCKETS = [
  { key: 'short_term', mark: '01', title: 'Short term', blurb: 'Catalyst + momentum. Weighted toward the political signal and recent price move. Highest noise, shortest shelf life.' },
  { key: 'long_term', mark: '02', title: 'Long term', blurb: 'Quality at a fair price. Weighted toward valuation — PEG, forward P/E, P/S — combined with the signal.' },
  { key: 'retirement', mark: '03', title: 'Retirement / broad', blurb: 'Diversification first. Broad-market and dividend ETFs anchor; single stocks only appear as stable satellites.' },
]

function Val({ v, good, rich }) {
  if (v == null) return <span className="mono" style={{ color: 'var(--text-faint)' }}>—</span>
  let cls = ''
  if (good && v > 0 && v <= good) cls = 'pos'
  else if (rich && v > rich) cls = 'neg'
  return <span className={`mono ${cls}`}>{v}</span>
}

export default function Picks() {
  const { data, loading } = useData('picks.json')
  const [tab, setTab] = useState('short_term')
  if (loading) return <Loading />
  if (!data) return <Empty />

  const rows = data.buckets[tab] || []
  const meta = BUCKETS.find((b) => b.key === tab)

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">Best <span className="accent">picks</span></h1>
          <p className="page-sub">Signals re-ranked into three horizons. Each blends the congressional signal with the valuation screen differently — see how the same ticker moves between buckets.</p>
        </div>
      </div>

      <div className="tabs">
        {BUCKETS.map((b) => (
          <button key={b.key} className={`tab${tab === b.key ? ' active' : ''}`} onClick={() => setTab(b.key)}>
            <span className="tabmark">{b.mark}</span>{b.title}
          </button>
        ))}
      </div>

      <p className="page-sub" style={{ margin: '0 0 18px', maxWidth: 640 }}>{meta.blurb}</p>

      <div className="card card-pad">
        <table>
          <thead>
            <tr>
              <th style={{ width: 34 }}>#</th>
              <th>Ticker</th>
              <th>Tier</th>
              <th className="num">Bucket</th>
              <th className="num">Signal</th>
              <th className="num">Val</th>
              <th className="num">PEG</th>
              <th className="num">Fwd P/E</th>
              <th className="num">P/S</th>
              <th className="num">30d</th>
              <th>Why it's here</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={r.ticker}>
                <td className="mono" style={{ color: 'var(--text-faint)' }}>{i + 1}</td>
                <td className="tick-cell">
                  {r.ticker}
                  {r.is_etf && <span className="chip" style={{ marginLeft: 6, fontSize: 9 }}>ETF</span>}
                </td>
                <td><Tier label={r.tier} /></td>
                <td className="mono num" style={{ color: 'var(--accent)', fontWeight: 600 }}>{r.bucket_score}</td>
                <td className="mono num">{r.political_score ?? '—'}</td>
                <td className="mono num">{r.valuation_score ?? '—'}</td>
                <td className="num"><Val v={r.peg} good={1.5} rich={2.5} /></td>
                <td className="num"><Val v={r.forward_pe} good={15} rich={40} /></td>
                <td className="num"><Val v={r.price_to_sales} good={2} rich={12} /></td>
                <td className="num"><Move pct={r.pct_30d} /></td>
                <td style={{ color: 'var(--text-dim)', fontSize: 12.5 }}>{r.why}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="disclaimer">{data.disclaimer} — Green = attractive on that metric, red = rich/expensive. Buckets differ only in how they weight the signal vs. valuation vs. stability; nothing here is a recommendation to buy.</div>
    </>
  )
}
