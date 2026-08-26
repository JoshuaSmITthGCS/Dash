import { STATES } from '../../core/states.js'

/** A window with a title bar — one per metric group, per DESIGN.md §10 containers. */
export default function Container({ primary = false, state, title, children, ...rest }) {
  const breached = state?.state === STATES.BREACHED
  return (
    <section data-beige-window="true" data-breached={breached ? 'true' : undefined} data-primary={primary ? 'true' : undefined} {...rest}>
      <div data-beige-titlebar="true">
        <span>{title || 'Untitled.grp'}</span>
        {breached && <span aria-hidden="true">⚠</span>}
      </div>
      <div data-beige-body="true">{children}</div>
    </section>
  )
}
