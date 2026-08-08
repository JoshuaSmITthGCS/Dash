import { useMemo, useState } from 'react'
import { useData } from '../lib/useData'
import { Empty, Loading, Tier } from '../components/Bits.jsx'
import { ScreenNavigation } from './ResearchScreen.jsx'
import { activeThemes, rankThemeExposure } from '../lib/researchScreens.js'
import CompanyLogo from '../components/CompanyLogo.jsx'
import Icon from '../components/Icons.jsx'
import StockDetailModal from '../components/StockDetailModal.jsx'

const SOURCE_LABEL = {
  published_leader: 'Published leader',
  portfolio: 'Your holding',
  sector_peer: 'Sector-connected',
}

function ThemeTable({ rows, onOpen }) {
  return <div className="research-table card"><table>
    <thead><tr>
      <th scope="col">Rank</th><th scope="col">Company</th><th scope="col">Sector</th>
      <th scope="col">Research rating</th><th scope="col" className="num">Exposure</th>
      <th scope="col" className="num">Opportunity</th><th scope="col">Leading signals</th>
      <th scope="col">Eligible</th><th scope="col"><span className="sr-only">Open</span></th>
    </tr></thead>
    <tbody>{rows.map((row, index) => <tr key={row.ticker}>
      <td className="rank">#{index + 1}</td>
      <td><div className="table-company company-with-logo">
        <CompanyLogo company={row} size={34} />
        <div><b>{row.ticker}</b><span>{row.name}{row.candidate_source && <span className="chip"> {SOURCE_LABEL[row.candidate_source] || row.candidate_source}</span>}</span></div>
      </div></td>
      <td>{row.sector || '–'}</td>
      <td>{row.stance ? <Tier label={row.stance} /> : '–'}</td>
      <td className="mono num">{row.theme_exposure_score ?? '–'}</td>
      <td className="mono num">{row.opportunity_score ?? '–'}</td>
      <td>{(row.leading_signals_fired || []).length || '–'}</td>
      <td>{row.eligible ? 'Yes' : 'No'}</td>
      <td><button className="icon-button" onClick={() => onOpen(row)} aria-label={`Open ${row.name} research`}><Icon name="chevron" /></button></td>
    </tr>)}</tbody>
  </table></div>
}

export default function ThemeExposureScreen() {
  const { data, loading, error } = useData('advisor.json')
  const [selectedStock, setSelectedStock] = useState(null)

  // The theme screen's own rows carry only theme-scoring fields (ticker, exposure,
  // opportunity, eligibility) - merge back onto the full research/screen-universe row so
  // company name, sector, stance, and everything StockDetailModal needs is available.
  const byTicker = useMemo(() => {
    const merged = new Map()
    for (const row of [...(data?.research || []), ...(data?.screen_universe || [])]) {
      merged.set(row.ticker, row)
    }
    return merged
  }, [data])

  const themes = activeThemes(data?.theme_screen)

  return <>
    <ScreenNavigation />
    <div className="page-head">
      <div>
        <span className="eyebrow">Structural trend exposure</span>
        <h1 className="page-title">Theme <span className="accent">exposure</span></h1>
        <p className="page-sub">
          Which companies are exposed to a multi-year demand driver, and whether that exposure has
          already been priced in. Price momentum contributes nothing to this ranking by design – a
          name earns a spot from filing evidence and supply-chain ties, not from having already run.
          "Connected, not yet re-rated" surfaces names that are not already a top research score but
          share a sector or peer group with a theme's anchor companies – the kind of name riding the
          same wave as a proven leader before the market has fully connected the dots.
        </p>
      </div>
    </div>

    {loading ? <Loading /> : error ? <div className="card etf-state" role="alert"><strong>Theme screen unavailable</strong><span>{error.message}</span></div> : <>
      {!themes.length ? <Empty note={data?.theme_screen?.unavailable_reason || 'No theme produced scored exposures in the latest report.'} /> : themes.map((theme) => {
        const rows = (theme.rows || []).map((row) => ({ ...byTicker.get(row.ticker), ...row }))
        const leaders = rows
          .filter((row) => row.candidate_source !== 'sector_peer')
          .sort((a, b) => (b.theme_exposure_score ?? -1) - (a.theme_exposure_score ?? -1))
        const connectedTheme = { ...theme, rows: rows.filter((row) => row.candidate_source === 'sector_peer') }
        const connected = rankThemeExposure(connectedTheme, connectedTheme.rows.length)

        return <section className="card theme-exposure-panel" key={theme.id}>
          <header>
            <h2>{theme.display_name}</h2>
            <p>{theme.thesis}</p>
          </header>

          <h3>Leaders</h3>
          {!leaders.length
            ? <p className="disclaimer">No published leader or holding cleared this theme's signal minimum yet.</p>
            : <ThemeTable rows={leaders} onOpen={setSelectedStock} />}

          <h3>Connected, not yet re-rated</h3>
          <p className="disclaimer">
            Sector/peer-group neighbours of this theme's anchor companies that are not already a
            published top research score, ranked by exposure × business quality × how cheap the
            stock still is. "Not eligible" means the name already trades in the top valuation decile
            of its sector – real exposure, but a price that already reflects it.
          </p>
          {!connected.length
            ? <p className="disclaimer">No sector-connected candidate cleared this theme's signal minimum in the latest report.</p>
            : <ThemeTable rows={connected} onOpen={setSelectedStock} />}
        </section>
      })}
      <p className="disclaimer">
        A separate screen, never a modifier on the fundamentals research score. Names already in the
        top valuation decile of their sector are flagged rather than promoted – specialized thematic
        products have historically lost about 30% risk-adjusted over five years by doing the opposite
        (Ben-David, Franzoni, Kim &amp; Moussawi, RFS 2023).
      </p>
    </>}
    {selectedStock && <StockDetailModal stock={selectedStock} benchmarkHistory={data?.benchmark_history} onClose={() => setSelectedStock(null)} />}
  </>
}
