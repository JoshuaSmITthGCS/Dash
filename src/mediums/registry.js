/**
 * The medium registry: static, synchronous metadata for all twelve mediums (available even
 * before a medium's manifest.js file exists on disk — Settings' picker and the pre-paint IIFE
 * both need this without waiting on a dynamic import), plus a lazy loader for whichever
 * manifests are actually implemented.
 *
 * `import.meta.glob` (not a template-literal `import(`./${id}/manifest.js`)`) is deliberate:
 * Vite/Rolldown can statically enumerate every `manifest.js` that exists at build time, so a
 * medium not yet built (Phase 2b ships them one at a time) is simply absent from the glob
 * instead of being a broken dynamic import path that fails the build.
 */

// Sync metadata — safe to import from anywhere, including the pre-paint script's data table
// and PreferencesContext's acceptsAccent guard, neither of which can wait on a lazy import.
export const MEDIUM_META = Object.freeze([
  { id: 'gallery', label: 'Gallery', colorScheme: 'light', themeColor: '#f2ede2', acceptsAccent: false, hasEntry: true, shipAtLaunch: true },
  { id: 'cockpit', label: 'Cockpit', colorScheme: 'dark', themeColor: '#0a0d10', acceptsAccent: false, hasEntry: false, shipAtLaunch: false },
  { id: 'neon', label: 'Neon', colorScheme: 'dark', themeColor: '#0d0a2e', acceptsAccent: false, hasEntry: true, shipAtLaunch: false },
  { id: 'poster', label: 'Poster', colorScheme: 'light', themeColor: '#f6f1e6', acceptsAccent: false, hasEntry: true, shipAtLaunch: false },
  { id: 'ticker', label: 'Ticker', colorScheme: 'dark', themeColor: '#050505', acceptsAccent: false, hasEntry: false, shipAtLaunch: true },
  { id: 'book', label: 'Book', colorScheme: 'light', themeColor: '#f7f4ec', acceptsAccent: false, hasEntry: true, shipAtLaunch: false },
  { id: 'blueprint', label: 'Blueprint', colorScheme: 'dark', themeColor: '#0b1e33', acceptsAccent: false, hasEntry: true, shipAtLaunch: false },
  { id: 'star-chart', label: 'Star Chart', colorScheme: 'dark', themeColor: '#050818', acceptsAccent: false, hasEntry: true, shipAtLaunch: false },
  { id: 'newspaper', label: 'Newspaper', colorScheme: 'light', themeColor: '#faf6ee', acceptsAccent: false, hasEntry: true, shipAtLaunch: true },
  { id: 'chalkboard', label: 'Chalkboard', colorScheme: 'dark', themeColor: '#2b3339', acceptsAccent: false, hasEntry: false, shipAtLaunch: true },
  { id: 'beige-box', label: 'Beige Box', colorScheme: 'light', themeColor: '#d9d3c4', acceptsAccent: false, hasEntry: true, shipAtLaunch: true },
  { id: 'classic', label: 'Classic — what you have now', colorScheme: 'dark', themeColor: '#0a0e14', acceptsAccent: true, hasEntry: false, shipAtLaunch: true },
])

const META_BY_ID = new Map(MEDIUM_META.map((entry) => [entry.id, entry]))

export const DEFAULT_MEDIUM_DURING_BUILD = 'classic'
// Flips once cutover ships every medium behind the new shell (Phase 3 hard gate cleared).
export const DEFAULT_MEDIUM_AT_CUTOVER = 'gallery'

export function getMediumMeta(id) {
  return META_BY_ID.get(id) || null
}

export function getAllMediumMeta() {
  return MEDIUM_META
}

export function isKnownMedium(id) {
  return META_BY_ID.has(id)
}

// Vite feature: enumerates every `./<id>/manifest.js` that exists on disk right now. Each value
// is `() => Promise<Module>` — nothing is eagerly imported, and a medium with no manifest.js yet
// (most of them, until Phase 2b builds them one at a time) simply has no entry here.
const manifestLoaders = import.meta.glob('./*/manifest.js')

function loaderFor(id) {
  return manifestLoaders[`./${id}/manifest.js`]
}

export function isMediumImplemented(id) {
  return Boolean(loaderFor(id))
}

/**
 * Loads and returns one medium's manifest (the module's default export). Rejects with a clear,
 * catchable error for a medium that's registered in MEDIUM_META but not yet built — MediumShell
 * uses this to show "medium not yet available" instead of a raw import error during the Phase
 * 2b rollout, when only some of the twelve manifests exist.
 */
export async function loadMedium(id) {
  if (!isKnownMedium(id)) throw new Error(`Unknown medium "${id}" — not in MEDIUM_META.`)
  const loader = loaderFor(id)
  if (!loader) throw new Error(`Medium "${id}" is registered but its manifest.js has not been built yet.`)
  const module = await loader()
  return module.default
}
