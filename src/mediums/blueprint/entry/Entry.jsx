import { useData } from '../../../lib/useData.js'
import { cap } from '../../core/capability.js'

const SHEETS = [
  { label: 'Home', sheet: '01/06', rev: 'C' },
  { label: 'Research', sheet: '02/06', rev: 'B' },
  { label: 'Screens', sheet: '03/06', rev: 'D' },
  { label: 'Portfolio', sheet: '04/06', rev: 'A' },
  { label: 'Markets', sheet: '05/06', rev: 'B' },
  { label: 'Evidence', sheet: '06/06', rev: 'C' },
]

/** A sheet index with revision states — DESIGN.md §6 entry. */
export default function Entry({ onContinue }) {
  const { data } = useData('report.json')
  const asOf = data?.generated_at ? new Date(data.generated_at).toLocaleDateString() : '—'

  return (
    <div style={{ minHeight: '100dvh', background: 'var(--surface-ground)', color: 'var(--ink-primary)', padding: '24px 16px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
      <h1 style={{ fontFamily: 'var(--font-display)', fontSize: '20px', margin: 0, letterSpacing: '0.04em' }}>SHEET INDEX</h1>
      <p style={{ fontSize: '11px', color: 'var(--ink-faint)' }}>AS OF {asOf}</p>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
        {SHEETS.map((s) => (
          <button
            key={s.label}
            onClick={onContinue}
            {...cap('nav.chrome.mobile-tab-bar')}
            style={{
              display: 'flex', justifyContent: 'space-between', background: 'transparent',
              border: '1px solid var(--rule-cyan)', color: 'inherit', fontFamily: 'var(--font-mono)', fontSize: '12px',
              padding: '10px 12px', minHeight: '44px', textAlign: 'left',
            }}
          >
            <span>SHEET {s.sheet} — {s.label.toUpperCase()}</span>
            <span style={{ color: 'var(--ink-faint)' }}>REV. {s.rev}</span>
          </button>
        ))}
      </div>
    </div>
  )
}
