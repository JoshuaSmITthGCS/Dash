import { useData } from '../lib/useData'
import { Loading, Empty } from '../components/Bits.jsx'

export default function PolicyRadar() {
  const { data, loading } = useData('news.json')
  if (loading) return <Loading />
  if (!data) return <Empty />

  const sectors = Object.entries(data.flagged_sectors || {}).sort((a, b) => b[1] - a[1])

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">Policy <span className="accent">radar</span></h1>
          <p className="page-sub">Headlines matched to policy-sensitive sectors and tickers. When a flagged sector also has congressional buying, that overlap is the strongest signal in the system.</p>
        </div>
      </div>

      <div className="sec-label">Hot sectors this week</div>
      <div className="grid grid-3" style={{ marginBottom: 28 }}>
        {sectors.map(([s, c]) => (
          <div className="card kpi" key={s}>
            <div className="kpi-label">{s.replace(/_/g, ' ')}</div>
            <div className="kpi-value lime">{c}<span style={{ fontSize: 13, color: 'var(--text-faint)', fontFamily: 'var(--font-mono)' }}> hits</span></div>
          </div>
        ))}
      </div>

      <div className="sec-label">Flagged headlines</div>
      <div className="grid" style={{ gridTemplateColumns: '1fr' }}>
        {(data.items || []).map((item, i) => {
          const Tag = item.url ? 'a' : 'article'
          const linkProps = item.url ? { href: item.url, target: '_blank', rel: 'noreferrer' } : {}
          return (
          <Tag className="card card-pad" key={i} {...linkProps}
            style={{ display: 'grid', gap: 8 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'baseline' }}>
              <strong style={{ fontSize: 15 }}>{item.title}</strong>
              <span className="chip" style={{ whiteSpace: 'nowrap' }}>{item.source}</span>
            </div>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              {item.flags?.map((f, j) => (
                <span className="chip" key={j} style={{ color: 'var(--accent)' }}>
                  {f.sector.replace(/_/g, ' ')} → {f.tickers.join(' ')}
                </span>
              ))}
            </div>
          </Tag>
        )})}
      </div>
    </>
  )
}
