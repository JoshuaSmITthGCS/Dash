import { NavLink } from 'react-router-dom'

const DESTINATIONS = [
  { to: '/v2', label: 'Home' },
  { to: '/v2/research', label: 'Research' },
  { to: '/v2/screens', label: 'Screens' },
  { to: '/v2/portfolio', label: 'Portfolio' },
  { to: '/v2/markets', label: 'Markets' },
  { to: '/v2/evidence', label: 'Evidence' },
]

const linkStyle = ({ isActive }) => ({
  color: 'var(--ink-primary)', textDecoration: 'none', fontFamily: 'var(--font-body)',
  fontStyle: isActive ? 'italic' : 'normal', fontSize: '14px',
  padding: '10px 12px', minWidth: '44px', minHeight: '44px', display: 'inline-flex', alignItems: 'center',
})

/** Room directory from a thumb-reachable plaque, plus next-room progression. */
export default function Nav() {
  return (
    <nav aria-label="Room directory" data-gallery-plaque="true" style={{ display: 'flex', justifyContent: 'space-between', borderTop: '1px solid var(--rule-hairline)', background: 'var(--surface-panel)' }}>
      <div style={{ display: 'flex', overflowX: 'auto' }}>
        {DESTINATIONS.map((item, i) => (
          <NavLink key={item.to} to={item.to} end={item.to === '/v2'} style={linkStyle}>
            {`Room ${i + 1} · ${item.label}`}
          </NavLink>
        ))}
      </div>
      <NavLink to="/settings" style={linkStyle} aria-label="Settings">Desk</NavLink>
    </nav>
  )
}
