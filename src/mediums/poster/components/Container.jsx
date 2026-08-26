import { STATES } from '../../core/states.js'

/** A printed panel with trim and registration marks (tokens.css ::before/::after). */
export default function Container({ primary = false, state, children, ...rest }) {
  const breached = state?.state === STATES.BREACHED
  return (
    <section data-poster-panel="true" data-breached={breached ? 'true' : undefined} data-hero={primary ? 'true' : undefined} {...rest}>
      {children}
    </section>
  )
}
