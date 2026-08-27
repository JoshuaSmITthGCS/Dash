/** The existing button system, ported as-is (DESIGN.md §12 controls). */
export default function Control({ as: Tag = 'button', capId, children, pressed, ...rest }) {
  return (
    <Tag data-capability-id={capId} aria-pressed={pressed} className={pressed ? 'primary-button' : 'secondary-button'} {...rest}>
      {children}
    </Tag>
  )
}
