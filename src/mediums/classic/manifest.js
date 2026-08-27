import Nav from './nav/Nav.jsx'
import { Container, LabelFrame, EmptyState, Skeleton, ProvenanceStrip, Control, Tabs } from './components/index.js'

/**
 * Classic — what you have now (DESIGN.md §12). Built last, in an isolated pass (Phase 2c).
 * Preserves the current 3.2.0 presentation intact. The only medium permitted to reuse existing
 * components and CSS — see each component file for exactly what's ported vs newly adapted.
 * `acceptsAccent: true` is the one manifest in the whole system where this is true; every other
 * medium's inline `--brand-primary`/`--accent`/`--accent-ink` write is suppressed by
 * `PreferencesContext`'s guard (Phase 2a).
 *
 * @type {import('../registry.js').MediumManifest}
 */
const manifest = {
  id: 'classic',
  colorScheme: 'dark',
  themeColor: '#0a0e14',
  loadTokens: () => import('./tokens.css'),
  loadRenderer: () => import('./renderer/index.jsx').then((m) => m.default),
  components: { Container, LabelFrame, EmptyState, Skeleton, ProvenanceStrip, Control, Tabs },
  nav: { model: 'bottom', Component: Nav, settingsAffordance: true },
  entry: null,
  motion: { profile: 'existing', calmSetting: false },
  density: 'comfortable',
  vocabulary: { section: 'section', destination: 'destination', settings: 'settings', alerts: 'alerts', unavailable: 'unavailable', error: 'error', loading: 'loading' },
  type: { mono: "'Geist Mono', ui-monospace, monospace", display: "'Geist Sans', sans-serif", floorPx: 16 },
  acceptsAccent: true,
  budgets: { textureBytes: 0 },
}

export default manifest
