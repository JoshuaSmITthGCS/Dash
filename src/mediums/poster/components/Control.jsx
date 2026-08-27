/** A rubber-stamp-style toggle. */
export default function Control({ as: Tag = 'button', capId, children, pressed, ...rest }) {
  return (
    <Tag
      data-capability-id={capId}
      aria-pressed={pressed}
      style={{
        background: pressed ? 'var(--ink-black)' : 'transparent',
        color: pressed ? 'var(--surface-paper)' : 'var(--ink-black)',
        border: '2px solid var(--ink-black)',
        fontFamily: 'var(--font-mono)', fontSize: '12px', letterSpacing: '0.04em', textTransform: 'uppercase',
        padding: '8px 12px', minHeight: '44px',
      }}
      {...rest}
    >
      {children}
    </Tag>
  )
}
