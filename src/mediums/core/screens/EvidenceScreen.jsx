import { useSearchParams } from 'react-router-dom'
import { useData } from '../../../lib/useData.js'
import { useMedium } from '../MediumContext.jsx'
import { promotionDisclosure } from '../states.js'
import { cap } from '../capability.js'
import { EVIDENCE_IDS } from './capabilityIds.js'

export const EVIDENCE_SECTIONS = Object.freeze(['validation', 'backtests', 'shadow', 'methodology', 'glossary'])

/**
 * Absorbs validation (the 64-metric report), backtests, shadow, methodology, and glossary
 * behind `?section=` (see ROUTE-INVENTORY.md §2) — the destination that answers "should I trust
 * this model at all?" This shell renders the promotion/classification-B disclosure for real
 * (closing the docs-only gap noted in NOTES.md); the full SignalMetricsPanel embed, champion vs
 * challenger comparison, and the backtests/shadow/methodology/glossary sections port in per
 * medium in Phase 2b against CAPABILITY-LEDGER.md §10.
 */
export default function EvidenceScreen() {
  const manifest = useMedium()
  const Container = manifest.components?.Container || 'section'
  const [searchParams] = useSearchParams()
  const section = EVIDENCE_SECTIONS.includes(searchParams.get('section')) ? searchParams.get('section') : 'validation'

  const { data: signalMetrics, loading: metricsLoading } = useData(section === 'validation' ? 'validation/signal_metrics.json' : null)
  const { data: researchEvidence } = useData(section === 'validation' ? 'validation/research_evidence.json' : null)

  const promotion = promotionDisclosure(researchEvidence)

  if (section === 'validation' && metricsLoading) {
    return <div role="status" aria-live="polite">Loading…</div>
  }
  if (section === 'validation' && !signalMetrics) {
    return <div {...cap(EVIDENCE_IDS.icUnavailable)} role="alert">Signal metrics unavailable — run pipeline/signal_metrics.py.</div>
  }

  return (
    <div data-screen="evidence" data-section={section}>
      <Container {...cap(EVIDENCE_IDS.noSignalPromoted)}>
        <p data-testid="promotion-disclosure">{promotion.text}</p>
      </Container>
      {section === 'validation' && signalMetrics && (
        <Container {...cap(EVIDENCE_IDS.signalMetricsPanel)}>
          <span data-testid="metrics-summary">
            {signalMetrics.summary?.ready} ready · {signalMetrics.summary?.breached} breached of {signalMetrics.summary?.total}
          </span>
        </Container>
      )}
    </div>
  )
}
