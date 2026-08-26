import { useState } from 'react'
import { NavLink } from 'react-router-dom'
import Icon from '../../../components/Icons.jsx'
import { MobileSheet } from '../../../components/MobileSheet.jsx'

const TABS = [
  { to: '/v2', label: 'Home', icon: 'overview', end: true },
  { to: '/v2/portfolio', label: 'Portfolio', icon: 'portfolio' },
  { to: '/v2/research', label: 'Research', icon: 'research' },
  { to: '/v2/markets', label: 'Markets', icon: 'market' },
]

const MORE_ITEMS = [
  { to: '/v2/screens', label: 'Screens', icon: 'market' },
  { to: '/v2/evidence', label: 'Evidence', icon: 'method' },
  { to: '/alerts', label: 'Alerts', icon: 'more' },
  { to: '/settings', label: 'Settings', icon: 'settings' },
]

/**
 * The existing bottom navigation, ported as-is (DESIGN.md §12 navigation), reordered to the six
 * consolidated destinations: current five destinations becomes four direct tabs + a More sheet
 * absorbing Screens/Evidence plus the existing Alerts/Settings items — "Classic keeps its look,
 * not the old route sprawl" (master's own words), same interaction budget as the other eleven
 * mediums.
 */
export default function Nav() {
  const [moreOpen, setMoreOpen] = useState(false)
  return (
    <>
      <nav className="mobile-nav" aria-label="Mobile navigation">
        {TABS.map((item) => (
          <NavLink key={item.to} to={item.to} end={item.end} className={({ isActive }) => `mobile-nav-item${isActive ? ' active' : ''}`}>
            <span className="mobile-nav-icon"><Icon name={item.icon} size={18} /></span>
            <span>{item.label}</span>
          </NavLink>
        ))}
        <button type="button" className={`mobile-nav-item${moreOpen ? ' active' : ''}`}
          aria-haspopup="dialog" aria-expanded={moreOpen} onClick={() => setMoreOpen(true)}>
          <span className="mobile-nav-icon"><Icon name="more" size={18} /></span>
          <span>More</span>
        </button>
      </nav>
      <MobileSheet open={moreOpen} title="More" onClose={() => setMoreOpen(false)} className="mobile-more-sheet">
        <nav className="mobile-more-nav" aria-label="More screens">
          <div className="mobile-more-group">
            {MORE_ITEMS.map((item) => (
              <NavLink key={item.to} to={item.to} onClick={() => setMoreOpen(false)} className={({ isActive }) => `mobile-more-link${isActive ? ' active' : ''}`}>
                <Icon name={item.icon} size={16} /><span>{item.label}</span>
              </NavLink>
            ))}
          </div>
        </nav>
      </MobileSheet>
    </>
  )
}
