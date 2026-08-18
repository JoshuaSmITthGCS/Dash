import { useRef, useState } from 'react'
import Icon from './Icons.jsx'
import { buildExportSnapshot, snapshotFilename, snapshotToJson } from '../lib/exportSnapshot.js'
import { ANALYTICS_SCOPES } from '../pages/portfolio/format.js'

const STATUS_TIMEOUT_MS = 2500

/**
 * Every holding, every performance/risk/benchmark/signal-quality metric, and the research
 * pipeline's own tear sheet and forward projection, as one JSON file or clipboard payload --
 * for a user who wants to hand this to another AI assistant rather than read it as cards.
 */
export default function ExportMetricsMenu({ holdings, analytics, benchmarks, signalMetrics, monteCarlo, scope }) {
  const [status, setStatus] = useState(null)
  const detailsRef = useRef(null)
  const scopeLabel = ANALYTICS_SCOPES.find((row) => row.id === scope)?.label || 'All portfolio history'

  const announce = (message) => {
    setStatus(message)
    setTimeout(() => setStatus(null), STATUS_TIMEOUT_MS)
  }

  const snapshot = () => buildExportSnapshot({ holdings, analytics, benchmarks, signalMetrics, monteCarlo, scope })

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(snapshotToJson(snapshot()))
      announce('Copied to clipboard')
    } catch {
      announce('Copy failed -- your browser may block clipboard access here')
    }
    if (detailsRef.current) detailsRef.current.open = false
  }

  const handleDownload = () => {
    try {
      const blob = new Blob([snapshotToJson(snapshot())], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = snapshotFilename(scope)
      document.body.appendChild(anchor)
      anchor.click()
      anchor.remove()
      URL.revokeObjectURL(url)
      announce('Download started')
    } catch {
      announce('Download failed')
    }
    if (detailsRef.current) detailsRef.current.open = false
  }

  return (
    <details className="portfolio-data-menu export-metrics-menu" ref={detailsRef}>
      <summary><span>Export metrics</span><Icon name="chevron" size={15} aria-hidden="true" /></summary>
      <div className="portfolio-data-popover">
        <div className="portfolio-data-status">
          <span className="eyebrow">Scope</span>
          <span>{scopeLabel}</span>
        </div>
        <button type="button" className="secondary-button" onClick={handleCopy}>
          <Icon name="copy" size={17} />Copy all metrics to clipboard
        </button>
        <button type="button" className="secondary-button" onClick={handleDownload}>
          <Icon name="download" size={17} />Download all metrics (JSON)
        </button>
        <p className="export-metrics-note">
          Every holding, performance and risk metric, benchmark comparison, and signal-quality
          reading currently loaded -- everything you'd need to hand another AI your progress.
        </p>
      </div>
      {status && <p className="export-metrics-status" role="status">{status}</p>}
    </details>
  )
}
