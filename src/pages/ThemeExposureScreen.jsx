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
import DotPlot from '../components/DotPlot.jsx'

const signalTitle = (name = '') => name.replace(/_/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())
// Theme sector scope is published lowercased, since it is matched case-insensitively.
const titleCase = (value = '') => value.replace(/\b\w/g, (letter) => letter.toUpperCase())

// Average resolved score per declared signal, across whichever rows the caller
// considers eligible for the read (leaders, here) — never across every candidate,
// which would let unscreened sector-peer noise drag the average around. A signal
// only enters the result once at least one row actually resolved it.
function signalScoreRows(rows) {
  const totals = new Map()
  rows.forEach((row) => {
    (row.signals || []).forEach((signal) => {
      if (signal.score == null) return
      const entry = totals.get(signal.name) || { sum: 0, count: 0, leading: signal.leading }
      entry.sum += signal.score
      entry.count += 1
      totals.set(signal.name, entry)
    })
  })
  return [...totals.entries()].map(([name, { sum, count, leading }]) => ({
    id: name,
    label: `${signalTitle(name)}${leading ? ' · leading' : ''}`,
    value: sum / count,
  }))
}

const SOURCE_LABEL = {
  published_leader: 'Published leader',
  portfolio: 'Your holding',
  sector_peer: 'Sector-connected',
}

// Minimum themes a name must clear the guardrails on before it reads as a crossing point
// rather than a coincidence of two keyword lists overlapping.
const MULTI_THEME_MINIMUM = 2
const MULTI_THEME_LIMIT = 15

// Which structural trends each company clears the guardrails on, across every theme it was
// scored against - not only the ones whose published rows it made. A grid contractor that is
// also a reshoring beneficiary and an AI-buildout supplier is exposed to one buildout counted
// three ways, which is concentration wearing the costume of diversification; the same crossing
// is also the most direct thing this screen can say about where a trend actually converges.
// Built from `by_ticker`, the pipeline's full index, so it is not limited to published rows.
export function crossThemeNames(byTicker = {}, { minimum = MULTI_THEME_MINIMUM, limit = MULTI_THEME_LIMIT } = {}) {
  return Object.entries(byTicker)
    .map(([ticker, entries]) => {
      const eligible = (entries || []).filter((entry) => entry.eligible)
      const scores = eligible.map((entry) => entry.opportunity_score).filter((value) => Number.isFinite(value))
      const confidences = eligible.map((entry) => entry.confidence).filter((value) => Number.isFinite(value))
      return {
        ticker,
        themes: eligible,
        themeCount: eligible.length,
        bestOpportunity: scores.length ? Math.max(...scores) : null,
        // The weakest theme in the crossing, not the average: a crossing is only as good as
        // the thinnest evidence holding one of its legs up.
        weakestConfidence: confidences.length ? Math.min(...confidences) : null,
      }
    })
    .filter((row) => row.themeCount >= minimum)
    .sort((left, right) => (right.themeCount - left.themeCount)
      || ((right.bestOpportunity ?? -1) - (left.bestOpportunity ?? -1)))
    .slice(0, limit)
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
      <div><dt>Industry</dt><dd>{row.industry || row.sector || '–'}</dd></div>
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
      // Industry, not just sector: the whole question a reader has about a theme row is
      // whether the company actually builds any of it, and "Industrials" cannot answer that
      // for a chip-equipment maker and a trucking company alike. It is also the field the
      // theme's own scope is matched on, so this is the screen showing its working.
      { key: 'industry', label: 'Industry',
        sortValue: (row) => row.industry || row.sector || '',
        cell: (row) => <span className="table-industry"><b>{row.industry || row.sector || '\u2013'}</b>
          {row.industry && row.sector && <span>{row.sector}</span>}</span> },
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

function CrossThemeCard({ row, index, onOpen }) {
  return <article className="research-mobile-card" key={row.ticker}>
    <div className="research-card-head">
      <span className="rank-badge">#{index + 1}</span>
      <CompanyLogo company={row} size={42} />
      <div><h2>{row.ticker}</h2><p>{row.name}</p></div>
      <span className="mobile-score">{row.themeCount}<small>themes</small></span>
    </div>
    <div className="research-card-badges">
      {row.themes.map((theme) => <span className="chip" key={theme.theme_id}>{theme.display_name || theme.theme_id}</span>)}
    </div>
    <dl className="research-card-metrics">
      <div><dt>Best opportunity</dt><dd>{row.bestOpportunity ?? '–'}</dd></div>
      <div><dt>Weakest evidence</dt><dd>{row.weakestConfidence == null ? '–' : `${Math.round(row.weakestConfidence * 100)}%`}</dd></div>
      <div><dt>Industry</dt><dd>{row.industry || row.sector || '–'}</dd></div>
    </dl>
    <button className="primary-button compact" onClick={() => onOpen(row)}>Full research <Icon name="arrow" size={17} /></button>
  </article>
}

function CrossThemeTable({ rows, onOpen }) {
  return <DataTable
    rows={rows}
    getKey={(row) => row.ticker}
    columns={[
      { key: 'rank', label: 'Rank', sortable: false, cell: (row, index) => <span className="rank">#{index + 1}</span> },
      { key: 'ticker', label: 'Company', cell: (row) => (
        <div className="table-company company-with-logo">
          <CompanyLogo company={row} size={34} />
          <div><b>{row.ticker}</b><span>{row.name}</span></div>
        </div>) },
      { key: 'industry', label: 'Industry',
        sortValue: (row) => row.industry || row.sector || '',
        cell: (row) => <span className="table-industry"><b>{row.industry || row.sector || '–'}</b>
          {row.industry && row.sector && <span>{row.sector}</span>}</span> },
      { key: 'themeCount', label: 'Themes', numeric: true, cell: (row) => <span className="mono">{row.themeCount}</span> },
      { key: 'themes', label: 'Where it crosses', sortable: false,
        cell: (row) => <span className="table-chip-list">{row.themes.map((theme) => (
          <span className="chip" key={theme.theme_id}>{theme.display_name || theme.theme_id} {theme.theme_exposure_score ?? '–'}</span>
        ))}</span> },
      { key: 'bestOpportunity', label: 'Best opportunity', numeric: true,
        cell: (row) => <span className="mono">{row.bestOpportunity ?? '–'}</span> },
      { key: 'weakestConfidence', label: 'Weakest evidence', numeric: true,
        cell: (row) => <span className="mono">{row.weakestConfidence == null ? '–' : `${Math.round(row.weakestConfidence * 100)}%`}</span> },
      { key: 'open', label: <span className="sr-only">Open</span>, sortable: false,
        cell: (row) => <button className="icon-button" onClick={() => onOpen(row)}
          aria-label={`Open ${row.name} research`}><Icon name="chevron" /></button> },
    ]}
    mobile={{ estimateSize: 250, renderItem: (row, index) => <CrossThemeCard row={row} index={index} onOpen={onOpen} /> }}
  />
}

// "Showing 20 of 83" rather than a bare table: with per-group publishing caps, a reader who
// cannot see how much was scored has no way to tell a thin theme from a truncated one.
function GroupCount({ shown, total }) {
  if (!total || total <= shown) return null
  return <span className="chip">Showing {shown} of {total}</span>
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
  const crossTheme = useMemo(
    () => crossThemeNames(data?.theme_screen?.by_ticker || {})
      .map((row) => ({ ...byTicker.get(row.ticker), ...row })),
    [data, byTicker],
  )

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
      {!themes.length ? <Empty note={data?.theme_screen?.unavailable_reason || 'No theme produced scored exposures in the latest report.'} /> : <>
      <nav className="card theme-index" aria-label="Themes in this report">
        <h2>Structural trends in this report</h2>
        <ul>
          {themes.map((theme) => (
            <li key={theme.id}>
              <a href={`#theme-${theme.id}`}>{theme.display_name}</a>
              <small>{theme.eligible_count ?? theme.rows.length} names cleared the guardrails
                {theme.count ? ` of ${theme.count} scored` : ''}</small>
            </li>
          ))}
        </ul>
      </nav>

      {crossTheme.length > 0 && <section className="card theme-exposure-panel" aria-labelledby="cross-theme-heading">
        <header>
          <h2 id="cross-theme-heading">Where the themes cross
            <InfoTag label="Where the themes cross">
              <strong>Where the themes cross</strong>
              <p>Companies that clear the guardrails on more than one structural trend at once.
                Read it both ways: a name sitting in three themes is the most direct expression of
                where those trends converge, and it is also a single position carrying three
                correlated bets, which is concentration that looks like diversification on a
                sector breakdown.</p>
              <p>Counted across every theme a company was scored against, not only the themes
                whose published rows it made.</p>
              <strong>Weakest evidence</strong>
              <p>The lowest share of declared signal weight that resolved among the themes this
                name clears - a crossing is only as strong as its thinnest leg. Most rows sit well
                below 100% today: with no curated segment or named-customer data and no transcript
                source, the filing-keyword trend and the spenders' capex are the only signals that
                resolve broadly, so a crossing is a lead to check rather than a confirmed
                convergence.</p>
            </InfoTag>
          </h2>
          <p>Ranked by how many themes a company clears, then by its best opportunity score in any
            of them.</p>
        </header>
        <CrossThemeTable rows={crossTheme} onOpen={setSelectedStock} />
      </section>}

      {themes.map((theme) => {
        const rows = (theme.rows || []).map((row) => ({ ...byTicker.get(row.ticker), ...row }))
        const leaderTheme = { ...theme, rows: rows.filter((row) => row.candidate_source !== 'sector_peer') }
        // Ranked the same way the connected group is - eligible first, then opportunity, then
        // exposure. Ordering leaders by raw exposure alone left the top of the table decided by
        // ties, since a saturated signal puts many names at exactly 100.
        const leaders = rankThemeExposure(leaderTheme, leaderTheme.rows.length)
        const connectedTheme = { ...theme, rows: rows.filter((row) => row.candidate_source === 'sector_peer') }
        const connected = rankThemeExposure(connectedTheme, connectedTheme.rows.length)

        return <section className="card theme-exposure-panel" id={`theme-${theme.id}`} key={theme.id}>
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
                <p>How many of this company's own leading signals fired - evidence of what it is
                  building, as opposed to lagging evidence like historical segment revenue. Counted
                  company by company: a theme-level reading such as the spenders' capex growth is
                  identical for every candidate, so it describes the demand driver and never counts
                  as confirmation that a particular company is exposed. At least one company-specific
                  leading signal is required to be eligible.</p>
                <strong>Eligible</strong>
                <p>"No" means the name already trades in the top valuation decile of its sector, or no
                  company-specific leading signal confirmed the exposure - real exposure, flagged
                  rather than promoted.</p>
              </InfoTag>
            </h2>
            <p>{theme.thesis}</p>
            <div className="research-card-badges">
              <span className="chip">{theme.count ?? theme.rows.length} scored</span>
              <span className="chip">{theme.eligible_count ?? 0} cleared the guardrails</span>
            </div>
            {(theme.industries || theme.sectors || []).length > 0 && (
              <p className="disclaimer theme-scope">
                <b>Built by:</b> {(theme.industries?.length ? theme.industries : theme.sectors).map(titleCase).join(' · ')}
                <InfoTag label="Built by">
                  <strong>Built by</strong>
                  <p>The industries this theme's supply chain can sit in. A company outside them
                    is never scored against the theme and never costs a filing read, however
                    much its own filings talk about the trend - which is what stopped banks and
                    insurers ranking as top exposure to an accelerator buildout, and what keeps
                    a trucking company out of a theme it happens to share a sector with.</p>
                  <p>Membership makes a name a candidate, nothing more. Exposure and
                    eligibility still come from its own filing evidence.</p>
                </InfoTag>
              </p>
            )}
          </header>

          <h3>Leaders <GroupCount shown={leaders.length} total={theme.group_counts?.leaders} />
            <InfoTag label="Leaders">
              <strong>Leaders</strong>
              <p>Names already a published top research score or one of your holdings, that also
                cleared this theme's signal minimum. These are the recognized, already-priced-in
                exposure to the trend.</p>
            </InfoTag>
          </h3>
          {!leaders.length
            ? <p className="disclaimer">No published leader or holding cleared this theme's signal minimum yet.</p>
            : <>
              <ThemeTable rows={leaders} onOpen={setSelectedStock} />
              {signalScoreRows(leaders).length > 1 && (
                <DotPlot
                  rows={signalScoreRows(leaders)}
                  xLabel="Mean signal score among leaders (0-100)"
                  xFormatter={(value) => value.toFixed(0)}
                  domain={{ min: 0, max: 100 }}
                  caption={`${theme.display_name}: mean resolved score per signal, across this theme's leaders`}
                />
              )}
            </>}

          <h3>Connected, not yet re-rated <GroupCount shown={connected.length} total={theme.group_counts?.connected} />
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
      </>}
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
