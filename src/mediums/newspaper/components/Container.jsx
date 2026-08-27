import { STATES } from '../../core/states.js'

/** Column rules as the container device — a vertical rule, never a box (DESIGN.md §8). */
export default function Container({ primary = false, state, children, ...rest }) {
  const breached = state?.state === STATES.BREACHED
  return (
    <section data-column-rule="true" data-breached={breached ? 'true' : undefined} data-primary={primary ? 'true' : undefined} {...rest}>
      {children}
    </section>
  )
}
