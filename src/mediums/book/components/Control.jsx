/** A footnote-style control — small caps, underline on press, never a filled button. */
export default function Control({ as: Tag = 'button', capId, children, pressed, ...rest }) {
  return (
    <Tag
      data-capability-id={capId}
      aria-pressed={pressed}
      style={{
        background: 'transparent', border: '1px solid var(--rule-hairline)', color: 'var(--ink-primary)',
        fontFamily: 'var(--font-body)', fontSize: '13px',
        textDecoration: pressed ? 'underline' : 'none',
        padding: '10px 12px', minHeight: '44px', minWidth: '44px',
      }}
      {...rest}
    >
      {children}
    </Tag>
  )
}
