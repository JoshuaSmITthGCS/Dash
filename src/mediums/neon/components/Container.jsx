import { STATES } from '../../core/states.js'

/**
 * A flat panel — grid substrate behind data, never perspective-distorting. `data-breached` is
 * the ONLY condition that may ever add the glow token (tokens.css enforces this structurally:
 * the box-shadow rule is scoped to `[data-breached="true"]` alone).
 */
export default function Container({ primary = false, state, children, ...rest }) {
  const breached = state?.state === STATES.BREACHED
  return (
    <section
      data-neon-panel="true"
      data-breached={breached ? 'true' : undefined}
      data-hero={primary ? 'true' : undefined}
      {...rest}
    >
      {children}
    </section>
  )
}
