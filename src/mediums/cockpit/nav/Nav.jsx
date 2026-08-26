import { NavLink } from 'react-router-dom'

const DESTINATIONS = [
  { to: '/v2', label: 'HOME', end: true },
  { to: '/v2/research', label: 'RSCH' },
  { to: '/v2/screens', label: 'SCRN' },
  { to: '/v2/portfolio', label: 'PORT' },
  { to: '/v2/markets', label: 'MKT' },
  { to: '/v2/evidence', label: 'EVID' },
]

const linkStyle = ({ isActive }) => ({
  color: isActive ? 'var(--state-established)' : 'var(--ink-secondary)',
  textDecoration: 'none',
  fontFamily: 'var(--font-mono)',
  fontSize: '12px',
  letterSpacing: '0.06em',
  padding: '10px 12px',
  minWidth: '44px',
  minHeight: '44px',
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  borderTop: isActive ? '2px solid var(--state-established)' : '2px solid transparent',
})

/** Channel selector — bottom bracket bar at 390px, left rail at desktop. No entry page. */
export default function Nav() {
  return (
    <nav aria-label="Primary" data-cockpit-nav="true" style={{ display: 'flex', justifyContent: 'space-between', borderTop: '1px solid var(--rule-hairline)', background: 'var(--surface-bezel)' }}>
      <div style={{ display: 'flex' }}>
        {DESTINATIONS.map((item) => (
          <NavLink key={item.to} to={item.to} end={item.end} style={linkStyle}>{item.label}</NavLink>
        ))}
      </div>
      <NavLink to="/settings" style={linkStyle} aria-label="Settings">SET</NavLink>
    </nav>
  )
}
