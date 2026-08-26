import { useData } from '../../../lib/useData.js'
import { cap } from '../../core/capability.js'

/** A front page with a lead story — the actual top-ranked/most-actionable name, never a placeholder. */
export default function Entry({ onContinue }) {
  const { data, loading } = useData('report.json')
  const asOf = data?.generated_at ? new Date(data.generated_at).toLocaleDateString() : '—'
  const lead = Array.isArray(data?.research)
    ? [...data.research].sort((a, b) => (b.score ?? 0) - (a.score ?? 0))[0]
    : null

  return (
    <div style={{ minHeight: '100dvh', background: 'var(--surface-ground)', color: 'var(--ink-primary)', padding: '24px 16px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
      <p style={{ textAlign: 'center', fontFamily: 'var(--font-display)', fontSize: '28px', margin: 0, letterSpacing: '0.04em' }}>
        THE VALUESIGNAL REPORT
      </p>
      <p style={{ textAlign: 'center', fontSize: '11px', color: 'var(--ink-faint)', margin: 0 }}>AS OF {asOf}</p>
      <hr style={{ border: 'none', borderTop: '3px double var(--ink-primary)' }} />
      {loading && <p style={{ fontFamily: 'var(--font-mono)', fontSize: '12px' }}>Wire developing…</p>}
      {lead && (
        <div data-column-rule="true">
          <h1 style={{ fontFamily: 'var(--font-display)', fontSize: '24px', margin: '0 0 4px' }}>
            {lead.name} ({lead.ticker}) leads today's report — score {lead.score}
          </h1>
          <p style={{ fontSize: '13px', color: 'var(--ink-secondary)' }}>
            Stance: {lead.stance}. Recommendation: {lead.recommendation?.action || '—'}.
          </p>
        </div>
      )}
      <button
        onClick={onContinue}
        {...cap('nav.chrome.mobile-tab-bar')}
        style={{ marginTop: 'auto', minHeight: '44px', padding: '10px 24px', background: 'var(--ink-primary)', color: 'var(--surface-ground)', border: 'none', fontFamily: 'var(--font-display)', letterSpacing: '0.04em' }}
      >
        Read the full report
      </button>
    </div>
  )
}
