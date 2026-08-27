/**
 * The extended metric stack, grouped the way an analyst would read it.
 *
 * Every entry declares how to format itself and which direction is good, so a value can be
 * tinted without a second lookup table. Metrics that the pipeline could not derive are
 * hidden rather than shown as a zero – a missing number is not a bad number.
 *
 * SECTIONS, readValue, canonicalKey, and resolvedMetricSections live in
 * ../lib/resolvedMetricSections.js (a pure module with no src/components dependency, so
 * code outside src/components can use them too) and are re-exported here for existing
 * call sites that import them from this file.
 */

export { SECTIONS, readValue, canonicalKey, resolvedMetricSections } from '../lib/resolvedMetricSections.js'
import { SECTIONS, resolvedMetricSections } from '../lib/resolvedMetricSections.js'

function tone(value, thresholds) {
  if (!thresholds) return 'var(--text)'
  const { good, bad, lowerBetter } = thresholds
  if (good == null || bad == null) return 'var(--text)'
  const isGood = lowerBetter ? value <= good : value >= good
  const isBad = lowerBetter ? value >= bad : value <= bad
  if (isGood) return 'var(--pos)'
  if (isBad) return 'var(--neg)'
  return 'var(--text)'
}

function Metric({ label, value, format, why, thresholds }) {
  return (
    <div className="metric-detail" title={why}>
      <span className="metric-detail-label">{label}</span>
      <b className="mono" style={{ color: tone(value, thresholds) }}>{format(value)}</b>
      {why && <small>{why}</small>}
    </div>
  )
}

export default function MetricSections({ stock, sections = SECTIONS }) {
  const status = stock.analysis_v2?.metric_status || {}
  const rendered = resolvedMetricSections(stock, sections)

  if (!rendered.length) {
    return (
      <p className="metric-section-empty">
        Extended metrics appear here once the pipeline has derived this company’s financial statements.
      </p>
    )
  }

  const exceptions = Object.entries(status).filter(([, detail]) => detail.status !== 'applied')
  return (
    <div className="metric-sections-list">
      {rendered.map((section) => (
        <section key={section.title}>
          <div className="sec-label">{section.title}</div>
          {section.note && (
            <p className="metric-section-note">{section.note}</p>
          )}
          <div className="metric-detail-grid">
            {section.resolved.map((metric) => <Metric key={metric.key} {...metric} />)}
          </div>
        </section>
      ))}
      {exceptions.length > 0 && (
        <section className="metric-exceptions">
          <div className="sec-label">Applicability and data-quality exceptions</div>
          <div className="metric-exception-list">
            {exceptions.map(([metric, detail]) => (
              <div key={metric}>
                <b>{metric.replace(/_/g, ' ')}</b>
                <span className="chip">{detail.status}</span>
                <small>{detail.reason || (detail.replaced_by ? `Replaced by ${detail.replaced_by.replace(/_/g, ' ')}` : 'No canonical observation available.')}</small>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  )
}
