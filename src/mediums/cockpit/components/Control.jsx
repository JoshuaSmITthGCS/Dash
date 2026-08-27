/** A detented switch — a two-state toggle rendered as a physical throw, or a plain input when `as` differs. */
export default function Control({ as: Tag = 'button', capId, children, pressed, ...rest }) {
  return (
    <Tag
      data-capability-id={capId}
      aria-pressed={pressed}
      style={{
        background: pressed ? 'var(--surface-bezel-raised)' : 'var(--surface-bezel)',
        border: '1px solid var(--rule-hairline)',
        color: 'var(--ink-primary)',
        fontFamily: 'var(--font-mono)',
        fontSize: '12px',
        letterSpacing: '0.05em',
        textTransform: 'uppercase',
        padding: '8px 12px',
        minHeight: '44px',
        borderRadius: 'var(--bezel-radius)',
      }}
      {...rest}
    >
      {children}
    </Tag>
  )
}
