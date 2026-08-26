import Nav from './nav/Nav.jsx'
import { Container, LabelFrame, EmptyState, Skeleton, ProvenanceStrip, Control, Tabs, SectionHeading } from './components/index.js'

/**
 * Chalkboard — hand-lettered slate (DESIGN.md §9). No entry: "the board is already written on
 * when you walk in" — `entry: null` is deliberate, not an oversight (mirrors `hasEntry: false`
 * in registry.js's MEDIUM_META for 'chalkboard').
 *
 * @type {import('../registry.js').MediumManifest}
 */
const manifest = {
  id: 'chalkboard',
  colorScheme: 'dark',
  themeColor: '#2b3339',
  loadTokens: () => import('./tokens.css'),
  loadRenderer: () => import('./renderer/index.jsx').then((m) => m.default),
  components: { Container, LabelFrame, EmptyState, Skeleton, ProvenanceStrip, Control, Tabs, SectionHeading },
  nav: { model: 'bottom', Component: Nav, settingsAffordance: true },
  entry: null,
  motion: { profile: 'none', calmSetting: false },
  density: 'comfortable',
  vocabulary: { section: 'board', destination: 'board', settings: 'chalk tray', alerts: 'margin notes', unavailable: 'not chalked yet', error: 'wipe', loading: 'chalking' },
  type: { mono: "'IBM Plex Mono', ui-monospace, monospace", display: "'Caveat', 'Shadows Into Light', cursive", floorPx: 16 },
  acceptsAccent: false,
  budgets: { textureBytes: 15_000 },
}

export default manifest
