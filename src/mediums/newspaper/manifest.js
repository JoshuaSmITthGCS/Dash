import Nav from './nav/Nav.jsx'
import Entry from './entry/Entry.jsx'
import { Container, LabelFrame, EmptyState, Skeleton, ProvenanceStrip, Control, Tabs } from './components/index.js'

/** @type {import('../registry.js').MediumManifest} */
const manifest = {
  id: 'newspaper',
  colorScheme: 'light',
  themeColor: '#faf6ee',
  loadTokens: () => import('./tokens.css'),
  loadRenderer: () => import('./renderer/index.jsx').then((m) => m.default),
  components: { Container, LabelFrame, EmptyState, Skeleton, ProvenanceStrip, Control, Tabs },
  nav: { model: 'top', Component: Nav, settingsAffordance: true },
  entry: { Component: Entry },
  motion: { profile: 'none', calmSetting: false },
  density: 'comfortable',
  vocabulary: { section: 'section', destination: 'section', settings: 'masthead', alerts: 'the wire', unavailable: 'not yet reported', error: 'correction', loading: 'developing' },
  type: { mono: "'IBM Plex Mono', ui-monospace, monospace", display: "'Playfair Display', 'Libre Baskerville', serif", floorPx: 16 },
  acceptsAccent: false,
  budgets: { textureBytes: 0 },
}

export default manifest
