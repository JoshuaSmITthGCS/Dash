import Nav from './nav/Nav.jsx'
import { Container, LabelFrame, EmptyState, Skeleton, ProvenanceStrip, Control, Tabs } from './components/index.js'

/** @type {import('../registry.js').MediumManifest} */
const manifest = {
  id: 'cockpit',
  colorScheme: 'dark',
  themeColor: '#0a0d10',
  loadTokens: () => import('./tokens.css'),
  loadRenderer: () => import('./renderer/index.jsx').then((m) => m.default),
  components: { Container, LabelFrame, EmptyState, Skeleton, ProvenanceStrip, Control, Tabs },
  nav: { model: 'bottom', Component: Nav, settingsAffordance: true },
  entry: null,
  motion: { profile: 'state', calmSetting: false },
  density: 'compact',
  vocabulary: {
    section: 'channel',
    settings: 'calibration',
    alerts: 'annunciators',
    filter: 'select',
    unavailable: 'unlit',
    error: 'fault',
    loading: 'acquiring',
  },
  type: { mono: "'Share Tech Mono', 'JetBrains Mono', ui-monospace, monospace", display: "'Share Tech Mono', ui-monospace, monospace", floorPx: 16 },
  acceptsAccent: false,
  budgets: { textureBytes: 0 },
}

export default manifest
