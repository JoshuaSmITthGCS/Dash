import { useData } from '../../../lib/useData.js'
import { cap } from '../../core/capability.js'

const ICONS = [
  { label: 'Home', glyph: '🏠' },
  { label: 'Research', glyph: '🔍' },
  { label: 'Screens', glyph: '📋' },
  { label: 'Portfolio', glyph: '💼' },
  { label: 'Markets', glyph: '📈' },
  { label: 'Evidence', glyph: '📄' },
]

/** A desktop of icons — destinations as icons, DESIGN.md §10 entry. */
export default function Entry({ onContinue }) {
  const { data } = useData('report.json')
  const asOf = data?.generated_at ? new Date(data.generated_at).toLocaleDateString() : '—'

  return (
    <div data-beige-phosphor="true" style={{ minHeight: '100dvh', display: 'flex', flexDirection: 'column', padding: '24px 16px', gap: '24px' }}>
      <p style={{ fontSize: '12px' }}>ValueSignal 3.2 — booted. As of {asOf}</p>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '16px' }}>
        {ICONS.map((icon) => (
          <button
            key={icon.label}
            onClick={onContinue}
            {...cap('nav.chrome.mobile-tab-bar')}
            style={{
              background: 'transparent', border: 'none', color: 'inherit',
              display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '4px',
              minHeight: '44px', fontFamily: 'var(--font-mono)', fontSize: '11px',
            }}
          >
            <span aria-hidden="true" style={{ fontSize: '28px' }}>{icon.glyph}</span>
            {icon.label}
          </button>
        ))}
      </div>
      <button
        onClick={onContinue}
        data-beige-bevel="true"
        {...cap('nav.chrome.mobile-tab-bar')}
        style={{ alignSelf: 'flex-start', minHeight: '44px', padding: '8px 16px', fontFamily: 'var(--font-mono)', color: 'var(--ink-primary)', marginTop: 'auto' }}
      >
        Start
      </button>
    </div>
  )
}
