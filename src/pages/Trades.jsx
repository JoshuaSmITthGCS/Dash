import { useMemo, useState } from 'react'
import { useData } from '../lib/useData'
import { Loading, Empty } from '../components/Bits.jsx'

export default function Trades() {
  const { data, loading } = useData('trades.json')
  const [chamber, setChamber] = useState('all')
  const [party, setParty] = useState('all')
  const [type, setType] = useState('all')
  const [q, setQ] = useState('')

  const rows = useMemo(() => {
    let t = data?.trades || []
    if (chamber !== 'all') t = t.filter((x) => x.chamber === chamber)
    if (party !== 'all') t = t.filter((x) => x.party === party)
    if (type !== 'all') t = t.filter((x) => x.type === type)
    if (q) t = t.filter((x) => x.ticker.includes(q.toUpperCase()) || x.politician.includes(q.toLowerCase()))
    return t
  }, [data, chamber, party, type, q])

  if (loading) return <Loading />
  if (!data) return <Empty />

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">Trade <span className="accent">feed</span></h1>
          <p className="page-sub">Every disclosed transaction in the last 90 days, normalized across both chambers.</p>
        </div>
      </div>

      <div className="filters">
        <input placeholder="ticker or name…" value={q} onChange={(e) => setQ(e.target.value)} />
        <select value={chamber} onChange={(e) => setChamber(e.target.value)}>
          <option value="all">all chambers</option><option>House</option><option>Senate</option>
        </select>
        <select value={party} onChange={(e) => setParty(e.target.value)}>
          <option value="all">all parties</option><option value="D">Democrat</option><option value="R">Republican</option>
        </select>
        <select value={type} onChange={(e) => setType(e.target.value)}>
          <option value="all">buys + sells</option><option value="buy">buys</option><option value="sell">sells</option>
        </select>
        <span className="chip" style={{ alignSelf: 'center' }}>{rows.length} rows</span>
      </div>

      <div className="card card-pad">
        <table>
          <thead>
            <tr><th>Politician</th><th>Ticker</th><th>Type</th><th>Amount</th><th className="num">Chamber</th><th className="num">Trade</th><th className="num">Filed</th><th className="num">Lag</th></tr>
          </thead>
          <tbody>
            {rows.map((t, i) => (
              <tr key={i}>
                <td style={{ textTransform: 'capitalize' }}>{t.politician} <span className="chip" style={{ marginLeft: 4 }}>{t.party}</span></td>
                <td className="tick-cell">{t.ticker}</td>
                <td><span className={t.type === 'buy' ? 'pos mono' : 'neg mono'} style={{ textTransform: 'uppercase', fontSize: 11 }}>{t.type}</span></td>
                <td className="mono" style={{ fontSize: 12, color: 'var(--text-dim)' }}>{t.amount_range}</td>
                <td className="num" style={{ color: 'var(--text-dim)' }}>{t.chamber}</td>
                <td className="mono num" style={{ color: 'var(--text-dim)' }}>{t.trade_date}</td>
                <td className="mono num" style={{ color: 'var(--text-dim)' }}>{t.filing_date}</td>
                <td className="mono num"><span className="lag">{t.filing_lag_days ?? '—'}d</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}
