import { useData } from '../../../lib/useData.js'

const CHAPTERS = [
  { label: 'Home', folio: 1 },
  { label: 'Research', folio: 12 },
  { label: 'Screens', folio: 28 },
  { label: 'Portfolio', folio: 47 },
  { label: 'Markets', folio: 63 },
  { label: 'Evidence', folio: 71 },
]

/** A table of contents — the six destinations as chapters with folios, DESIGN.md §5 entry. */
export default function Entry({ onContinue }) {
  const { data } = useData('report.json')
  const asOf = data?.generated_at ? new Date(data.generated_at).toLocaleDateString() : '—'

  return (
    <div style={{ minHeight: '100dvh', background: 'var(--surface-page)', color: 'var(--ink-primary)', padding: '32px 20px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
      <h1 style={{ fontFamily: 'var(--font-display)', fontSize: '26px', margin: 0 }}>ValueSignal</h1>
      <p style={{ fontSize: '12px', color: 'var(--ink-faint)', margin: 0 }}>An annual reference. As of {asOf}.</p>
      <nav aria-label="Table of contents" style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
        {CHAPTERS.map((c, i) => (
          <button
            key={c.label}
            onClick={onContinue}
            style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'baseline',
              background: 'transparent', border: 'none', color: 'inherit', fontFamily: 'var(--font-body)', fontSize: '15px',
              padding: '10px 0', minHeight: '44px', borderBottom: '1px dotted var(--rule-hairline)', textAlign: 'left',
            }}
          >
            <span>Ch. {i + 1} · {c.label}</span>
            <span data-book-folio="true">{c.folio}</span>
          </button>
        ))}
      </nav>
    </div>
  )
}
