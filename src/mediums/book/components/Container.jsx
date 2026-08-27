import { STATES } from '../../core/states.js'

/** A ruled table with a folio (page-position marker) — DESIGN.md §5 containers. */
export default function Container({ primary = false, state, folio, children, ...rest }) {
  const breached = state?.state === STATES.BREACHED
  return (
    <section data-book-table="true" data-breached={breached ? 'true' : undefined} data-primary={primary ? 'true' : undefined} {...rest}>
      {children}
      {folio && <div data-book-folio="true">{folio}</div>}
    </section>
  )
}
