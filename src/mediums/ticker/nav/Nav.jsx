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
  color: isActive ? 'var(--ink-primary)' : 'var(--ink-faint)',
  textDecoration: 'none', fontFamily: 'var(--font-mono)', fontSize: '11px',
  padding: '10px', minWidth: '44px', minHeight: '44px', display: 'inline-flex', alignItems: 'center',
  borderBottom: isActive ? '1px solid var(--ink-primary)' : '1px solid transparent',
})

/** Session bar across the top; destinations are channels. No entry. */
export default function Nav() {
  return (
    <nav aria-label="Primary" style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid var(--rule-hairline)' }}>
      <div style={{ display: 'flex', overflowX: 'auto' }}>
        {DESTINATIONS.map((item) => <NavLink key={item.to} to={item.to} end={item.end} style={linkStyle}>{item.label}</NavLink>)}
      </div>
      <NavLink to="/settings" style={linkStyle} aria-label="Settings">SET</NavLink>
    </nav>
  )
}
