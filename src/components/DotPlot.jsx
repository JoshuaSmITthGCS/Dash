/**
 * One dot per row along a shared horizontal scale — a compact visual ranking to sit
 * beside a table that already carries the full numbers. Because the value is always
 * printed beside its dot, this satisfies its own "every chart offers a table view"
 * obligation by staying next to the DataTable it summarizes rather than duplicating
 * a toggle for data already fully tabulated one scroll away.
 *
 * Rows outside `domain` (or with a non-finite value) are dropped, matching
 * ScatterChart's handling of missing data.
 */

export default function DotPlot({ rows = [], xLabel, xFormatter = String, domain = null, caption, className = '' }) {
  const usable = rows.filter((row) => Number.isFinite(row.value))
  if (!usable.length) return null

  const values = usable.map((row) => row.value)
  const min = domain?.min ?? Math.min(0, ...values)
  const max = domain?.max ?? Math.max(...values)
  const span = max - min || 1
  const width = 100 // percentage-based scale; the track is a flex row, not SVG
  const pct = (value) => Math.max(0, Math.min(width, ((value - min) / span) * width))
  const zeroPct = min <= 0 && max >= 0 ? pct(0) : null

  return (
    <figure className={`dot-plot ${className}`.trim()}>
      <div className="dot-plot-rows">
        {usable.map((row) => (
          <div className="dot-plot-row" key={row.id ?? row.label}>
            <span className="dot-plot-label">{row.label}</span>
            <span className="dot-plot-track" aria-hidden="true">
              {zeroPct != null && <i className="dot-plot-zero" style={{ left: `${zeroPct}%` }} />}
              <i className={`dot-plot-dot${row.tone ? ` ${row.tone}` : ''}`} style={{ left: `${pct(row.value)}%` }} />
            </span>
            <span className="dot-plot-value mono">{xFormatter(row.value)}</span>
          </div>
        ))}
      </div>
      {xLabel && <p className="dot-plot-axis-label">{xLabel}</p>}
      {caption && <p className="sr-only">{caption}</p>}
    </figure>
  )
}
