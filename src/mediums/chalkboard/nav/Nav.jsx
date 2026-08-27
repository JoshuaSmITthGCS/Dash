import { NavLink } from 'react-router-dom'

const DESTINATIONS = [
  { to: '/v2', label: 'HOME' },
  { to: '/v2/research', label: 'RSCH' },
  { to: '/v2/screens', label: 'SCRN' },
  { to: '/v2/portfolio', label: 'PORT' },
  { to: '/v2/markets', label: 'MKT' },
  { to: '/v2/evidence', label: 'EVID' },
]

const linkStyle = ({ isActive }) => ({
  color: 'var(--chalk-white)', textDecoration: isActive ? 'underline' : 'none', textDecorationStyle: isActive ? 'double' : undefined,
  fontFamily: 'var(--font-mono)', fontSize: '12px',
  padding: '10px 8px', minWidth: '44px', minHeight: '44px', display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
})

/** Chalk tray along the bottom edge, thumb-reachable — DESIGN.md §9 navigation. */
export default function Nav() {
  return (
    <nav
      aria-label="Chalk tray"
      style={{
        display: 'flex', justifyContent: 'space-between', overflowX: 'auto',
        borderTop: '2px solid var(--chalk-white)', background: 'var(--surface-slate)',
        position: 'sticky', bottom: 0,
      }}
    >
      <div style={{ display: 'flex' }}>
        {DESTINATIONS.map((item) => (
          <NavLink key={item.to} to={item.to} end={item.to === '/v2'} style={linkStyle}>
            {`✎${item.label}`}
          </NavLink>
        ))}
      </div>
      <NavLink to="/settings" style={linkStyle} aria-label="Settings">✎SET</NavLink>
    </nav>
  )
}
