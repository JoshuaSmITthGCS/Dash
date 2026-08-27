import { STATES } from '../../core/states.js'

/**
 * Bezel/corner-bracket container — never a card. `primary` renders the raised bezel tone;
 * `live`/`breached` add the glow that means, respectively, "this readout is live" and "the one
 * alert accent" — never both meaning the same thing (Cockpit vs. Neon's closest-pair divergence,
 * see DESIGN.md).
 */
export default function Container({ primary = false, state, children, ...rest }) {
  const live = state?.state === STATES.ESTABLISHED
  const breached = state?.state === STATES.BREACHED
  return (
    <section
      data-cockpit-bezel="true"
      data-live={live ? 'true' : undefined}
      data-breached={breached ? 'true' : undefined}
      style={primary ? { background: 'var(--surface-bezel-raised)' } : undefined}
      {...rest}
    >
      {children}
    </section>
  )
}
