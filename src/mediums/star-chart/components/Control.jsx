/** A legend-key-styled control — plain text, small caps, underline on press. */
export default function Control({ as: Tag = 'button', capId, children, pressed, ...rest }) {
  return (
    <Tag
      data-capability-id={capId}
      aria-pressed={pressed}
      style={{
        background: 'transparent', border: '1px solid var(--graticule)', color: 'var(--ink-primary)',
        fontFamily: 'var(--font-mono)', fontSize: '11px',
        textDecoration: pressed ? 'underline' : 'none',
        padding: '8px 12px', minHeight: '44px', minWidth: '44px',
      }}
      {...rest}
    >
      {children}
    </Tag>
  )
}
