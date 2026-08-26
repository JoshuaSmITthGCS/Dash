import Nav from './nav/Nav.jsx'
import Entry from './entry/Entry.jsx'
import { Container, LabelFrame, EmptyState, Skeleton, ProvenanceStrip, Control, Tabs } from './components/index.js'

/** @type {import('../registry.js').MediumManifest} */
const manifest = {
  id: 'book',
  colorScheme: 'light',
  themeColor: '#f7f4ec',
  loadTokens: () => import('./tokens.css'),
  loadRenderer: () => import('./renderer/index.jsx').then((m) => m.default),
  components: { Container, LabelFrame, EmptyState, Skeleton, ProvenanceStrip, Control, Tabs },
  nav: { model: 'edge', Component: Nav, settingsAffordance: true },
  entry: { Component: Entry },
  motion: { profile: 'none', calmSetting: false },
  density: 'spacious',
  vocabulary: { section: 'chapter', destination: 'chapter', settings: 'appendix', alerts: 'errata', unavailable: 'not yet reported', error: 'correction', loading: 'setting' },
  type: { mono: "'IBM Plex Mono', ui-monospace, monospace", display: "'Libre Baskerville', 'Playfair Display', serif", floorPx: 16 },
  acceptsAccent: false,
  budgets: { textureBytes: 0 },
}

export default manifest
