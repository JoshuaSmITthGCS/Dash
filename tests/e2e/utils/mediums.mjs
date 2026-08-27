/**
 * The twelve medium ids, mirrored from `src/mediums/registry.js`'s `MEDIUM_META`. Duplicated
 * here (rather than imported) because `registry.js` uses `import.meta.glob`, a Vite build-time
 * macro that only resolves inside Vite's own transform pipeline (the app itself, or vitest) —
 * not in a plain Node ESM context, which is what `playwright.config.mjs` and every spec file run
 * under. Keep this list in sync with `MEDIUM_META` by hand; `parity.spec.mjs`'s nav-parity check
 * (#2) visits every id here and would fail loudly on a stale/misspelled id (the medium simply
 * wouldn't load), giving a second, independent check against drift.
 */
export const MEDIUM_IDS = Object.freeze([
  'gallery', 'cockpit', 'neon', 'poster', 'ticker', 'book',
  'blueprint', 'star-chart', 'newspaper', 'chalkboard', 'beige-box', 'classic',
])

export const MEDIUMS_WITH_ENTRY = Object.freeze([
  'gallery', 'neon', 'poster', 'book', 'blueprint', 'star-chart', 'newspaper', 'beige-box',
])

export const VIEWPORTS = Object.freeze([
  { name: '390', width: 390, height: 844 },
  { name: '430', width: 430, height: 932 },
])
