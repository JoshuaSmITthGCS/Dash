import { useState } from 'react'
import { NavLink } from 'react-router-dom'
import StatusBar from '../components/StatusBar.jsx'

const DESTINATIONS = [
  { to: '/v2', label: 'Home', end: true },
  { to: '/v2/research', label: 'Research' },
  { to: '/v2/screens', label: 'Screens' },
  { to: '/v2/portfolio', label: 'Portfolio' },
  { to: '/v2/markets', label: 'Markets' },
  { to: '/v2/evidence', label: 'Evidence' },
]

const itemStyle = ({ isActive }) => ({
  display: 'block', padding: '10px 12px', minHeight: '44px', color: 'var(--ink-primary)',
  textDecoration: 'none', fontFamily: 'var(--font-mono)', fontSize: '13px',
  background: isActive ? 'var(--ink-primary)' : 'transparent',
  ...(isActive ? { color: 'var(--surface-window)' } : null),
})

/**
 * Menu bar across the very top (DESIGN.md §10 navigation) — the literal "File Edit View" bar —
 * but at 390px it resolves to a single thumb-reachable trigger (bottom-anchored, 44px) that
 * opens the same menu content as a sheet, per the medium's own named Fitts's Law compensation:
 * the medium is preserved (still structurally "the menu bar"), the ergonomics are fixed.
 */
export default function Nav() {
  const [open, setOpen] = useState(false)

  return (
    <>
      <nav aria-label="Menu bar" data-beige-bevel="true" style={{ display: 'flex', alignItems: 'center', gap: '4px', padding: '2px 4px', fontSize: '12px' }}>
        <span>File</span><span>Edit</span><span>View</span><span style={{ color: 'var(--ink-faint)' }}>ValueSignal 3.2</span>
      </nav>

      {open && (
        <div data-beige-window="true" role="menu" style={{ position: 'fixed', top: '36px', left: '8px', right: '8px', zIndex: 20 }}>
          <div data-beige-titlebar="true">
            <span>Destinations</span>
            <button onClick={() => setOpen(false)} aria-label="Close menu" data-beige-bevel="true" style={{ minWidth: '24px', minHeight: '24px', fontSize: '11px' }}>×</button>
          </div>
          <div data-beige-body="true" style={{ padding: 0 }}>
            {DESTINATIONS.map((item) => (
              <NavLink key={item.to} to={item.to} end={item.end} style={itemStyle} onClick={() => setOpen(false)} role="menuitem">
                {item.label}
              </NavLink>
            ))}
            <NavLink to="/settings" style={itemStyle} onClick={() => setOpen(false)} role="menuitem">Settings</NavLink>
          </div>
        </div>
      )}

      <button
        onClick={() => setOpen((o) => !o)}
        aria-label="Open menu"
        aria-expanded={open}
        data-beige-bevel="true"
        data-pressed={open ? 'true' : undefined}
        style={{
          position: 'fixed', bottom: '32px', right: '8px', zIndex: 21,
          minWidth: '44px', minHeight: '44px', fontSize: '18px', fontFamily: 'var(--font-mono)',
        }}
      >
        ☰
      </button>

      <StatusBar text="Ready." />
    </>
  )
}
