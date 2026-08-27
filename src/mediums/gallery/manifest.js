import Nav from './nav/Nav.jsx'
import Entry from './entry/Entry.jsx'
import { Container, LabelFrame, EmptyState, Skeleton, ProvenanceStrip, Control, Tabs } from './components/index.js'

/** @type {import('../registry.js').MediumManifest} */
const manifest = {
  id: 'gallery',
  colorScheme: 'light',
  themeColor: '#f2ede2',
  loadTokens: () => import('./tokens.css'),
  loadRenderer: () => import('./renderer/index.jsx').then((m) => m.default),
  components: { Container, LabelFrame, EmptyState, Skeleton, ProvenanceStrip, Control, Tabs },
  nav: { model: 'legend', Component: Nav, settingsAffordance: true },
  entry: { Component: Entry },
  motion: { profile: 'none', calmSetting: false },
  density: 'spacious',
  vocabulary: { section: 'room', destination: 'room', settings: 'front desk', alerts: 'notices', unavailable: 'not on view', error: 'conservation', loading: 'conservation in progress' },
  type: { mono: "'IBM Plex Mono', ui-monospace, monospace", display: "'Playfair Display', 'Libre Baskerville', serif", floorPx: 16 },
  acceptsAccent: false,
  budgets: { textureBytes: 20_000 },
}

export default manifest
