import { useMemo, useState } from 'react'
import { useData } from '../lib/useData'
import { Empty, Loading, Move, RefreshProgress } from '../components/Bits'
import Icon from '../components/Icons.jsx'
import { useScreenRefresh } from '../lib/useScreenRefresh'
import { ScreenNavigation } from './ResearchScreen'
import DataTable from '../components/DataTable.jsx'
import { ResponsiveControlPanel } from '../components/MobileSheet.jsx'

const FLAG_LABELS = {
  LATE_FILING: 'Late filing',
  OPTIONS_TRADE: 'Options trade',
  RARE_TRADER: 'Rare trader',
  CONCENTRATED_SIZE: 'Concentrated size',
  CLUSTER_TRADE: 'Cluster trade',
  SAME_SECTOR_REPEAT: 'Same-sector repeat',
  BUY_SELL_FLIP: 'Buy/sell flip',
  NOVEL_TICKER: 'Novel ticker',
}

const money = (value, digits = 0) =>
  value == null ? '–' : `$${Number(value).toLocaleString('en-US', { maximumFractionDigits: digits })}`

const compactMoney = (value) => {
  if (value == null) return '–'
  if (value >= 1e9) return `$${(value / 1e9).toFixed(3)}B`
  if (value >= 1e6) return `$${(value / 1e6).toFixed(1)}M`
  return money(value)
}

// An empty screen has more than one cause, and "nothing was disclosed this week" is the only
// one that needs no attention. Saying that when the disclosure feed actually refused every
// request would hide a broken collector behind a reassuring sentence.
export function emptyNote(data) {
  const failures = data?.collection?.failures || []
  if (data?.reason_code === 'CONGRESS_DISCLOSURE_FEED_UNAVAILABLE') {
    return `Disclosure feed unavailable, so nothing could be collected this run${failures.length ? ` (${failures[0]})` : ''}.`
  }
  if (data?.reason_code === 'NO_DISCLOSURES_IN_PUBLISH_WINDOW') {
    return `No disclosures filed in the trailing ${data.publish_window_days || 120} days.`
  }
  return 'No disclosures collected yet – this screen updates weekly.'
}

function FlagChips({ flags }) {
  if (!flags?.length) return <span className="mono text-faint">–</span>
  return <div className="congress-flag-row">
    {flags.map((flag) => <span key={flag} className="chip">{FLAG_LABELS[flag] || flag}</span>)}
  </div>
}

export default function CongressTrades() {
  const { data, loading, error, reload } = useData('screens/congress-trades.json')
  const refresh = useScreenRefresh('congress', reload)
  const [filters, setFilters] = useState({ chamber: 'all', flag: 'all', sort: 'disclosed' })
  const rows = data?.results || []
  const summary = data?.summary

  const filtered = useMemo(() => {
    let next = rows.filter((row) => filters.chamber === 'all' || row.chamber === filters.chamber)
    if (filters.flag !== 'all') next = next.filter((row) => (row.flags || []).includes(filters.flag))
    const sorted = [...next]
    if (filters.sort === 'amount') {
      sorted.sort((left, right) => (right.amount_upper || 0) - (left.amount_upper || 0))
    } else if (filters.sort === 'performance') {
      sorted.sort((left, right) => (right.return_since_purchase_pct ?? -Infinity) - (left.return_since_purchase_pct ?? -Infinity))
    } else {
      sorted.sort((left, right) => (right.disclosure_date || '').localeCompare(left.disclosure_date || ''))
    }
    return sorted
  }, [rows, filters])

  const update = (key) => (event) => setFilters((current) => ({ ...current, [key]: event.target.value }))

  return <>
    <ScreenNavigation />
    <div className="page-head">
      <div>
        <span className="eyebrow">STOCK Act disclosures</span>
        <h1 className="page-title">Politics <span className="accent">trade alert</span></h1>
        <p className="page-sub">
          Senate and House trade disclosures, collected weekly from Financial Modeling Prep and the public
          House/Senate disclosure datasets – both mirrors of the same Clerk and eFD filings. Flags are computed
          directly from the disclosure data – a late filing, an options trade, an unusually large or clustered
          position, a repeat pattern – not a claim that any trade was improper. Where a plain stock purchase has
          enough price history, "since purchase" shows how the stock has actually performed – a price fact, not a
          claim about why it moved or a recommendation to trade.
        </p>
      </div>
      {refresh.available && (
        <div className="page-actions">
          {/* This screen is on a weekly cron and the main research refresh does not
              collect it, so without this the only way to re-run it is to wait. */}
          <button className="secondary-button" onClick={refresh.requestRefresh} disabled={refresh.refreshing}
            title="Re-run the disclosure collection now – it reads every configured source and takes a few minutes">
            <Icon name="sync" size={17} className={refresh.refreshing ? 'refresh-spin' : ''} />
            {refresh.refreshing ? 'Collecting…' : 'Re-run collection'}
          </button>
        </div>
      )}
    </div>

    <RefreshProgress active={refresh.refreshing} elapsedLabel={refresh.elapsedLabel}
      percent={refresh.progress} stage={refresh.stage} />
    {refresh.message && (
      <div className={`card etf-state${refresh.status === 'error' ? '' : ' subtle'}`}
        role={refresh.status === 'error' ? 'alert' : 'status'}>
        <span>{refresh.message}</span>
      </div>
    )}

    {loading ? <Loading /> : error ? (
      <div className="card etf-state" role="alert"><strong>Congress trades screen unavailable</strong><span>{error.message}</span></div>
    ) : <>
      {data && data.status === 'partial' && (
        // Rows are real but incomplete: at least one source answered and at least one did
        // not, so what follows understates the week rather than describing it.
        <div className="card etf-state" role="alert">
          <strong>Collected from some sources only</strong>
          <span>{`Some disclosures below may be missing – ${(data.collection?.failures || []).join('; ')}`}</span>
        </div>
      )}

      {summary && (
        <div className="grid congress-kpi-grid">
          <div className="card kpi">
            <div className="kpi-label">Trades</div>
            <div className="kpi-value">{summary.trades.toLocaleString('en-US')}</div>
          </div>
          <div className="card kpi">
            <div className="kpi-label">Filings</div>
            <div className="kpi-value">{summary.filings_estimated.toLocaleString('en-US')}</div>
            <div className="kpi-note">estimated</div>
          </div>
          <div className="card kpi">
            <div className="kpi-label">Volume</div>
            <div className="kpi-value">{compactMoney(summary.volume_upper)}</div>
            <div className="kpi-note">range ceiling</div>
          </div>
          <div className="card kpi">
            <div className="kpi-label">Politicians</div>
            <div className="kpi-value">{summary.politicians.toLocaleString('en-US')}</div>
          </div>
          <div className="card kpi">
            <div className="kpi-label">Issuers</div>
            <div className="kpi-value">{summary.issuers.toLocaleString('en-US')}</div>
          </div>
        </div>
      )}

      <ResponsiveControlPanel label="Filter and sort" title="Filter disclosures"><div className="screen-filters" aria-label="Disclosure filters">
        <label>Chamber
          <select value={filters.chamber} onChange={update('chamber')}>
            <option value="all">All</option>
            <option value="senate">Senate</option>
            <option value="house">House</option>
          </select>
        </label>
        <label>Flag
          <select value={filters.flag} onChange={update('flag')}>
            <option value="all">All</option>
            {Object.entries(FLAG_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>
        <label>Sort by
          <select value={filters.sort} onChange={update('sort')}>
            <option value="disclosed">Most recently disclosed</option>
            <option value="amount">Largest reported amount</option>
            <option value="performance">Best performance since purchase</option>
          </select>
        </label>
      </div></ResponsiveControlPanel>

      {!filtered.length ? (
        <Empty note={rows.length ? 'No disclosures match these filters.' : emptyNote(data)} />
      ) : (
        <DataTable
          rows={filtered}
          getKey={(row, index) => `${row.representative}-${row.symbol}-${row.transaction_date}-${index}`}
          columns={[
            { key: 'symbol', label: 'Stock', cell: (row) => (
              <details className="trade-identity-reveal">
                <summary><b className="mono">{row.symbol || '\u2013'}</b></summary>
                <span><b>{row.asset_description || 'Issuer unavailable'}</b><small>{row.representative || 'Representative unavailable'} \u00b7 {row.chamber}{row.district ? ` \u00b7 ${row.district}` : ''}</small></span>
              </details>) },
            { key: 'transaction_type', label: 'Type', cell: (row) => row.transaction_type || '\u2013' },
            { key: 'amount', label: 'Size', numeric: true, cell: (row) => <span className="mono">{row.amount || '\u2013'}</span> },
            { key: 'transaction_date', label: 'Traded', cell: (row) => <span className="mono">{row.transaction_date || '\u2013'}</span> },
            { key: 'filing_delay_days', label: 'Filed after',
              cell: (row) => <span className="mono">{row.filing_delay_days != null ? `${row.filing_delay_days}d` : '\u2013'}</span> },
            { key: 'return_since_purchase_pct', label: 'Since purchase', numeric: true,
              cell: (row) => row.return_since_purchase_pct != null
                ? <Move pct={row.return_since_purchase_pct} />
                : <span className="mono faint-cell">\u2013</span> },
            { key: 'flags', label: 'Flags', sortable: false, cell: (row) => <FlagChips flags={row.flags} /> },
          ]}
          mobile={{
            titleColumn: 'symbol',
            title: (row) => row.symbol || 'Ticker unavailable',
            subtitle: (row) => `${row.transaction_type || 'Transaction'} \u00b7 ${row.transaction_date || 'date unavailable'}`,
          }}
        />
      )}

      <p className="disclaimer">
        {data?.history_days != null && `${data.history_days} day(s) of accumulated history. `}
        Reported amounts are STOCK Act ranges, not exact figures. "Since purchase" only appears for a plain stock
        purchase with enough collected price history, and reflects the price move alone, nothing else.
        Research only, not investment advice. Schema {data?.schema_version} · model {data?.model_version}.
      </p>
    </>}
  </>
}
