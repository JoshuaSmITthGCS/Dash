/** Tabs as a row of bevelled, mutually-exclusive buttons — dotted focus rectangle on each. */
export default function Tabs({ items = [], active, onSelect, capId }) {
  return (
    <div role="tablist" data-capability-id={capId} style={{ display: 'flex', gap: '2px' }}>
      {items.map((item) => (
        <button
          key={item.id} role="tab" aria-selected={item.id === active} onClick={() => onSelect?.(item.id)}
          data-beige-bevel="true" data-pressed={item.id === active ? 'true' : undefined}
          style={{ fontFamily: 'var(--font-mono)', fontSize: '12px', padding: '8px 10px', minHeight: '44px', color: 'var(--ink-primary)' }}
        >
          {item.label}
        </button>
      ))}
    </div>
  )
}
