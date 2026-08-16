import { useMemo, useState } from 'react'
import { useData } from '../lib/useData'
import { Empty, Loading, Tier } from '../components/Bits.jsx'
import { ScreenNavigation } from './ResearchScreen.jsx'
import { activeThemes, rankThemeExposure } from '../lib/researchScreens.js'
import CompanyLogo from '../components/CompanyLogo.jsx'
import Icon from '../components/Icons.jsx'
import StockDetailModal from '../components/StockDetailModal.jsx'
import InfoTag from '../components/InfoTag.jsx'
import DataTable from '../components/DataTable.jsx'

const SOURCE_LABEL = {
  published_leader: 'Published leader',
  portfolio: 'Your holding',
  sector_peer: 'Sector-connected',
}

// `.research-table` is hidden outright below 900px (see global.css) in favor of this card
// list - without it, this screen would render nothing at all on a phone.
function ThemeCard({ row, index, onOpen }) {
  return <article className="research-mobile-card" key={row.ticker}>
    <div className="research-card-head">
      <span className="rank-badge">#{index + 1}</span>
      <CompanyLogo company={row} size={42} />
      <div><h2>{row.ticker}</h2><p>{row.name}</p></div>
      <span className="mobile-score">{row.opportunity_score ?? '–'}<small>opportunity</small></span>
    </div>
    <div className="research-card-badges">
      {row.stance && <Tier label={row.stance} />}
      {row.candidate_source && <span className="chip">{SOURCE_LABEL[row.candidate_source] || row.candidate_source}</span>}
      {!row.eligible && <span className="chip">Not eligible</span>}
    </div>
    <dl className="research-card-metrics">
      <div><dt>Exposure</dt><dd>{row.theme_exposure_score ?? '–'}</dd></div>
      <div><dt>Sector</dt><dd>{row.sector || '–'}</dd></div>
      <div><dt>Leading signals</dt><dd>{(row.leading_signals_fired || []).length || '–'}</dd></div>
    </dl>
    <button className="primary-button compact" onClick={() => onOpen(row)}>Full research <Icon name="arrow" size={17} /></button>
  </article>
}

function ThemeTable({ rows, onOpen }) {
  return <DataTable
    rows={rows}
    getKey={(row) => row.ticker}
    columns={[
      { key: 'rank', label: 'Rank', sortable: false, cell: (row, index) => <span className="rank">#{index + 1}</span> },
      { key: 'ticker', label: 'Company', cell: (row) => (
        <div className="table-company company-with-logo">
          <CompanyLogo company={row} size={34} />
          <div><b>{row.ticker}</b><span>{row.name}{row.candidate_source && <span className="chip"> {SOURCE_LABEL[row.candidate_source] || row.candidate_source}</span>}</span></div>
        </div>) },
      { key: 'sector', label: 'Sector', cell: (row) => row.sector || '\u2013' },
      { key: 'stance', label: 'Research rating', cell: (row) => row.stance ? <Tier label={row.stance} /> : '\u2013' },
      { key: 'theme_exposure_score', label: 'Exposure', numeric: true,
        cell: (row) => <span className="mono">{row.theme_exposure_score ?? '\u2013'}</span> },
      { key: 'opportunity_score', label: 'Opportunity', numeric: true,
        cell: (row) => <span className="mono">{row.opportunity_score ?? '\u2013'}</span> },
      { key: 'leading_signals_fired', label: 'Leading signals',
        sortValue: (row) => (row.leading_signals_fired || []).length,
        cell: (row) => (row.leading_signals_fired || []).length || '\u2013' },
      { key: 'eligible', label: 'Eligible', cell: (row) => row.eligible ? 'Yes' : 'No' },
      { key: 'open', label: <span className="sr-only">Open</span>, sortable: false,
        cell: (row) => <button className="icon-button" onClick={() => onOpen(row)}
          aria-label={`Open ${row.name} research`}><Icon name="chevron" /></button> },
    ]}
    mobile={{ estimateSize: 250, renderItem: (row, index) => <ThemeCard row={row} index={index} onOpen={onOpen} /> }}
  />
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
            <h2>{theme.display_name}
              <InfoTag label="What the columns mean">
                <strong>Exposure</strong>
                <p>0–100. How exposed this company is to the theme, from filing evidence (segment
                  revenue, rising keyword density in its own 10-K language, supply-chain ties to
                  confirmed spenders) - never from price action.</p>
                <strong>Opportunity</strong>
                <p>Exposure × business quality × how cheap the stock still is - a name combining real
                  exposure with a business that holds up and a price that has not already run, not just
                  the purest-play, most expensive name in the theme.</p>
                <strong>Leading signals</strong>
                <p>How many "leading" signals fired - evidence of what a company is building, as opposed
                  to lagging evidence like historical segment revenue. At least one is required to be
                  eligible.</p>
                <strong>Eligible</strong>
                <p>"No" means the name already trades in the top valuation decile of its sector, or no
                  leading signal confirmed the exposure - real exposure, flagged rather than promoted.</p>
              </InfoTag>
            </h2>
            <p>{theme.thesis}</p>
          </header>

          <h3>Leaders
            <InfoTag label="Leaders">
              <strong>Leaders</strong>
              <p>Names already a published top research score or one of your holdings, that also
                cleared this theme's signal minimum. These are the recognized, already-priced-in
                exposure to the trend.</p>
            </InfoTag>
          </h3>
          {!leaders.length
            ? <p className="disclaimer">No published leader or holding cleared this theme's signal minimum yet.</p>
            : <ThemeTable rows={leaders} onOpen={setSelectedStock} />}

          <h3>Connected, not yet re-rated
            <InfoTag label="Connected, not yet re-rated">
              <strong>Connected, not yet re-rated</strong>
              <p>Sector/peer-group neighbours of this theme's anchor companies that are not already a
                published top research score - the kind of name riding the same wave as a proven leader
                before the market has fully connected the dots. This is a sector/peer-group heuristic,
                not the more rigorous product-space (10-K similarity) peer matching this feature aims
                for eventually - a peer-group match only makes a name a candidate, the exposure and
                eligibility columns still come from real filing evidence.</p>
            </InfoTag>
          </h3>
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
