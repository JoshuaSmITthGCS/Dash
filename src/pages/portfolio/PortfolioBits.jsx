// Small presentational pieces shared across the three portfolio views.

import { NavLink } from 'react-router-dom'
import { ResponsiveControlPanel } from '../../components/MobileSheet.jsx'
import { PORTFOLIO_SORT_OPTIONS } from '../../lib/portfolioSort'
import { moveColor, signedPct } from './format.js'

export const PORTFOLIO_NAV = [
  { to: '/portfolio', label: 'Summary', end: true },
  { to: '/portfolio/performance', label: 'Performance' },
  { to: '/portfolio/data-overview', label: 'Data overview' },
]

export const PORTFOLIO_PAGE_COPY = {
  summary: {
    title: <>My <span className="accent">portfolio</span></>,
    description: 'Your holdings, suggested actions, and current allocation.',
  },
  performance: {
    title: <>Portfolio <span className="accent">performance</span></>,
    description: 'Your time-weighted return and a fair comparison with the selected benchmark.',
  },
  data: {
    title: <>Portfolio <span className="accent">data overview</span></>,
    description: 'Why your portfolio moved and the evidence behind its standard measures.',
  },
}

export function PortfolioNavigation() {
  return (
    <nav className="screen-nav portfolio-section-nav" aria-label="Portfolio sections">
      {PORTFOLIO_NAV.map((item) => (
        <NavLink key={item.to} to={item.to} end={item.end}
          className={({ isActive }) => isActive ? 'active' : ''}>{item.label}</NavLink>
      ))}
    </nav>
  )
}

export function Move({ value, digits = 1 }) {
  return <span className="mono" style={{ color: moveColor(value) }}>{signedPct(value, digits)}</span>
}

/** Where the binding stop sits and how far away it is – visible before it's hit, not just after. */
export function StopLossNote({ stopLoss }) {
  if (!stopLoss || stopLoss.bindingPrice == null) return null
  const close = stopLoss.distancePct != null && stopLoss.distancePct <= 5
  const past = stopLoss.distancePct != null && stopLoss.distancePct < 0
  return (
    <span className="mono stop-loss-note" style={{ color: past ? 'var(--neg)' : close ? 'var(--warn)' : 'var(--text-faint)', fontSize: 12 }}>
      Stop ${stopLoss.bindingPrice.toFixed(2)}
      {stopLoss.distancePct != null && (
        past ? ` · ${Math.abs(stopLoss.distancePct).toFixed(1)}% past it` : ` · ${stopLoss.distancePct.toFixed(1)}% away`
      )}
    </span>
  )
}

export function PortfolioSortToolbar({ sort, selectedLabel, onSortKey, onToggleDirection }) {
  const controls = (
    <div className="portfolio-sort-toolbar" aria-label="Portfolio sorting controls">
      <label>
        <span>Sort holdings</span>
        <select value={sort.key} onChange={(event) => onSortKey(event.target.value)}>
          {PORTFOLIO_SORT_OPTIONS.map((option) => (
            <option key={option.key} value={option.key}>{option.label}</option>
          ))}
        </select>
      </label>
      <button
        className="secondary-button portfolio-sort-direction"
        onClick={onToggleDirection}
        aria-label={`Reverse ${selectedLabel || 'portfolio'} sort order`}
      >
        {sort.direction === 'asc' ? 'Ascending ↑' : 'Descending ↓'}
      </button>
    </div>
  )
  return <ResponsiveControlPanel label={`Sort: ${selectedLabel || 'holdings'}`} title="Sort holdings">{controls}</ResponsiveControlPanel>
}
