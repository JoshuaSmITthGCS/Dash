/** A calibrated-dial-style tab row — used for in-page selectors (e.g. Portfolio's ?view= tabs). */
export default function Tabs({ items = [], active, onSelect, capId }) {
  return (
    <div role="tablist" data-capability-id={capId} style={{ display: 'flex', gap: '2px', borderBottom: '1px solid var(--rule-hairline)' }}>
      {items.map((item) => (
        <button
          key={item.id}
          role="tab"
          aria-selected={item.id === active}
          onClick={() => onSelect?.(item.id)}
          style={{
            background: 'transparent',
            border: 'none',
            borderBottom: item.id === active ? '2px solid var(--state-established)' : '2px solid transparent',
            color: item.id === active ? 'var(--ink-primary)' : 'var(--ink-faint)',
            fontFamily: 'var(--font-mono)',
            fontSize: '11px',
            letterSpacing: '0.05em',
            textTransform: 'uppercase',
            padding: '10px 12px',
            minHeight: '44px',
          }}
        >
          {item.label}
        </button>
      ))}
    </div>
  )
}
