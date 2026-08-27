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
  color: isActive ? 'var(--ink-primary)' : 'var(--ink-faint)', textDecoration: 'none',
  fontFamily: 'var(--font-mono)', fontSize: '12px',
  padding: '10px 8px', minWidth: '44px', minHeight: '44px', display: 'inline-flex', alignItems: 'center',
})

/**
 * A corner legend that doubles as navigation, persistent (never collapsed) and full-width so it
 * stays thumb-reachable at 390px — the master's corner-affordance ban means it can be styled
 * like a corner key, but it must not actually hide in one, per this medium's own named
 * Jakob's-Law compensation (DESIGN.md §7).
 */
export default function Nav() {
  return (
    <nav aria-label="Legend" data-sc-legend="true" style={{ position: 'sticky', bottom: 0, display: 'flex', flexDirection: 'column', gap: '4px' }}>
      <p style={{ margin: 0, color: 'var(--ink-faint)' }}>
        <span style={{ color: 'var(--ink-primary)' }}>●</span> established &nbsp;
        <span>○</span> accumulating &nbsp;
        <span style={{ color: 'var(--state-breach)' }}>✛</span> breached
      </p>
      <div style={{ display: 'flex', flexWrap: 'wrap' }}>
        {DESTINATIONS.map((item) => <NavLink key={item.to} to={item.to} end={item.end} style={linkStyle}>{item.label}</NavLink>)}
        <NavLink to="/settings" style={linkStyle} aria-label="Settings">Settings</NavLink>
      </div>
    </nav>
  )
}
