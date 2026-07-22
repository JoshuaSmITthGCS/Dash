import { useData } from '../lib/useData'
import { Move, Loading, Empty } from '../components/Bits.jsx'

export default function Politicians() {
  const { data, loading } = useData('politicians.json')
  if (loading) return <Loading />
  if (!data || !data.leaderboard?.length) return <Empty note="No track-record data yet — it builds weekly from trade history." />

  const rows = data.leaderboard

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">Track-record <span className="accent">leaderboard</span></h1>
          <p className="page-sub">Average 90-day return of each member's disclosed buys, measured as excess return over SPY (alpha). Refreshed weekly.</p>
        </div>
      </div>

      <div className="card card-pad">
        <table>
          <thead>
            <tr><th style={{ width: 34 }}>#</th><th>Politician</th><th className="num">Buys scored</th><th className="num">Avg 90d alpha</th><th className="num">Percentile</th></tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={r.politician}>
                <td className="mono" style={{ color: 'var(--text-faint)' }}>{i + 1}</td>
                <td style={{ textTransform: 'capitalize', fontWeight: 500 }}>{r.politician}</td>
                <td className="mono num" style={{ color: 'var(--text-dim)' }}>{r.n_buys_scored}</td>
                <td className="num"><Move pct={r.avg_90d_alpha} /></td>
                <td className="mono num">
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, justifyContent: 'flex-end' }}>
                    <span className="bar-track" style={{ width: 70 }}>
                      <span className="bar-fill" style={{ width: `${r.percentile}%` }} />
                    </span>
                    {r.percentile}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="disclaimer">Past disclosed performance is not predictive. Track record feeds 25% of a signal's score but is one input among six.</div>
    </>
  )
}
