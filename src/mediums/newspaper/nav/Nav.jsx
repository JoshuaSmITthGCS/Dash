import { NavLink } from 'react-router-dom'

const DESTINATIONS = [
  { to: '/v2', label: 'Home', end: true },
  { to: '/v2/research', label: 'Research' },
  { to: '/v2/screens', label: 'Screens' },
  { to: '/v2/portfolio', label: 'Portfolio' },
  { to: '/v2/markets', label: 'Markets' },
  { to: '/v2/evidence', label: 'Evidence' },
]

const linkStyle = ({ isActive }) => ({
  color: 'var(--ink-primary)', textDecoration: 'none',
  fontFamily: 'var(--font-display)', fontSize: '13px', letterSpacing: '0.02em',
  borderBottom: isActive ? '2px solid var(--accent-standfirst)' : '2px solid transparent',
  padding: '10px 10px', minWidth: '44px', minHeight: '44px', display: 'inline-flex', alignItems: 'center',
})

/** Masthead section tabs — DESIGN.md §8 navigation. */
export default function Nav() {
  return (
    <header style={{ background: 'var(--surface-panel)', borderBottom: '3px double var(--ink-primary)' }}>
      <p style={{ textAlign: 'center', fontFamily: 'var(--font-display)', fontSize: '22px', margin: '8px 0 0', letterSpacing: '0.04em' }}>
        THE VALUESIGNAL REPORT
      </p>
      <nav aria-label="Masthead sections" style={{ display: 'flex', justifyContent: 'center', flexWrap: 'wrap', gap: '4px' }}>
        {DESTINATIONS.map((item) => <NavLink key={item.to} to={item.to} end={item.end} style={linkStyle}>{item.label}</NavLink>)}
        <NavLink to="/settings" style={linkStyle} aria-label="Settings">Settings</NavLink>
      </nav>
    </header>
  )
}
