export default function Tabs({ items = [], active, onSelect, capId }) {
  return (
    <div role="tablist" data-capability-id={capId} style={{ display: 'flex', gap: '2px', borderBottom: '2px solid var(--ink-black)' }}>
      {items.map((item) => (
        <button
          key={item.id}
          role="tab"
          aria-selected={item.id === active}
          onClick={() => onSelect?.(item.id)}
          style={{
            background: item.id === active ? 'var(--ink-black)' : 'transparent',
            color: item.id === active ? 'var(--surface-paper)' : 'var(--ink-black)',
            border: 'none', fontFamily: 'var(--font-mono)', fontSize: '11px', letterSpacing: '0.04em', textTransform: 'uppercase',
            padding: '10px 12px', minHeight: '44px',
          }}
        >
          {item.label}
        </button>
      ))}
    </div>
  )
}
