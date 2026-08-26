import { STATES } from '../../core/states.js'

/** A hand-drawn box, corners overshooting slightly (tokens.css border-radius asymmetry). */
export default function Container({ primary = false, state, children, ...rest }) {
  const breached = state?.state === STATES.BREACHED
  return (
    <section data-chalk-box="true" data-breached={breached ? 'true' : undefined} data-primary={primary ? 'true' : undefined} {...rest}>
      {children}
    </section>
  )
}
