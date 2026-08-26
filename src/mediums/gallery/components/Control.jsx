/** An engraved-placard-style toggle. */
export default function Control({ as: Tag = 'button', capId, children, pressed, ...rest }) {
  return (
    <Tag
      data-capability-id={capId}
      aria-pressed={pressed}
      style={{
        background: pressed ? 'var(--frame-plain)' : 'transparent',
        color: pressed ? 'var(--surface-wall)' : 'var(--ink-primary)',
        border: '1px solid var(--frame-plain)', fontFamily: 'var(--font-mono)', fontSize: '11px', letterSpacing: '0.04em',
        padding: '8px 12px', minHeight: '44px',
      }}
      {...rest}
    >
      {children}
    </Tag>
  )
}
