/** A chalk-stick control, tray-tray sized (44px), per DESIGN.md §9 "a chalk tray along the bottom edge". */
export default function Control({ as: Tag = 'button', capId, children, pressed, ...rest }) {
  return (
    <Tag
      data-capability-id={capId}
      aria-pressed={pressed}
      style={{
        background: pressed ? 'var(--surface-slate-raised)' : 'transparent',
        color: 'var(--chalk-white)',
        border: `2px ${pressed ? 'solid' : 'dashed'} var(--chalk-white)`,
        borderRadius: '2px 6px 2px 6px',
        fontFamily: 'var(--font-mono)', fontSize: '12px',
        padding: '8px 12px', minHeight: '44px', minWidth: '44px',
      }}
      {...rest}
    >
      {children}
    </Tag>
  )
}
