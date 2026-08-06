import { useState } from 'react'
import { useData } from '../lib/useData'
import { Empty, Loading, Move, Tier } from '../components/Bits.jsx'
import { ScreenNavigation } from './ResearchScreen.jsx'
import { rankFastGrowth } from '../lib/researchScreens.js'
import CompanyLogo from '../components/CompanyLogo.jsx'
import Sparkline from '../components/Sparkline.jsx'
import Icon from '../components/Icons.jsx'
import StockDetailModal from '../components/StockDetailModal.jsx'
import MobileVirtualList from '../components/MobileVirtualList.jsx'

export default function FastGrowthScreen() {
  const { data, loading, error } = useData('report.json')
  const [sector, setSector] = useState('all')
  const [selectedStock, setSelectedStock] = useState(null)

  const universe = [...new Map(
    [...(data?.research || []), ...(data?.screen_universe || [])].map((row) => [row.ticker, row]),
  ).values()]
  const rows = rankFastGrowth(universe, universe.length)
  const sectors = [...new Set(rows.map((row) => row.sector).filter(Boolean))].sort()
  const filtered = sector === 'all' ? rows : rows.filter((row) => row.sector === sector)

  return <>
    <ScreenNavigation />
    <div className="page-head">
      <div>
        <span className="eyebrow">Sharp recent acceleration</span>
        <h1 className="page-title">Fast growth <span className="accent">breakouts</span></h1>
        <p className="page-sub">
          Names whose most recent week moved faster than the pace set over the prior three weeks - the setup behind a
          Microsoft, SanDisk, or AMD run right before it takes off, not a name that has simply drifted higher all month.
        </p>
      </div>
      <div className="result-count"><strong>{filtered.length}</strong><span>results</span></div>
    </div>

    {loading ? <Loading /> : error ? <div className="card etf-state" role="alert"><strong>Screen snapshot unavailable</strong><span>{error.message}</span></div> : <>
      {sectors.length > 0 && <div className="research-toolbar">
        <label><span className="sr-only">Filter by sector</span><select value={sector} onChange={(event) => setSector(event.target.value)}>
          <option value="all">All sectors</option>{sectors.map((item) => <option key={item}>{item}</option>)}
        </select></label>
      </div>}

      {!filtered.length ? <Empty note="No name is accelerating sharply enough to clear this screen in the latest report." /> : <>
        <MobileVirtualList className="research-mobile-list" items={filtered} getKey={(row) => row.ticker} estimateSize={250}
          renderItem={(row, index) => <article className="research-mobile-card" key={row.ticker}>
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
            <button className="primary-button compact" onClick={() => setSelectedStock(row)}>Full research <Icon name="arrow" size={17} /></button>
          </article>} />

        <div className="research-table card">
          <table>
            <thead><tr>
              <th scope="col">Rank</th><th scope="col">Company</th><th scope="col">Sector</th><th scope="col">Research rating</th>
              <th scope="col" className="num">5-day return</th><th scope="col" className="num">20-day return</th>
              <th scope="col" className="num">Acceleration</th><th scope="col" className="num">Score</th><th scope="col"><span className="sr-only">Open</span></th>
            </tr></thead>
            <tbody>{filtered.map((row, index) => <tr key={row.ticker}>
              <td className="rank">#{index + 1}</td>
              <td><div className="table-company company-with-logo"><CompanyLogo company={row} size={34} /><div><b>{row.ticker}</b><span>{row.name}</span></div></div></td>
              <td>{row.sector || '–'}</td>
              <td><Tier label={row.stance} /></td>
              <td className="num"><Move pct={row.screen.weekReturn} /></td>
              <td className="num"><Move pct={row.screen.monthReturn} /></td>
              <td className="num"><Move pct={row.screen.acceleration} /></td>
              <td className="mono num score-cell">{row.score}</td>
              <td><button className="icon-button" onClick={() => setSelectedStock(row)} aria-label={`Open ${row.name} research`}><Icon name="chevron" /></button></td>
            </tr>)}</tbody>
          </table>
        </div>
      </>}
      <p className="disclaimer">
        A breakout screen flags a change in pace, not a guaranteed continuation - a sharp run can just as easily fade or
        reverse the following week. This is a research screen, not a trade instruction; confirm current price, liquidity,
        news, and your own risk limits before acting.
      </p>
    </>}
    {selectedStock && <StockDetailModal stock={selectedStock} benchmarkHistory={data?.benchmark_history} onClose={() => setSelectedStock(null)} />}
  </>
}
