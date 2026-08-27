/** Tabs drawn as adjoining boxes on the rail — active tab underlined twice, like a breach mark. */
export default function Tabs({ items = [], active, onSelect, capId }) {
  return (
    <div role="tablist" data-capability-id={capId} style={{ display: 'flex', gap: '4px', borderBottom: '2px dotted var(--ink-faint)' }}>
      {items.map((item) => (
        <button
          key={item.id} role="tab" aria-selected={item.id === active} onClick={() => onSelect?.(item.id)}
          style={{
            background: 'transparent', border: 'none', fontFamily: 'var(--font-mono)', fontSize: '13px',
            padding: '10px 12px', minHeight: '44px', color: 'var(--chalk-white)',
            textDecoration: item.id === active ? 'underline' : 'none',
            textDecorationStyle: item.id === active ? 'double' : undefined,
          }}
        >
          {item.label}
        </button>
      ))}
    </div>
  )
}
