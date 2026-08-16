import { useState } from 'react'
import { useData } from '../lib/useData'
import { Empty, Loading, Move, Tier } from '../components/Bits.jsx'
import { ScreenNavigation } from './ResearchScreen.jsx'
import { rankBreakoutInProgress, rankEmergingGrowth } from '../lib/researchScreens.js'
import CompanyLogo from '../components/CompanyLogo.jsx'
import Sparkline from '../components/Sparkline.jsx'
import Icon from '../components/Icons.jsx'
import StockDetailModal from '../components/StockDetailModal.jsx'
import DataTable from '../components/DataTable.jsx'

function BreakoutCard({ row, index, onOpen }) {
  return <article className="research-mobile-card" key={row.ticker}>
    <div className="research-card-head">
      <span className="rank-badge">#{index + 1}</span>
      <CompanyLogo company={row} size={42} />
      <div><h2>{row.ticker}</h2><p>{row.name}</p></div>
      <span className="mobile-score">{row.score}<small>score</small></span>
    </div>
    <div className="research-card-badges">
      <Tier label={row.stance} />
      <span className="chip screen-chip screen-chip-breakout">Breakout</span>
    </div>
    <dl className="research-card-metrics">
      <div><dt>5-day return</dt><dd><Move pct={row.screen.weekReturn} capsule /></dd></div>
      <div><dt>20-day return</dt><dd><Move pct={row.screen.monthReturn} capsule /></dd></div>
      <div><dt>Acceleration</dt><dd><Move pct={row.screen.acceleration} capsule /></dd></div>
    </dl>
    <Sparkline values={(row.history?.closes || []).slice(-22)} label={`${row.ticker} one-month daily close trend`} height={54} className="research-card-spark" />
    <button className="primary-button compact" onClick={() => onOpen(row)}>Full research <Icon name="arrow" size={17} /></button>
  </article>
}

function EmergingGrowthCard({ row, index, onOpen }) {
  return <article className="research-mobile-card" key={row.ticker}>
    <div className="research-card-head">
      <span className="rank-badge">#{index + 1}</span>
      <CompanyLogo company={row} size={42} />
      <div><h2>{row.ticker}</h2><p>{row.name}</p></div>
      <span className="mobile-score">{row.score}<small>score</small></span>
    </div>
    <div className="research-card-badges">
      <Tier label={row.stance} />
      <span className="chip screen-chip screen-chip-prospective">Unvalidated</span>
    </div>
    <dl className="research-card-metrics">
      <div><dt>Revenue growth</dt><dd><Move pct={row.screen.revenueGrowth != null ? row.screen.revenueGrowth * 100 : null} capsule /></dd></div>
      <div><dt>Relative strength</dt><dd><Move pct={row.screen.relativeStrength} capsule /></dd></div>
      <div><dt>Vol. contracting</dt><dd>{row.screen.volatilityContracting == null ? '–' : row.screen.volatilityContracting ? 'Yes' : 'No'}</dd></div>
    </dl>
    <Sparkline values={(row.history?.closes || []).slice(-22)} label={`${row.ticker} one-month daily close trend`} height={54} className="research-card-spark" />
    <button className="primary-button compact" onClick={() => onOpen(row)}>Full research <Icon name="arrow" size={17} /></button>
  </article>
}

export default function FastGrowthScreen() {
  const { data, loading, error } = useData('report.json')
  const [sector, setSector] = useState('all')
  const [view, setView] = useState('breakout')
  const [selectedStock, setSelectedStock] = useState(null)

  const universe = [...new Map(
    [...(data?.research || []), ...(data?.screen_universe || [])].map((row) => [row.ticker, row]),
  ).values()]
  const breakoutRows = rankBreakoutInProgress(universe, universe.length)
  const emergingRows = rankEmergingGrowth(universe, universe.length)
  const rows = view === 'breakout' ? breakoutRows : emergingRows
  const sectors = [...new Set(rows.map((row) => row.sector).filter(Boolean))].sort()
  const filtered = sector === 'all' ? rows : rows.filter((row) => row.sector === sector)

  return <>
    <ScreenNavigation />
    <div className="page-head">
      <div>
        <span className="eyebrow">{view === 'breakout' ? 'Sharp recent acceleration' : 'Prospective, unvalidated research'}</span>
        <h1 className="page-title">Fast growth <span className="accent">{view === 'breakout' ? 'breakouts' : 'candidates'}</span></h1>
        <p className="page-sub">
          {view === 'breakout'
            ? 'Names whose most recent week moved faster than the pace set over the prior three weeks - a Microsoft, SanDisk, or AMD run already in progress, not a name that has simply drifted higher all month. This screen finds a move already underway, not one that hasn’t happened yet.'
            : 'An attempt at the harder question: names that have not yet made a big visible move but show real, currently-measurable signs (revenue growth, a margin inflection, early relative strength, contracting volatility) that sometimes precede one. Nothing in this codebase has tested whether this combination actually predicts a subsequent move - treat every result here as a research lead, not a track record.'}
        </p>
      </div>
      <div className="result-count"><strong>{filtered.length}</strong><span>results</span></div>
    </div>

    <div className="research-toolbar">
      <label><span className="sr-only">Screen</span><select value={view} onChange={(event) => setView(event.target.value)}>
        <option value="breakout">Breakout in progress</option>
        <option value="emerging">Emerging growth (unvalidated)</option>
      </select></label>
      {sectors.length > 0 && <label><span className="sr-only">Filter by sector</span><select value={sector} onChange={(event) => setSector(event.target.value)}>
        <option value="all">All sectors</option>{sectors.map((item) => <option key={item}>{item}</option>)}
      </select></label>}
    </div>

    {view === 'emerging' && (
      <div className="card prospective-notice" role="note">
        <strong>Prospective and unvalidated.</strong> No backtest, no rank-IC, no track record backs this screen - the
        validation harness (see /screens/validation) has not accumulated enough prospective history to test it. It exists
        so that history can start accumulating, not because it is known to work.
      </div>
    )}

    {loading ? <Loading /> : error ? <div className="card etf-state" role="alert"><strong>Screen snapshot unavailable</strong><span>{error.message}</span></div> : <>
      {!filtered.length ? (
        <Empty note={view === 'breakout'
          ? 'No name is accelerating sharply enough to clear this screen in the latest report.'
          : 'No name clears the emerging-growth measurables in the latest report.'} />
      ) : <>
        <DataTable
          rows={filtered}
          getKey={(row) => row.ticker}
          columns={view === 'breakout' ? [
            { key: 'rank', label: 'Rank', sortable: false, cell: (row, index) => <span className="rank">#{index + 1}</span> },
            { key: 'ticker', label: 'Company', cell: (row) => (
              <div className="table-company company-with-logo"><CompanyLogo company={row} size={34} />
                <div><b>{row.ticker}</b><span>{row.name}</span></div></div>) },
            { key: 'sector', label: 'Sector', cell: (row) => row.sector || '\u2013' },
            { key: 'stance', label: 'Research rating', cell: (row) => <Tier label={row.stance} /> },
            { key: 'weekReturn', label: '5-day return', numeric: true,
              sortValue: (row) => row.screen.weekReturn, cell: (row) => <Move pct={row.screen.weekReturn} /> },
            { key: 'monthReturn', label: '20-day return', numeric: true,
              sortValue: (row) => row.screen.monthReturn, cell: (row) => <Move pct={row.screen.monthReturn} /> },
            { key: 'acceleration', label: 'Acceleration', numeric: true,
              sortValue: (row) => row.screen.acceleration, cell: (row) => <Move pct={row.screen.acceleration} /> },
            { key: 'score', label: 'Score', numeric: true,
              cell: (row) => <span className="mono score-cell">{row.score}</span> },
            { key: 'open', label: <span className="sr-only">Open</span>, sortable: false,
              cell: (row) => <button className="icon-button" onClick={() => setSelectedStock(row)}
                aria-label={`Open ${row.name} research`}><Icon name="chevron" /></button> },
          ] : [
            { key: 'rank', label: 'Rank', sortable: false, cell: (row, index) => <span className="rank">#{index + 1}</span> },
            { key: 'ticker', label: 'Company', cell: (row) => (
              <div className="table-company company-with-logo"><CompanyLogo company={row} size={34} />
                <div><b>{row.ticker}</b><span>{row.name}</span></div></div>) },
            { key: 'sector', label: 'Sector', cell: (row) => row.sector || '\u2013' },
            { key: 'stance', label: 'Research rating', cell: (row) => <Tier label={row.stance} /> },
            { key: 'revenueGrowth', label: 'Revenue growth', numeric: true,
              sortValue: (row) => row.screen.revenueGrowth,
              cell: (row) => <Move pct={row.screen.revenueGrowth != null ? row.screen.revenueGrowth * 100 : null} /> },
            { key: 'relativeStrength', label: 'Relative strength', numeric: true,
              sortValue: (row) => row.screen.relativeStrength, cell: (row) => <Move pct={row.screen.relativeStrength} /> },
            { key: 'volatilityContracting', label: 'Vol. contracting',
              sortValue: (row) => row.screen.volatilityContracting,
              cell: (row) => row.screen.volatilityContracting == null ? '\u2013' : row.screen.volatilityContracting ? 'Yes' : 'No' },
            { key: 'score', label: 'Score', numeric: true,
              cell: (row) => <span className="mono score-cell">{row.score}</span> },
            { key: 'open', label: <span className="sr-only">Open</span>, sortable: false,
              cell: (row) => <button className="icon-button" onClick={() => setSelectedStock(row)}
                aria-label={`Open ${row.name} research`}><Icon name="chevron" /></button> },
          ]}
          mobile={{
            estimateSize: 250,
            renderItem: (row, index) => view === 'breakout'
              ? <BreakoutCard row={row} index={index} onOpen={setSelectedStock} />
              : <EmergingGrowthCard row={row} index={index} onOpen={setSelectedStock} />,
          }}
        />
      </>}
      <p className="disclaimer">
        {view === 'breakout'
          ? 'A breakout screen flags a change in pace, not a guaranteed continuation - a sharp run can just as easily fade or reverse the following week.'
          : 'An emerging-growth screen flags currently-measurable conditions with no proven predictive track record in this system.'}
        {' '}This is a research screen, not a trade instruction; confirm current price, liquidity, news, and your own risk limits before acting.
      </p>
    </>}
    {selectedStock && <StockDetailModal stock={selectedStock} benchmarkHistory={data?.benchmark_history} onClose={() => setSelectedStock(null)} />}
  </>
}
