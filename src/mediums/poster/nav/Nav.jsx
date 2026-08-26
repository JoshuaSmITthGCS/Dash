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
  color: 'var(--ink-black)',
  textDecoration: isActive ? 'underline' : 'none',
  fontFamily: 'var(--font-display)', fontSize: '14px', letterSpacing: '0.02em',
  padding: '10px 10px', minWidth: '44px', minHeight: '44px', display: 'inline-flex', alignItems: 'center',
})

/** Masthead across the top. */
export default function Nav() {
  return (
    <nav aria-label="Primary" style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '3px solid var(--ink-black)', background: 'var(--surface-paper)' }}>
      <div style={{ display: 'flex', flexWrap: 'wrap' }}>
        {DESTINATIONS.map((item) => <NavLink key={item.to} to={item.to} end={item.end} style={linkStyle}>{item.label}</NavLink>)}
      </div>
      <NavLink to="/settings" style={linkStyle} aria-label="Settings">SET</NavLink>
    </nav>
  )
}
