export default function Tabs({ items = [], active, onSelect, capId }) {
  return (
    <div role="tablist" data-capability-id={capId} style={{ display: 'flex', gap: '2px', borderBottom: '1px solid var(--rule-hairline)' }}>
      {items.map((item) => (
        <button
          key={item.id} role="tab" aria-selected={item.id === active} onClick={() => onSelect?.(item.id)}
          style={{
            background: 'transparent', border: 'none', color: item.id === active ? 'var(--ink-primary)' : 'var(--ink-faint)',
            fontFamily: 'var(--font-mono)', fontSize: '11px', padding: '10px 12px', minHeight: '44px',
          }}
        >
          {item.label}
        </button>
      ))}
    </div>
  )
}
