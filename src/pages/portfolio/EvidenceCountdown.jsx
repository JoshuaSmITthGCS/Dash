// When each "not yet" on the evidence views becomes a reading. Most unavailable cells are
// waiting on time, not broken; this puts a date on every one.

// Year included: the prospective verdict is two years out, and "Sep 1" alone would read as next month.
const formatDate = (iso) => new Date(`${iso}T12:00:00Z`).toLocaleDateString('en-US', {
  timeZone: 'UTC', month: 'short', day: 'numeric', year: 'numeric',
})

const UNIT = { sessions: 'sessions', months: 'monthly periods' }

export default function EvidenceCountdown({ countdown }) {
  if (!countdown?.pending?.length) return null
  return (
    <section className="card card-pad evidence-countdown" aria-labelledby="evidence-countdown-title">
      <div className="portfolio-section-heading">
        <div><span className="eyebrow">Evidence</span><h3 id="evidence-countdown-title">When the evidence arrives</h3></div>
      </div>
      <ol className="evidence-countdown-list">
        {countdown.pending.map((row) => (
          <li key={row.id}>
            <time dateTime={row.estimatedDate || undefined}>
              {row.estimatedDate ? formatDate(row.estimatedDate) : 'Undated'}
              {row.overdue && <small> · overdue</small>}
            </time>
            <div>
              <strong>{row.label}</strong>
              <span>{row.unlocks}</span>
            </div>
            {row.required != null && (
              <div className="evidence-countdown-progress" role="img" aria-label={`${row.observations ?? 0} of ${row.required} ${UNIT[row.unit]}`}>
                <meter min={0} max={row.required} value={row.observations ?? 0} />
                <small className="mono">{row.observations ?? 0} / {row.required} {UNIT[row.unit]}</small>
              </div>
            )}
          </li>
        ))}
      </ol>
      <p className="disclaimer">
        Dates are lower-bound estimates: sessions skip weekends but not exchange holidays, and a missed refresh
        moves a date later. Counts come straight from the published reports.
        {countdown.met.length ? ` Already reading: ${countdown.met.map((row) => row.label).join(', ')}.` : ''}
      </p>
    </section>
  )
}
