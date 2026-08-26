export default function Tabs({ items = [], active, onSelect, capId }) {
  return (
    <div role="tablist" data-capability-id={capId} style={{ display: 'flex', gap: '4px', borderBottom: '1px solid var(--frame-plain)' }}>
      {items.map((item) => (
        <button
          key={item.id} role="tab" aria-selected={item.id === active} onClick={() => onSelect?.(item.id)}
          style={{
            background: 'transparent', border: 'none', fontFamily: 'var(--font-body)',
            fontStyle: item.id === active ? 'italic' : 'normal', fontSize: '13px',
            padding: '10px 12px', minHeight: '44px', color: 'var(--ink-primary)',
          }}
        >
          {item.label}
        </button>
      ))}
    </div>
  )
}
