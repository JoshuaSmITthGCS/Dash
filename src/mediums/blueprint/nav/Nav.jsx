import { NavLink } from 'react-router-dom'

const ZONES = [
  { to: '/v2', label: 'HOME', end: true, coord: 'A1' },
  { to: '/v2/research', label: 'RSCH', coord: 'A2' },
  { to: '/v2/screens', label: 'SCRN', coord: 'A3' },
  { to: '/v2/portfolio', label: 'PORT', coord: 'B1' },
  { to: '/v2/markets', label: 'MKT', coord: 'B2' },
  { to: '/v2/evidence', label: 'EVID', coord: 'B3' },
]

const tabStyle = ({ isActive }) => ({
  display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '2px',
  color: 'var(--ink-primary)', textDecoration: 'none',
  fontFamily: 'var(--font-mono)', fontSize: '11px', textTransform: 'uppercase',
  padding: '8px 10px', minWidth: '44px', minHeight: '44px',
  borderTop: isActive ? '2px solid var(--rule-cyan)' : '2px solid transparent',
})

/** Zone tabs along the sheet edge — DESIGN.md §6 navigation. Plain-English labels alongside the drafting-accurate coordinate marks, the medium's own Jakob's Law compensation. */
export default function Nav() {
  return (
    <nav aria-label="Zone tabs" data-bp-titleblock="true" style={{ display: 'flex', overflowX: 'auto' }}>
      {ZONES.map((z) => (
        <NavLink key={z.to} to={z.to} end={z.end} style={tabStyle}>
          <span style={{ fontSize: '9px', color: 'var(--ink-faint)' }}>{z.coord}</span>
          {z.label}
        </NavLink>
      ))}
      <NavLink to="/settings" style={tabStyle} aria-label="Settings">SET</NavLink>
    </nav>
  )
}
