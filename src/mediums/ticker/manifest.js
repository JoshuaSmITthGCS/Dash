import Nav from './nav/Nav.jsx'
import { Container, LabelFrame, EmptyState, Skeleton, ProvenanceStrip, Control, Tabs } from './components/index.js'

/** @type {import('../registry.js').MediumManifest} */
const manifest = {
  id: 'ticker',
  colorScheme: 'dark',
  themeColor: '#050505',
  loadTokens: () => import('./tokens.css'),
  loadRenderer: () => import('./renderer/index.jsx').then((m) => m.default),
  components: { Container, LabelFrame, EmptyState, Skeleton, ProvenanceStrip, Control, Tabs },
  nav: { model: 'top', Component: Nav, settingsAffordance: true },
  entry: null,
  // The governed flip-and-reorder exception (master doc) — real values only, pauses on
  // touch/focus, full static readability under reduced-motion. Mandatory calm setting, never
  // the theme default, per its own named fatigue risk.
  motion: { profile: 'governed-ticker', calmSetting: true },
  density: 'compact',
  vocabulary: { section: 'feed', destination: 'channel', settings: 'wire settings', alerts: 'wire', unavailable: 'no print', error: 'dropped', loading: 'connecting' },
  type: { mono: "'IBM Plex Mono', ui-monospace, monospace", display: "'IBM Plex Mono', ui-monospace, monospace", floorPx: 16 },
  acceptsAccent: false,
  budgets: { textureBytes: 0 },
}

export default manifest
