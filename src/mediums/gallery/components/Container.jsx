import { STATES } from '../../core/states.js'

/** A frame around every work — gilt reserved for the primary work, plain moulding elsewhere. */
export default function Container({ primary = false, state, children, ...rest }) {
  const breached = state?.state === STATES.BREACHED
  return (
    <section data-gallery-frame="true" data-primary={primary ? 'true' : undefined} data-breached={breached ? 'true' : undefined} {...rest}>
      {children}
    </section>
  )
}
