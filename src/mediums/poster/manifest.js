import Nav from './nav/Nav.jsx'
import Entry from './entry/Entry.jsx'
import { Container, LabelFrame, EmptyState, Skeleton, ProvenanceStrip, Control, Tabs } from './components/index.js'

/** @type {import('../registry.js').MediumManifest} */
const manifest = {
  id: 'poster',
  colorScheme: 'light',
  themeColor: '#f6f1e6',
  loadTokens: () => import('./tokens.css'),
  loadRenderer: () => import('./renderer/index.jsx').then((m) => m.default),
  components: { Container, LabelFrame, EmptyState, Skeleton, ProvenanceStrip, Control, Tabs },
  nav: { model: 'top', Component: Nav, settingsAffordance: true },
  entry: { Component: Entry },
  motion: { profile: 'none', calmSetting: false },
  density: 'regular',
  vocabulary: { section: 'plate', settings: 'press settings', alerts: 'bulletin', unavailable: 'unprinted', error: 'misprint', loading: 'press running' },
  type: { mono: "'IBM Plex Mono', ui-monospace, monospace", display: "'Anton', 'Arial Narrow', sans-serif", floorPx: 16 },
  acceptsAccent: false,
  budgets: { textureBytes: 0 },
}

export default manifest
