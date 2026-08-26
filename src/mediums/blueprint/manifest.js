import Nav from './nav/Nav.jsx'
import Entry from './entry/Entry.jsx'
import { Container, LabelFrame, EmptyState, Skeleton, ProvenanceStrip, Control, Tabs } from './components/index.js'

/** @type {import('../registry.js').MediumManifest} */
const manifest = {
  id: 'blueprint',
  colorScheme: 'dark',
  themeColor: '#0b1e33',
  loadTokens: () => import('./tokens.css'),
  loadRenderer: () => import('./renderer/index.jsx').then((m) => m.default),
  components: { Container, LabelFrame, EmptyState, Skeleton, ProvenanceStrip, Control, Tabs },
  nav: { model: 'edge', Component: Nav, settingsAffordance: true },
  entry: { Component: Entry },
  motion: { profile: 'none', calmSetting: false },
  density: 'comfortable',
  vocabulary: { section: 'sheet', destination: 'zone', settings: 'title block', alerts: 'markups', unavailable: 'not yet specified', error: 'revision', loading: 'drafting' },
  type: { mono: "'IBM Plex Mono', ui-monospace, monospace", display: "'Space Grotesk', 'IBM Plex Sans', sans-serif", floorPx: 16 },
  acceptsAccent: false,
  budgets: { textureBytes: 3_000 },
}

export default manifest
