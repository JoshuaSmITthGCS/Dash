import { useData } from '../../../lib/useData.js'

/** A cover, carrying an issue number and the live as-of date. */
export default function Entry({ onContinue }) {
  const { data } = useData('report.json')
  const asOf = data?.generated_at ? new Date(data.generated_at).toLocaleDateString() : '—'

  return (
    <div style={{ minHeight: '100dvh', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '16px', background: 'var(--surface-paper)' }}>
      <p style={{ fontSize: '12px', letterSpacing: '0.1em' }}>ISSUE 01</p>
      <h1 style={{ fontFamily: 'var(--font-display)', fontSize: '36px', margin: 0 }}>VALUESIGNAL</h1>
      <p style={{ fontSize: '13px', color: 'var(--ink-secondary)' }}>AS OF {asOf}</p>
      <button
        onClick={onContinue}
        style={{ minHeight: '44px', padding: '10px 24px', background: 'var(--ink-black)', color: 'var(--surface-paper)', border: 'none', fontFamily: 'var(--font-mono)', letterSpacing: '0.06em' }}
      >
        OPEN
      </button>
    </div>
  )
}
