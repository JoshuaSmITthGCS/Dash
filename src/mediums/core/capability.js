/**
 * `data-capability-id` instrumentation. Every element the ledger tracks carries this attribute
 * so Phase 3's parity assertion can diff the live DOM against CAPABILITY-LEDGER.md in both
 * directions (an id in the DOM but not the ledger fails; an id in the ledger but never rendered
 * in some medium fails).
 *
 * Primary path: `WallLabel`, `manifest.components.Control`/`Tabs`, and `DataTable` columns apply
 * this automatically from the metric/column id they're already given. `cap(id)` below is the
 * escape hatch for any bespoke element that doesn't go through one of those primitives.
 */
export function cap(id) {
  if (!id) return {}
  return { 'data-capability-id': id }
}

// Populated lazily from scripts/build-ledger-ids.mjs's generated scripts/ledger-ids.json in dev
// builds only — kept optional so this module works standalone in tests and in a production
// build carries zero cost (the dynamic import below only ever runs when import.meta.env.DEV).
let knownIds = null

export function registerLedgerIds(ids) {
  knownIds = new Set(ids)
}

if (typeof import.meta !== 'undefined' && import.meta.env?.DEV && !import.meta.env?.VITEST) {
  import('../../../scripts/ledger-ids.json')
    .then((module) => registerLedgerIds(module.default))
    .catch(() => { /* scripts/build-ledger-ids.mjs has not been run yet — enforcement stays off */ })
}

/**
 * Dev-mode-only console warning for a capabilityId that isn't in the ledger. A no-op until
 * `registerLedgerIds` has been called (e.g. once ledger-ids.json exists and is wired into the
 * dev server) and always a no-op in production builds.
 */
export function warnIfUnknownCapability(id) {
  if (!knownIds || !id) return
  if (import.meta.env?.PROD) return
  if (!knownIds.has(id)) {
    console.error(`[capability] "${id}" is not in CAPABILITY-LEDGER.md — add a row or fix the id.`)
  }
}
