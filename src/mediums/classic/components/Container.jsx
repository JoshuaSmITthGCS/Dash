import { STATES } from '../../core/states.js'

/** The existing glass card/shelf system, ported as-is (DESIGN.md §12 containers). */
export default function Container({ primary = false, state, children, ...rest }) {
  const breached = state?.state === STATES.BREACHED
  return (
    <section
      className={`card card-pad${primary ? ' card--interactive' : ''}${breached ? ' tone-breached' : ''}`}
      data-breached={breached ? 'true' : undefined}
      {...rest}
    >
      {children}
    </section>
  )
}
