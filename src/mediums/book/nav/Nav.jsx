import { NavLink, useLocation } from 'react-router-dom'

const DESTINATIONS = [
  { to: '/v2', label: 'Home', initial: 'H', end: true },
  { to: '/v2/research', label: 'Research', initial: 'R' },
  { to: '/v2/screens', label: 'Screens', initial: 'S' },
  { to: '/v2/portfolio', label: 'Portfolio', initial: 'P' },
  { to: '/v2/markets', label: 'Markets', initial: 'M' },
  { to: '/v2/evidence', label: 'Evidence', initial: 'E' },
]

const railStyle = ({ isActive }) => ({
  display: 'flex', alignItems: 'center', justifyContent: 'center',
  minWidth: '44px', minHeight: '44px', textDecoration: 'none',
  color: 'var(--ink-primary)', fontFamily: 'var(--font-mono)', fontSize: '13px',
  fontWeight: isActive ? 700 : 400,
  borderLeft: isActive ? '3px solid var(--ink-editorial)' : '3px solid transparent',
})

/** Running head + a thumb index down the edge — DESIGN.md §5 navigation. */
export default function Nav() {
  const location = useLocation()
  const current = DESTINATIONS.find((d) => (d.end ? location.pathname === d.to : location.pathname.startsWith(d.to))) || DESTINATIONS[0]

  return (
    <>
      <header data-book-index="true" style={{ borderBottom: '1px solid var(--rule-hairline)', padding: '6px 12px', display: 'flex', justifyContent: 'space-between' }}>
        <span>Ch. {DESTINATIONS.indexOf(current) + 1} · {current.label.toUpperCase()}</span>
        <span>ValueSignal</span>
      </header>
      <nav
        aria-label="Thumb index"
        style={{
          position: 'fixed', top: 0, right: 0, bottom: 0, zIndex: 15,
          display: 'flex', flexDirection: 'column', justifyContent: 'center',
          background: 'var(--surface-panel)', borderLeft: '1px solid var(--rule-hairline)',
        }}
      >
        {DESTINATIONS.map((item) => (
          <NavLink key={item.to} to={item.to} end={item.end} style={railStyle} aria-label={item.label}>
            {item.initial}
          </NavLink>
        ))}
        <NavLink to="/settings" style={railStyle} aria-label="Settings">·</NavLink>
      </nav>
    </>
  )
}
