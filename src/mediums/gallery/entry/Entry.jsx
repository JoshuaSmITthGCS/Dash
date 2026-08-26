import { useData } from '../../../lib/useData.js'
import { cap } from '../../core/capability.js'

/** A foyer, listing the current exhibition and its dates from the live as-of timestamp. */
export default function Entry({ onContinue }) {
  const { data } = useData('report.json')
  const asOf = data?.generated_at ? new Date(data.generated_at).toLocaleDateString() : '—'

  return (
    <div style={{ minHeight: '100dvh', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '16px', background: 'var(--surface-wall)' }}>
      <h1 style={{ fontFamily: 'var(--font-display)', fontSize: '30px', margin: 0 }}>ValueSignal</h1>
      <p style={{ fontStyle: 'italic', color: 'var(--ink-secondary)' }}>An exhibition of current holdings and research</p>
      <p data-gallery-plaque="true">Open through {asOf}</p>
      <button
        onClick={onContinue}
        {...cap('nav.chrome.mobile-tab-bar')}
        style={{ minHeight: '44px', padding: '10px 24px', background: 'transparent', border: '1px solid var(--frame-plain)', fontFamily: 'var(--font-body)' }}
      >
        Enter the gallery
      </button>
    </div>
  )
}
