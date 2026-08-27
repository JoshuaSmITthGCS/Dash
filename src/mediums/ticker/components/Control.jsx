export default function Control({ as: Tag = 'button', capId, children, pressed, ...rest }) {
  return (
    <Tag
      data-capability-id={capId}
      aria-pressed={pressed}
      style={{
        background: 'transparent', color: pressed ? 'var(--ink-primary)' : 'var(--ink-faint)',
        border: '1px solid var(--rule-hairline)', fontFamily: 'var(--font-mono)', fontSize: '12px',
        padding: '8px 12px', minHeight: '44px',
      }}
      {...rest}
    >
      {children}
    </Tag>
  )
}
