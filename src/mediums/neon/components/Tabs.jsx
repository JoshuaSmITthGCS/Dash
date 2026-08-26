/** The active tab is lit — nav-chrome affordance lighting, not a data-glow device (see DESIGN.md §2). */
export default function Tabs({ items = [], active, onSelect, capId }) {
  return (
    <div role="tablist" data-capability-id={capId} style={{ display: 'flex', gap: '2px' }}>
      {items.map((item) => (
        <button
          key={item.id}
          role="tab"
          aria-selected={item.id === active}
          onClick={() => onSelect?.(item.id)}
          style={{
            background: 'transparent', border: 'none',
            borderBottom: item.id === active ? '2px solid var(--brand-cyan)' : '2px solid transparent',
            color: item.id === active ? 'var(--brand-cyan)' : 'var(--ink-faint)',
            fontFamily: 'var(--font-mono)', fontSize: '11px', letterSpacing: '0.05em', textTransform: 'uppercase',
            padding: '10px 12px', minHeight: '44px',
          }}
        >
          {item.label}
        </button>
      ))}
    </div>
  )
}
