import InfoTag from './InfoTag.jsx'

const labelize = (value) => String(value).replace(/_/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())

export function radarEntries(stock) {
  const source = stock?.analysis_v2?.structural?.categories
    || stock?.fundamental_categories
    || stock?.scores
    || {}
  return Object.entries(source)
    .filter(([, value]) => Number.isFinite(Number(value)))
    .slice(0, 8)
    .map(([key, value]) => ({ key, label: labelize(key), value: Math.max(0, Math.min(100, Number(value))) }))
}

function point(index, count, radius, center = 160) {
  const angle = (Math.PI * 2 * index) / count - Math.PI / 2
  return [center + Math.cos(angle) * radius, center + Math.sin(angle) * radius]
}

function polygon(entries, scale) {
  return entries.map((entry, index) => point(index, entries.length, 105 * scale * (entry?.value == null ? 1 : entry.value / 100)).join(',')).join(' ')
}

export default function ResearchRadarChart({ stock }) {
  const entries = radarEntries(stock)
  if (entries.length < 3) return null
  const summary = entries.map((entry) => `${entry.label} ${Math.round(entry.value)} out of 100`).join(', ')

  return (
    <figure className="research-radar" aria-label={`${stock.ticker} section scores: ${summary}`}>
      <div className="research-radar-heading">
        <div><span className="sec-label">Section radar</span><h3>Research profile
          <InfoTag label="Research profile">
            <strong>Research profile</strong>
            <p>Each axis is one structural research category (e.g. valuation, profitability, growth) on
              a 0–100 scale, higher is stronger. Shows the shape of a company's evidence at a glance -
              a broad, even shape is a different story from a name that is strong on one axis only.</p>
          </InfoTag>
        </h3></div>
        <span>0–100 · higher is stronger</span>
      </div>
      <svg viewBox="0 0 320 320" role="img" aria-hidden="true">
        {[0.25, 0.5, 0.75, 1].map((scale) => (
          <polygon key={scale} className="radar-grid" points={polygon(entries.map(() => ({ value: 100 })), scale)} />
        ))}
        {entries.map((entry, index) => {
          const [x, y] = point(index, entries.length, 105)
          return <line key={entry.key} className="radar-axis" x1="160" y1="160" x2={x} y2={y} />
        })}
        <polygon className="radar-area" points={polygon(entries, 1)} />
        {entries.map((entry, index) => {
          const [x, y] = point(index, entries.length, 105 * entry.value / 100)
          return <circle key={entry.key} className="radar-point" cx={x} cy={y} r="4" />
        })}
      </svg>
      <dl className="research-radar-values">
        {entries.map((entry) => <div key={entry.key}><dt>{entry.label}</dt><dd>{Math.round(entry.value)}</dd></div>)}
      </dl>
    </figure>
  )
}
