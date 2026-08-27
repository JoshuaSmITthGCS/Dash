import { STATES } from '../../core/states.js'

/** A faint graticule — no filled card, per DESIGN.md §7's "no card containers in the plot area". */
export default function Container({ primary = false, state, children, ...rest }) {
  const breached = state?.state === STATES.BREACHED
  return (
    <section data-sc-plate="true" data-breached={breached ? 'true' : undefined} data-primary={primary ? 'true' : undefined} {...rest}>
      {children}
    </section>
  )
}
