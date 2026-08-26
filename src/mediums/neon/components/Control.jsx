export default function Control({ as: Tag = 'button', capId, children, pressed, ...rest }) {
  return (
    <Tag
      data-capability-id={capId}
      aria-pressed={pressed}
      style={{
        background: pressed ? 'var(--surface-panel)' : 'transparent',
        border: `1px solid ${pressed ? 'var(--brand-cyan)' : 'var(--rule-hairline)'}`,
        color: pressed ? 'var(--brand-cyan)' : 'var(--ink-secondary)',
        fontFamily: 'var(--font-mono)', fontSize: '12px', letterSpacing: '0.05em', textTransform: 'uppercase',
        padding: '8px 12px', minHeight: '44px', borderRadius: '3px',
      }}
      {...rest}
    >
      {children}
    </Tag>
  )
}
