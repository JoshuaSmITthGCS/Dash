import { useMemo, useState } from 'react'
import { NavLink } from 'react-router-dom'
import { useData } from '../lib/useData'
import { Empty, Loading } from '../components/Bits'
import DataTable from '../components/DataTable.jsx'
import { usePreferences } from '../lib/PreferencesContext.jsx'
import { ResponsiveControlPanel } from '../components/MobileSheet.jsx'
import ScatterChart from '../components/ScatterChart.jsx'

// Every options screen collapses into the single "Options" tab below; the individual
// strategies live on the sub-nav that page renders (OPTIONS_NAV), so the top-level row
// stays short enough to scan on a phone.
export const SCREEN_NAV = [
  ['/screens/swing', 'Swing signals'],
  ['/screens/fast-growth', 'Fast growth'],
  ['/screens/options', 'Options'],
  ['/screens/momentum', 'Momentum'], ['/screens/quality-value', 'Quality at valuation lows'],
  ['/screens/earnings', 'Earnings timeliness'], ['/screens/matrix', 'Structural vs tactical'],
  ['/screens/early-session', 'Early session'],
  ['/screens/backtests', 'Backtest comparison'],
  ['/screens/shadow', 'Shadow portfolios'], ['/screens/validation', 'Live validation'],
  ['/screens/politics', 'Politics trade alert'],
  ['/screens/institutional', 'Institutional accumulation'],
  ['/screens/themes', 'Theme exposure'],
]

// Sub-tabs shown once you are inside Options. `strategyId` keys into STRATEGY_SCREENS;
// the index entry (no id) is the multi-day call/put screen at /screens/options itself.
export const OPTIONS_NAV = [
  { to: '/screens/options', label: 'Multi-day', end: true },
  { to: '/screens/options/short-term-trades', label: 'Short-term', strategyId: 'short-term-trades' },
  { to: '/screens/options/covered-call', label: 'Covered call', strategyId: 'covered-call' },
  { to: '/screens/options/cash-secured-put', label: 'Cash-secured put', strategyId: 'cash-secured-put' },
  { to: '/screens/options/protective-put', label: 'Protective put', strategyId: 'protective-put' },
  { to: '/screens/options/collar', label: 'Collar', strategyId: 'collar' },
  { to: '/screens/options/vertical-spread', label: 'Vertical spread', strategyId: 'vertical-spread' },
  { to: '/screens/options/advanced-strategies', label: 'Advanced', strategyId: 'advanced-strategies' },
]

const capBucket = (value) => value >= 10e9 ? 'large' : value >= 2e9 ? 'mid' : 'small'
const number = (value) => value == null ? '–' : Number(value).toFixed(1)

// Structural-vs-tactical is the one screen whose rows carry both axes of the quadrant
// scatter. Tone follows the model's own classification, not a re-derived threshold.
const CLASSIFICATION_TONE = {
  'high-conviction candidate': 'high',
  'quality company, wait': 'watch',
  'tactical-only candidate': 'neutral',
  avoid: 'cool',
}
const CLASSIFICATION_LEGEND = [
  { tone: 'high', label: 'High-conviction candidate' },
  { tone: 'watch', label: 'Quality company, wait' },
  { tone: 'neutral', label: 'Tactical-only candidate' },
  { tone: 'cool', label: 'Avoid' },
]
function median(values) {
  const sorted = [...values].sort((left, right) => left - right)
  const mid = Math.floor(sorted.length / 2)
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2
}

export function ScreenNavigation() {
  return <nav className="screen-nav" aria-label="Research screens">{SCREEN_NAV.map(([to, label]) =>
    <NavLink key={to} to={to} className={({ isActive }) => isActive ? 'active' : ''}>{label}</NavLink>)}</nav>
}

// Rendered by every page under /screens/options so the strategies read as one tab with
// sub-tabs rather than eight peers competing for space in the top-level row.
export function OptionsNavigation() {
  return <nav className="screen-nav screen-subnav" aria-label="Options strategies">{OPTIONS_NAV.map((item) =>
    <NavLink key={item.to} to={item.to} end={item.end}
      className={({ isActive }) => isActive ? 'active' : ''}>{item.label}</NavLink>)}</nav>
}

export default function ResearchScreen({ file, eyebrow, title, description }) {
  const { data, loading, error } = useData(file)
  const { preferences } = usePreferences()
  const [filters, setFilters] = useState({ sector: 'all', cap: 'all', confidence: 0, liquidity: 0,
    structural: 0, tactical: 0, membership: 'all' })
  // Some published screens have carried the same ticker twice at adjacent ranks with
  // different percentiles (e.g. momentum.json: DINO at both #11/92.31 and #12/93.16) — a
  // pipeline dedup gap, not a display choice. `getKey` below is ticker-only, so an
  // undeduped pair collides and React warns about duplicate keys. Keep whichever copy is
  // ranked first; results already arrive rank-ordered.
  const seenTickers = new Set()
  const sourceRows = (data?.results || []).filter((row) => {
    if (seenTickers.has(row.ticker)) return false
    seenTickers.add(row.ticker)
    return true
  })
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
      {data?.coverage_note ? <p className="disclaimer" role="note">{data.coverage_note}</p> : null}
      {!rows.length ? <Empty note={data?.status === 'unavailable' ? `Unavailable: ${data.reason_code}` : 'No results match these filters.'} /> : <>
      {rows.some((row) => row.structural_score != null && row.tactical_score != null) && (
        <ScatterChart
          points={rows
            .filter((row) => row.structural_score != null && row.tactical_score != null)
            .map((row) => ({
              id: row.ticker, label: row.ticker, x: row.structural_score, y: row.tactical_score,
              tone: CLASSIFICATION_TONE[row.classification],
            }))}
          xLabel="Structural"
          yLabel="Tactical"
          xFormatter={(value) => value.toFixed(0)}
          yFormatter={(value) => value.toFixed(0)}
          quadrant={{
            x: median(rows.filter((row) => row.structural_score != null).map((row) => row.structural_score)),
            y: median(rows.filter((row) => row.tactical_score != null).map((row) => row.tactical_score)),
          }}
          legend={CLASSIFICATION_LEGEND}
          caption="Structural score versus tactical score, one point per name, split at the median of each"
        />
      )}
      <DataTable
        rows={rows}
        getKey={(row) => row.ticker}
        columns={[
          { key: 'rank', label: 'Rank', cell: (row) => `#${row.rank ?? '\u2013'}` },
          { key: 'ticker', label: 'Ticker', cell: (row) => <b>{row.ticker}</b> },
          { key: 'classification', label: 'Classification',
            cell: (row) => row.classification || (row.eligibility ? 'Eligible' : 'Ineligible') },
          { key: 'peer_group', label: 'Peer group', cell: (row) => row.peer_group || '\u2013' },
          { key: 'percentile', label: 'Percentile', numeric: true,
            cell: (row) => <span className="mono">{number(row.percentile)}</span> },
          { key: 'structural_score', label: 'Structural', numeric: true,
            cell: (row) => <span className="mono">{number(row.structural_score)}</span> },
          { key: 'tactical_score', label: 'Tactical', numeric: true,
            cell: (row) => <span className="mono">{number(row.tactical_score)}</span> },
          { key: 'confidence', label: 'Confidence', numeric: true,
            cell: (row) => <span className="mono">{number((row.confidence || 0) * 100)}%</span> },
          { key: 'reason_codes', label: 'Warnings', sortable: false,
            cell: (row) => (row.reason_codes || []).join(', ') || 'None' },
        ]}
        mobile={{
          variant: preferences.mobileResearchView,
          title: (row) => `#${row.rank ?? '\u2013'} \u00b7 ${row.ticker}`,
          subtitle: (row) => row.peer_group || row.sector || 'Unclassified',
          // Rank, ticker and peer group are already the card's title and subtitle,
          // so neither mobile view repeats them as fields.
          fields: preferences.mobileResearchView === 'detailed' ? [
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
          ],
        }}
      /></>}
      <p className="disclaimer">Schema {data?.schema_version || '–'} · model {data?.model_version || '–'} · config {data?.config_version || '–'}. Rankings are hypotheses for prospective validation, not claims of outperformance.</p>
    </>}
  </>
}
