import Nav from './nav/Nav.jsx'
import Entry from './entry/Entry.jsx'
import { Container, LabelFrame, EmptyState, Skeleton, ProvenanceStrip, Control, Tabs, StatusBar } from './components/index.js'

/**
 * Beige Box — mid-90s desktop (DESIGN.md §10). `98.css`'s bevel geometry, title-bar structure,
 * disabled treatment, and dotted focus rectangles are extracted as patterns here — the library
 * itself is never imported wholesale.
 *
 * @type {import('../registry.js').MediumManifest}
 */
const manifest = {
  id: 'beige-box',
  colorScheme: 'light',
  themeColor: '#d9d3c4',
  loadTokens: () => import('./tokens.css'),
  loadRenderer: () => import('./renderer/index.jsx').then((m) => m.default),
  components: { Container, LabelFrame, EmptyState, Skeleton, ProvenanceStrip, Control, Tabs, StatusBar },
  nav: { model: 'menu-bar', Component: Nav, settingsAffordance: true },
  entry: { Component: Entry },
  motion: { profile: 'none', calmSetting: false },
  density: 'comfortable',
  vocabulary: { section: 'window', destination: 'window', settings: 'control panel', alerts: 'notifications', unavailable: 'disabled', error: 'dialog', loading: 'loading' },
  type: { mono: "'IBM Plex Mono', ui-monospace, monospace", display: "'IBM Plex Mono', ui-monospace, monospace", floorPx: 16 },
  acceptsAccent: false,
  budgets: { textureBytes: 8_000 },
}

export default manifest
