import { useMemo, useState } from 'react'
import { NavLink } from 'react-router-dom'
import { useData } from '../lib/useData'
import { Empty, Loading } from '../components/Bits'
import ResultCards from '../components/ResultCards.jsx'
import { usePreferences } from '../lib/PreferencesContext.jsx'
import { ResponsiveControlPanel } from '../components/MobileSheet.jsx'

export const SCREEN_NAV = [
  ['/screens/fast-growth', 'Fast growth'],
  ['/screens/options', 'Best multi-day options'],
  ['/screens/covered-call', 'Covered call'], ['/screens/cash-secured-put', 'Cash-secured put'],
  ['/screens/protective-put', 'Protective put'], ['/screens/collar', 'Collar'],
  ['/screens/vertical-spread', 'Vertical spread'], ['/screens/advanced-strategies', 'Advanced strategies'],
  ['/screens/momentum', 'Momentum'], ['/screens/quality-value', 'Quality at valuation lows'],
  ['/screens/earnings', 'Earnings timeliness'], ['/screens/matrix', 'Structural vs tactical'],
  ['/screens/early-session', 'Early session'],
  ['/screens/shadow', 'Shadow portfolios'], ['/screens/validation', 'Live validation'],
  ['/screens/politics', 'Politics trade alert'],
  ['/screens/themes', 'Theme exposure'],
]

const capBucket = (value) => value >= 10e9 ? 'large' : value >= 2e9 ? 'mid' : 'small'
const number = (value) => value == null ? '–' : Number(value).toFixed(1)

export function ScreenNavigation() {
  return <nav className="screen-nav" aria-label="Research screens">{SCREEN_NAV.map(([to, label]) =>
    <NavLink key={to} to={to} className={({ isActive }) => isActive ? 'active' : ''}>{label}</NavLink>)}</nav>
}

export default function ResearchScreen({ file, eyebrow, title, description }) {
  const { data, loading, error } = useData(file)
  const { preferences } = usePreferences()
  const [filters, setFilters] = useState({ sector: 'all', cap: 'all', confidence: 0, liquidity: 0,
    structural: 0, tactical: 0, membership: 'all' })
  const sourceRows = data?.results || []
  const sectors = useMemo(() => [...new Set(sourceRows.map((row) => row.sector).filter(Boolean))].sort(), [sourceRows])
  const rows = sourceRows.filter((row) => filters.sector === 'all' || row.sector === filters.sector)
    .filter((row) => filters.cap === 'all' || capBucket(row.market_cap || 0) === filters.cap)
    .filter((row) => (row.confidence || 0) * 100 >= filters.confidence)
    .filter((row) => (row.median_dollar_volume_60d || 0) >= filters.liquidity * 1e6)
    .filter((row) => (row.structural_score || 0) >= filters.structural && (row.tactical_score || 0) >= filters.tactical)
    .filter((row) => filters.membership === 'all' || Boolean(row.current_membership) === (filters.membership === 'yes'))
  const update = (key) => (event) => setFilters((current) => ({ ...current, [key]: event.target.value }))

  return <>
    <ScreenNavigation />
    <div className="page-head"><div><span className="eyebrow">{eyebrow}</span><h1 className="page-title">{title}</h1>
      <p className="page-sub">{description}</p></div><div className="result-count"><strong>{rows.length}</strong><span>results</span></div></div>
    {loading ? <Loading /> : error ? <div className="card etf-state" role="alert"><strong>Screen snapshot unavailable</strong><span>{error.message}</span></div> : <>
      <ResponsiveControlPanel label="Filter results" title="Filter results"><div className="screen-filters" aria-label="Screen filters">
        <label>Sector<select value={filters.sector} onChange={update('sector')}><option value="all">All</option>{sectors.map((sector) => <option key={sector}>{sector}</option>)}</select></label>
        <label>Market cap<select value={filters.cap} onChange={update('cap')}><option value="all">All</option><option value="large">Large</option><option value="mid">Mid</option><option value="small">Small</option></select></label>
        <label>Min confidence<input type="number" min="0" max="100" value={filters.confidence} onChange={update('confidence')} /></label>
        <label>Min liquidity ($M)<input type="number" min="0" value={filters.liquidity} onChange={update('liquidity')} /></label>
        <label>Min structural<input type="number" min="0" max="100" value={filters.structural} onChange={update('structural')} /></label>
        <label>Min tactical<input type="number" min="0" max="100" value={filters.tactical} onChange={update('tactical')} /></label>
        <label>Membership<select value={filters.membership} onChange={update('membership')}><option value="all">All</option><option value="yes">Members</option><option value="no">Non-members</option></select></label>
      </div></ResponsiveControlPanel>
      {!rows.length ? <Empty note={data?.status === 'unavailable' ? `Unavailable: ${data.reason_code}` : 'No results match these filters.'} /> : <>
      <ResultCards rows={rows} getKey={(row) => row.ticker} variant={preferences.mobileResearchView}
        title={(row) => `#${row.rank ?? '–'} · ${row.ticker}`}
        subtitle={(row) => row.peer_group || row.sector || 'Unclassified'}
        fields={preferences.mobileResearchView === 'detailed' ? [
          { label: 'Classification', value: (row) => row.classification || (row.eligibility ? 'Eligible' : 'Ineligible') },
          { label: 'Percentile', value: (row) => number(row.percentile) },
          { label: 'Structural', value: (row) => number(row.structural_score) },
          { label: 'Tactical', value: (row) => number(row.tactical_score) },
          { label: 'Confidence', value: (row) => `${number((row.confidence || 0) * 100)}%` },
          { label: 'Warnings', value: (row) => (row.reason_codes || []).join(', ') || 'None' },
        ] : [
          { label: 'Classification', value: (row) => row.classification || (row.eligibility ? 'Eligible' : 'Ineligible') },
          { label: 'Composite', value: (row) => number(row.percentile) },
          { label: 'Confidence', value: (row) => `${number((row.confidence || 0) * 100)}%` },
        ]} />
      <div className="research-table card"><table>
        <thead><tr><th>Rank</th><th>Ticker</th><th>Classification</th><th>Peer group</th><th className="num">Percentile</th><th className="num">Structural</th><th className="num">Tactical</th><th className="num">Confidence</th><th>Warnings</th></tr></thead>
        <tbody>{rows.map((row) => <tr key={row.ticker}><td>#{row.rank ?? '–'}</td><td><b>{row.ticker}</b></td><td>{row.classification || (row.eligibility ? 'Eligible' : 'Ineligible')}</td><td>{row.peer_group || '–'}</td><td className="mono num">{number(row.percentile)}</td><td className="mono num">{number(row.structural_score)}</td><td className="mono num">{number(row.tactical_score)}</td><td className="mono num">{number((row.confidence || 0) * 100)}%</td><td>{(row.reason_codes || []).join(', ') || '–'}</td></tr>)}</tbody>
      </table></div></>}
      <p className="disclaimer">Schema {data?.schema_version || '–'} · model {data?.model_version || '–'} · config {data?.config_version || '–'}. Rankings are hypotheses for prospective validation, not claims of outperformance.</p>
    </>}
  </>
}
