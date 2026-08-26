import Nav from './nav/Nav.jsx'
import Entry from './entry/Entry.jsx'
import { Container, LabelFrame, EmptyState, Skeleton, ProvenanceStrip, Control, Tabs } from './components/index.js'

/** @type {import('../registry.js').MediumManifest} */
const manifest = {
  id: 'neon',
  colorScheme: 'dark',
  themeColor: '#0d0a2e',
  loadTokens: () => import('./tokens.css'),
  loadRenderer: () => import('./renderer/index.jsx').then((m) => m.default),
  components: { Container, LabelFrame, EmptyState, Skeleton, ProvenanceStrip, Control, Tabs },
  nav: { model: 'bottom', Component: Nav, settingsAffordance: true },
  entry: { Component: Entry },
  motion: { profile: 'state', calmSetting: true },
  density: 'regular',
  vocabulary: {
    section: 'sign', destination: 'sign', settings: 'calibration', alerts: 'marquee',
    unavailable: 'dark', error: 'dead tube', loading: 'warming up',
  },
  type: { mono: "'Share Tech Mono', ui-monospace, monospace", display: "'Share Tech Mono', ui-monospace, monospace", floorPx: 16 },
  acceptsAccent: false,
  budgets: { textureBytes: 40_000 },
}

export default manifest
