import { useData } from '../../../lib/useData.js'

const PLATES = [
  { label: 'Home', plate: 'I' },
  { label: 'Research', plate: 'II' },
  { label: 'Screens', plate: 'III' },
  { label: 'Portfolio', plate: 'IV' },
  { label: 'Markets', plate: 'V' },
  { label: 'Evidence', plate: 'VI' },
]

/** A plate index by epoch — DESIGN.md §7 entry. */
export default function Entry({ onContinue }) {
  const { data } = useData('report.json')
  const asOf = data?.generated_at ? new Date(data.generated_at).toLocaleDateString() : '—'

  return (
    <div style={{ minHeight: '100dvh', background: 'var(--surface-ground)', color: 'var(--ink-primary)', padding: '28px 18px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
      <h1 data-sc-smallcaps="true" style={{ fontSize: '18px', margin: 0 }}>Plate Index</h1>
      <p style={{ fontSize: '11px', color: 'var(--ink-faint)' }}>Epoch: {asOf}</p>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
        {PLATES.map((p) => (
          <button
            key={p.label}
            onClick={onContinue}
            style={{
              display: 'flex', justifyContent: 'space-between', background: 'transparent',
              border: '1px solid var(--graticule)', color: 'inherit', fontFamily: 'var(--font-mono)', fontSize: '12px',
              padding: '10px 12px', minHeight: '44px', textAlign: 'left',
            }}
          >
            <span>Plate {p.plate}</span>
            <span data-sc-designation="true">{p.label}</span>
          </button>
        ))}
      </div>
    </div>
  )
}
