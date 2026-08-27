import { NavLink } from 'react-router-dom'

const DESTINATIONS = [
  { to: '/v2', label: 'HOME', end: true },
  { to: '/v2/research', label: 'RESEARCH' },
  { to: '/v2/screens', label: 'SCREENS' },
  { to: '/v2/portfolio', label: 'PORTFOLIO' },
  { to: '/v2/markets', label: 'MARKETS' },
  { to: '/v2/evidence', label: 'EVIDENCE' },
]

const linkStyle = ({ isActive }) => ({
  color: isActive ? 'var(--brand-cyan)' : 'var(--ink-faint)',
  textDecoration: 'none', fontFamily: 'var(--font-mono)', fontSize: '11px', letterSpacing: '0.06em',
  padding: '10px 10px', minWidth: '44px', minHeight: '44px', display: 'inline-flex', alignItems: 'center',
  borderTop: isActive ? '2px solid var(--brand-cyan)' : '2px solid transparent',
})

/** Neon tab strip along the bottom, active tab lit — the nav-chrome exception to glow-means-breach. */
export default function Nav() {
  return (
    <nav aria-label="Primary" style={{ display: 'flex', justifyContent: 'space-between', borderTop: '1px solid var(--rule-hairline)', background: 'var(--surface-panel)' }}>
      <div style={{ display: 'flex' }}>
        {DESTINATIONS.map((item) => <NavLink key={item.to} to={item.to} end={item.end} style={linkStyle}>{item.label}</NavLink>)}
      </div>
      <NavLink to="/settings" style={linkStyle} aria-label="Settings">SET</NavLink>
    </nav>
  )
}
