/** Tabs within the legend idiom — small caps, filled dot for the active one. */
export default function Tabs({ items = [], active, onSelect, capId }) {
  return (
    <div role="tablist" data-capability-id={capId} style={{ display: 'flex', gap: '10px' }}>
      {items.map((item) => (
        <button
          key={item.id} role="tab" aria-selected={item.id === active} onClick={() => onSelect?.(item.id)}
          data-sc-smallcaps="true"
          style={{
            background: 'transparent', border: 'none', fontSize: '12px',
            padding: '10px 4px', minHeight: '44px', color: item.id === active ? 'var(--ink-primary)' : 'var(--ink-faint)',
          }}
        >
          {item.id === active ? '● ' : '○ '}{item.label}
        </button>
      ))}
    </div>
  )
}
