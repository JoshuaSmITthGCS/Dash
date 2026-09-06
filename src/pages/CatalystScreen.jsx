import { useMemo, useState } from 'react'
import { useData } from '../lib/useData'
import { Empty, Loading } from '../components/Bits.jsx'
import { ScreenNavigation } from './ResearchScreen.jsx'
import DataTable from '../components/DataTable.jsx'

const money = (value) => value == null ? '–' : `$${Number(value).toFixed(2)}`
const pct = (value, digits = 1) => value == null ? '–' : `${Number(value).toFixed(digits)}%`
const dateLabel = (value) => {
  if (!value) return '–'
  const parsed = new Date(`${value}T00:00:00Z`)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

const REASON_LABELS = {
  MINIMUM_PRICE: 'Below minimum price',
  MINIMUM_MARKET_CAP: 'Below minimum market cap',
  MINIMUM_LIQUIDITY: 'Below minimum dollar volume',
  NO_CONFIRMED_EARNINGS_DATE: 'No earnings date on file',
  OUTSIDE_CATALYST_WINDOW: 'Outside the earnings window',
  EXPECTED_MOVE_UNRESOLVED: 'No prior expiration to isolate the move against, or an illiquid chain',
}

export default function CatalystScreen() {
  const { data, loading, error } = useData('screens/catalyst.json')
  const [sector, setSector] = useState('all')
  const [showIneligible, setShowIneligible] = useState(false)

  const sourceRows = data?.results || []
  const sectors = useMemo(() => [...new Set(sourceRows.map((row) => row.sector).filter(Boolean))].sort(), [sourceRows])
  const rows = sourceRows
    .filter((row) => showIneligible || row.eligibility)
    .filter((row) => sector === 'all' || row.sector === sector)

  return <>
    <ScreenNavigation />
    <div className="page-head">
      <div>
        <span className="eyebrow">Earnings only · next {data?.window?.maximum_days_to_earnings ?? 14} days</span>
        <h1 className="page-title">Earnings <span className="accent">catalyst calendar</span></h1>
        <p className="page-sub">
          US names with a confirmed earnings date inside the window, and an event-isolated expected move
          computed by differencing the option expiration spanning earnings against the one just before it —
          the incremental variance is what the options market is pricing for the print itself, net of ordinary
          day-to-day volatility. Deliberately earnings-only: FDA, litigation, index and contract-award
          catalysts were excluded by the research this screen implements as contested-pricing, illiquid, or
          soft-dated — see the disclaimer below.
        </p>
      </div>
      <div className="result-count"><strong>{rows.length}</strong><span>results</span></div>
    </div>

    <div className="card prospective-notice" role="note">
      <strong>Research screen, not a trade instruction.</strong> The expected move is a sizing/framing number,
      never a claim that options are rich or cheap — the research behind this screen found options on average
      <em> under</em>-price earnings uncertainty, not over-price it. Confirm live quotes, open interest, and
      your own risk limits in your broker before acting on anything here.
    </div>

    <div className="research-toolbar">
      {sectors.length > 0 && <label><span className="sr-only">Filter by sector</span><select value={sector} onChange={(event) => setSector(event.target.value)}>
        <option value="all">All sectors</option>{sectors.map((item) => <option key={item}>{item}</option>)}
      </select></label>}
      <label className="toggle-control">
        <input type="checkbox" checked={showIneligible} onChange={(event) => setShowIneligible(event.target.checked)} />
        <span>Show ineligible rows</span>
      </label>
    </div>

    {loading ? <Loading /> : error ? <div className="card etf-state" role="alert"><strong>Screen snapshot unavailable</strong><span>{error.message}</span></div> : <>
      {data?.status === 'unavailable' ? (
        <Empty note={data.reason_code === 'YFINANCE_UNAVAILABLE'
          ? 'Options-chain data is unavailable in this snapshot.'
          : 'No ticker currently has a confirmed earnings date inside the catalyst window. Check back after the next data refresh.'} />
      ) : !rows.length ? (
        <Empty note="No candidate matches the current filters." />
      ) : (
        <DataTable
          rows={rows}
          getKey={(row) => row.ticker}
          columns={[
            { key: 'ticker', label: 'Ticker', cell: (row) => <b>{row.ticker}</b> },
            { key: 'sector', label: 'Sector', cell: (row) => row.sector || '–' },
            { key: 'earnings_date', label: 'Earnings', cell: (row) => dateLabel(row.earnings_date) },
            { key: 'days_to_earnings', label: 'Days out', numeric: true, cell: (row) => <span className="mono">{row.days_to_earnings}</span> },
            { key: 'price', label: 'Price', numeric: true, cell: (row) => <span className="mono">{money(row.price)}</span> },
            { key: 'expected_move_pct', label: 'Expected move', numeric: true,
              cell: (row) => <span className="mono">{row.expected_move_pct != null ? pct(row.expected_move_pct) : '–'}</span> },
            { key: 'straddle_move_pct', label: 'Straddle move (context)', numeric: true,
              cell: (row) => <span className="mono">{pct(row.straddle_move_pct)}</span> },
            { key: 'post_expiration', label: 'Bracketing expiration', cell: (row) => dateLabel(row.post_expiration) },
            { key: 'eligibility', label: 'Status', sortable: false, cell: (row) => row.eligibility
              ? <span className="chip">Eligible</span>
              : <span className="chip" title={(row.reason_codes || []).map((code) => REASON_LABELS[code] || code).join('; ')}>
                  {(row.reason_codes || []).map((code) => REASON_LABELS[code] || code)[0] || 'Ineligible'}
                </span> },
          ]}
          mobile={{
            titleColumn: 'ticker',
            title: (row) => row.ticker,
            subtitle: (row) => `${dateLabel(row.earnings_date)} · ${row.expected_move_pct != null ? pct(row.expected_move_pct) : 'move unresolved'}`,
          }}
        />
      )}
      <p className="disclaimer">
        Schema {data?.schema_version || '–'} · model {data?.model_version || '–'} · config {data?.config_version || '–'}.
        Yahoo's earnings calendar carries no confirmed-vs-estimated flag the way institutional providers do —
        treat every date here as the best available, not as confirmed. Implied volatility, spreads, and open
        interest are snapshots from the last pipeline run and move throughout the trading day.
      </p>
    </>}
  </>
}
