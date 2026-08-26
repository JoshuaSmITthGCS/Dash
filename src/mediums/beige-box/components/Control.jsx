/** A bevelled button — hard 1px highlight/shadow, never a soft shadow. */
export default function Control({ as: Tag = 'button', capId, children, pressed, ...rest }) {
  return (
    <Tag
      data-capability-id={capId}
      data-beige-bevel="true"
      data-pressed={pressed ? 'true' : undefined}
      aria-pressed={pressed}
      style={{
        color: 'var(--ink-primary)', fontFamily: 'var(--font-mono)', fontSize: '12px',
        padding: '8px 12px', minHeight: '44px', minWidth: '44px',
      }}
      {...rest}
    >
      {children}
    </Tag>
  )
}
