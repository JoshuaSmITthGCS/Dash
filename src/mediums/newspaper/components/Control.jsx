/** A masthead-styled control — small caps, underline on press. */
export default function Control({ as: Tag = 'button', capId, children, pressed, ...rest }) {
  return (
    <Tag
      data-capability-id={capId}
      aria-pressed={pressed}
      style={{
        background: 'transparent', border: 'none', color: 'var(--ink-primary)',
        fontFamily: 'var(--font-display)', fontSize: '13px', letterSpacing: '0.02em',
        textDecoration: pressed ? 'underline' : 'none',
        padding: '10px 12px', minHeight: '44px', minWidth: '44px',
      }}
      {...rest}
    >
      {children}
    </Tag>
  )
}
