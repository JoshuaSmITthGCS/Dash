/** Chapter tabs — roman for inactive, italic for active, per the medium's own typographic idiom. */
export default function Tabs({ items = [], active, onSelect, capId }) {
  return (
    <div role="tablist" data-capability-id={capId} style={{ display: 'flex', gap: '10px', borderBottom: '1px solid var(--rule-hairline)' }}>
      {items.map((item) => (
        <button
          key={item.id} role="tab" aria-selected={item.id === active} onClick={() => onSelect?.(item.id)}
          style={{
            background: 'transparent', border: 'none', fontFamily: 'var(--font-body)', fontSize: '13px',
            fontStyle: item.id === active ? 'italic' : 'normal',
            padding: '10px 4px', minHeight: '44px', color: 'var(--ink-primary)',
          }}
        >
          {item.label}
        </button>
      ))}
    </div>
  )
}
