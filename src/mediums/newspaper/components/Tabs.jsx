/** Masthead section tabs — the same device used for primary navigation, reused for in-page tabs. */
export default function Tabs({ items = [], active, onSelect, capId }) {
  return (
    <div role="tablist" data-capability-id={capId} style={{ display: 'flex', gap: '12px', borderBottom: '2px solid var(--ink-primary)' }}>
      {items.map((item) => (
        <button
          key={item.id} role="tab" aria-selected={item.id === active} onClick={() => onSelect?.(item.id)}
          data-masthead-tab="true"
          style={{
            background: 'transparent', border: 'none', fontSize: '13px',
            fontWeight: item.id === active ? 700 : 400,
            padding: '10px 4px', minHeight: '44px', color: 'var(--ink-primary)',
          }}
        >
          {item.label}
        </button>
      ))}
    </div>
  )
}
