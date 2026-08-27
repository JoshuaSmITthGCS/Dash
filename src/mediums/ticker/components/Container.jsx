import { STATES } from '../../core/states.js'

/** No cards — a hairline row is the only structure. */
export default function Container({ state, children, ...rest }) {
  const breached = state?.state === STATES.BREACHED
  return <div data-ticker-row="true" data-breached={breached ? 'true' : undefined} {...rest}>{children}</div>
}
