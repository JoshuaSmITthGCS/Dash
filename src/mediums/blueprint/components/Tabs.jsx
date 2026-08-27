/** Zone tabs — the same device used for primary navigation, reused for in-page tabs. */
export default function Tabs({ items = [], active, onSelect, capId }) {
  return (
    <div role="tablist" data-capability-id={capId} style={{ display: 'flex', gap: '2px', borderBottom: '1px solid var(--rule-cyan)' }}>
      {items.map((item) => (
        <button
          key={item.id} role="tab" aria-selected={item.id === active} onClick={() => onSelect?.(item.id)}
          style={{
            background: item.id === active ? 'var(--grid-construction)' : 'transparent',
            border: 'none', fontFamily: 'var(--font-mono)', fontSize: '11px', textTransform: 'uppercase',
            padding: '10px 8px', minHeight: '44px', color: 'var(--ink-primary)',
          }}
        >
          {item.label}
        </button>
      ))}
    </div>
  )
}
