import { STATES } from '../../core/states.js'

/** A sheet border with edge coordinate (zone) markers — DESIGN.md §6 containers. */
export default function Container({ primary = false, state, zone = 'A1', children, ...rest }) {
  const breached = state?.state === STATES.BREACHED
  return (
    <section data-bp-sheet="true" data-breached={breached ? 'true' : undefined} data-primary={primary ? 'true' : undefined} {...rest}>
      <span data-bp-zone-mark="true" style={{ top: '2px', left: '4px' }}>{zone}</span>
      {children}
    </section>
  )
}
