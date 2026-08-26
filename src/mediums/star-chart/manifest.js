import Nav from './nav/Nav.jsx'
import Entry from './entry/Entry.jsx'
import { Container, LabelFrame, EmptyState, Skeleton, ProvenanceStrip, Control, Tabs } from './components/index.js'

/** @type {import('../registry.js').MediumManifest} */
const manifest = {
  id: 'star-chart',
  colorScheme: 'dark',
  themeColor: '#050818',
  loadTokens: () => import('./tokens.css'),
  loadRenderer: () => import('./renderer/index.jsx').then((m) => m.default),
  components: { Container, LabelFrame, EmptyState, Skeleton, ProvenanceStrip, Control, Tabs },
  nav: { model: 'legend', Component: Nav, settingsAffordance: true },
  entry: { Component: Entry },
  motion: { profile: 'none', calmSetting: true },
  density: 'spacious',
  vocabulary: { section: 'plate', destination: 'plate', settings: 'observatory log', alerts: 'transient alerts', unavailable: 'unplotted', error: 'seeing poor', loading: 'exposing' },
  type: { mono: "'IBM Plex Mono', ui-monospace, monospace", display: "'IBM Plex Sans', sans-serif", floorPx: 16 },
  acceptsAccent: false,
  budgets: { textureBytes: 0 },
}

export default manifest
