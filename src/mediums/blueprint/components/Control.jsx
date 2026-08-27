/** A revision-stamp-style toggle — a boxed stamp, filled when pressed. */
export default function Control({ as: Tag = 'button', capId, children, pressed, ...rest }) {
  return (
    <Tag
      data-capability-id={capId}
      aria-pressed={pressed}
      style={{
        background: pressed ? 'var(--rule-cyan)' : 'transparent',
        color: pressed ? 'var(--surface-ground)' : 'var(--ink-primary)',
        border: '1px solid var(--rule-cyan)', fontFamily: 'var(--font-mono)', fontSize: '11px', textTransform: 'uppercase',
        padding: '8px 12px', minHeight: '44px', minWidth: '44px',
      }}
      {...rest}
    >
      {children}
    </Tag>
  )
}
