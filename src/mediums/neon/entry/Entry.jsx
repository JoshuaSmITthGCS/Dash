import { useData } from '../../../lib/useData.js'

/** Arcade attract-screen title card, carrying the live as-of date. Skippable, persisted, one interaction. */
export default function Entry({ onContinue }) {
  const { data } = useData('report.json')
  const asOf = data?.generated_at ? new Date(data.generated_at).toLocaleDateString() : '—'

  return (
    <div style={{ minHeight: '100dvh', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '16px', background: 'var(--surface-ground)' }}>
      <h1 data-neon-hero="true" style={{ fontSize: '32px', margin: 0 }}>VALUESIGNAL</h1>
      <p style={{ color: 'var(--ink-secondary)', fontSize: '13px' }}>AS OF {asOf}</p>
      <button
        onClick={onContinue}
        style={{ minHeight: '44px', padding: '10px 24px', background: 'transparent', border: '1px solid var(--brand-cyan)', color: 'var(--brand-cyan)', fontFamily: 'var(--font-mono)', letterSpacing: '0.08em' }}
      >
        ENTER
      </button>
    </div>
  )
}
