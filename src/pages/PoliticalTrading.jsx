import { useMemo, useState } from 'react'
import { useData } from '../lib/useData'
import { Empty, Loading, Move, RefreshProgress } from '../components/Bits'
import Icon from '../components/Icons.jsx'
import { useScreenRefresh } from '../lib/useScreenRefresh'
import { ScreenNavigation } from './ResearchScreen'
import DataTable from '../components/DataTable.jsx'
import { ResponsiveControlPanel } from '../components/MobileSheet.jsx'
import BarTimeline from '../components/BarTimeline.jsx'

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

// One point per calendar month of the disclosed trade's transaction date (when the
// trade happened, not when it was disclosed), summing each row's amount-range midpoint
// — the disclosure forms report a band, not an exact dollar figure, so the midpoint is
// the least-wrong single number to add across rows.
function monthlyVolume(rows) {
  const byMonth = new Map()
  rows.forEach((row) => {
    const month = (row.transaction_date || '').slice(0, 7)
    if (!month) return
    const lower = row.amount_lower
    const upper = row.amount_upper
    if (lower == null && upper == null) return
    const midpoint = lower != null && upper != null ? (lower + upper) / 2 : (lower ?? upper)
    byMonth.set(month, (byMonth.get(month) || 0) + midpoint)
  })
  return [...byMonth.entries()]
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([month, value]) => ({ id: month, label: month, value }))
}

// Three tiers over the published per-trade signal_strength (build_congress_screen's
// politician_performance.signal_strength: disclosed size x recency x the filer's shrunk,
// market-relative performance track record). Display-only ranking aid, never an
// advisor_engine input - same disclaimer every other panel on this page already carries.
const SIGNAL_TIERS = [
  { id: 'strong', min: 0.8, tone: 'high', label: 'Strong' },
  { id: 'moderate', min: 0.3, tone: 'watch', label: 'Moderate' },
  { id: 'weak', min: 0, tone: 'neutral', label: 'Weak' },
]

function signalTier(strength) {
  const value = strength ?? 0
  return SIGNAL_TIERS.find((tier) => value >= tier.min) || SIGNAL_TIERS[SIGNAL_TIERS.length - 1]
}

function performanceLookup(data) {
  const board = data?.politician_performance?.leaderboard || []
  const byName = new Map(board.map((row) => [row.politician, row]))
  return (representative) => byName.get(representative) || null
}

// Not a black box: the badge alone is a bucketed strength label, so the expand shows the
// filer's actual shrunk win rate, average alpha vs SPY, and how many priced buys that is
// built from - stats absent for a filer with no priced buy yet (their signal still uses
// the population baseline, but there is nothing politician-specific to show).
function SignalBadge({ strength, stats }) {
  const tier = signalTier(strength)
  return (
    <details className="trade-identity-reveal signal-badge-reveal">
      <summary><span className={`tier ${tier.tone}`}>{tier.label}</span></summary>
      <span className="signal-badge-detail">
        {stats ? <>
          <b>{`${Math.round(stats.win_rate * 100)}% beat S&P`}</b>
          <small>{`avg alpha ${stats.avg_alpha_pct >= 0 ? '+' : ''}${stats.avg_alpha_pct.toFixed(1)}pp · ${stats.n_priced_buys} priced buy${stats.n_priced_buys === 1 ? '' : 's'} · ${stats.confidence} confidence`}</small>
        </> : <b>No priced track record yet</b>}
      </span>
    </details>
  )
}

function FlagChips({ flags }) {
  if (!flags?.length) return <span className="mono text-faint">–</span>
  return <div className="congress-flag-row">
    {flags.map((flag) => <span key={flag} className="chip">{FLAG_LABELS[flag] || flag}</span>)}
  </div>
}

// A member of Congress reads as "chamber · district"; an executive-branch filer
// (office/agency present, no district) reads as "office · agency" instead.
function filerRole(row) {
  if (row.office) return [row.office, row.agency].filter(Boolean).join(' · ')
  return [row.chamber, row.district].filter(Boolean).join(' · ')
}

function filerLine(row) {
  return [row.representative, filerRole(row)].filter(Boolean).join(' · ')
}

// notable_signals()'s top-5 leaderboard: display-only, not a score - see
// build_congress_screen.py's docstring on why this never feeds the research score the way
// congress_signal.score_congressional_buying does.
function SignalsPanel({ signals }) {
  if (!signals?.length) return null
  return (
    <div className="card political-signals" aria-label="Most notable disclosures">
      <div className="political-signals-head">
        <h2 className="political-signals-title">Top disclosed signals</h2>
        <span className="political-signals-note">Largest, most novel, or most clustered disclosed trades this window – not a score, not advice.</span>
      </div>
      <ol className="political-signals-list">
        {signals.map((signal) => (
          <li key={signal.ticker} className="political-signal-card">
            <span className={`chip signal-direction ${signal.direction === 'BUY' ? 'positive' : 'negative'}`}>
              {signal.direction}
            </span>
            <b className="mono">{signal.ticker}</b>
            <span className="political-signal-filer">{filerLine(signal)}</span>
            <FlagChips flags={signal.flags} />
          </li>
        ))}
      </ol>
    </div>
  )
}

// top_ticker_aggregates()'s per-stock leaderboard: every disclosed trade in the window
// rolled up by ticker, so a stock several different filers quietly bought in separate
// tranches ranks alongside one filer's single outsized trade - display-only, same
// disclaimer as SignalsPanel above.
function TopTickersPanel({ tickers }) {
  if (!tickers?.length) return null
  return (
    <div className="card political-signals" aria-label="Top 10 unusual stocks">
      <div className="political-signals-head">
        <h2 className="political-signals-title">Top 10 unusual stocks</h2>
        <span className="political-signals-note">
          Every disclosed Congress and executive-branch trade this window, rolled up per stock by disclosed
          volume, how many distinct filers traded it, and clustering/novelty flags – not a score, not advice.
        </span>
      </div>
      <DataTable
        rows={tickers}
        getKey={(row) => row.ticker}
        columns={[
          { key: 'rank', label: '#', cell: (row) => <span className="mono">{row.rank}</span> },
          { key: 'symbol', label: 'Stock', cell: (row) => (
            <details className="trade-identity-reveal">
              <summary><b className="mono">{row.ticker}</b></summary>
              <span><b>{row.asset_description || 'Issuer unavailable'}</b></span>
            </details>) },
          { key: 'disclosed_volume_midpoint', label: 'Disclosed volume', numeric: true,
            cell: (row) => <span className="mono">{compactMoney(row.disclosed_volume_midpoint)}</span> },
          { key: 'max_single_trade_amount_upper', label: 'Biggest single trade', numeric: true,
            cell: (row) => <span className="mono">{compactMoney(row.max_single_trade_amount_upper)}</span> },
          { key: 'trade_count', label: 'Trades', numeric: true, cell: (row) => (
            <span className="mono">{`${row.trade_count} (${row.buy_count} buy / ${row.sell_count} sell)`}</span>) },
          { key: 'unique_politicians', label: 'Distinct filers', numeric: true, cell: (row) => (
            <details className="trade-identity-reveal">
              <summary><span className="mono">{row.unique_politicians}</span></summary>
              <span>{(row.politicians || []).join(', ') || 'Filer unavailable'}</span>
            </details>) },
          { key: 'flags', label: 'Flags', sortable: false, cell: (row) => <FlagChips flags={row.flags} /> },
        ]}
        mobile={{
          titleColumn: 'symbol',
          title: (row) => row.ticker,
          subtitle: (row) => `${compactMoney(row.disclosed_volume_midpoint)} disclosed · ${row.unique_politicians} filer(s)`,
        }}
      />
    </div>
  )
}

export default function PoliticalTrading() {
  const { data, loading, error, reload } = useData('screens/congress-trades.json')
  const refresh = useScreenRefresh('congress', reload)
  const [filters, setFilters] = useState({ chamber: 'all', flag: 'all', signal: 'all', sort: 'disclosed' })
  const rows = data?.results || []
  const summary = data?.summary
  const lookupPerformance = useMemo(() => performanceLookup(data), [data])

  const filtered = useMemo(() => {
    let next = rows.filter((row) => filters.chamber === 'all' || row.chamber === filters.chamber)
    if (filters.flag !== 'all') next = next.filter((row) => (row.flags || []).includes(filters.flag))
    if (filters.signal !== 'all') next = next.filter((row) => signalTier(row.signal_strength).id === filters.signal)
    const sorted = [...next]
    if (filters.sort === 'amount') {
      sorted.sort((left, right) => (right.amount_upper || 0) - (left.amount_upper || 0))
    } else if (filters.sort === 'performance') {
      sorted.sort((left, right) => (right.return_since_purchase_pct ?? -Infinity) - (left.return_since_purchase_pct ?? -Infinity))
    } else if (filters.sort === 'signal') {
      sorted.sort((left, right) => (right.signal_strength ?? -Infinity) - (left.signal_strength ?? -Infinity))
    } else {
      sorted.sort((left, right) => (right.disclosure_date || '').localeCompare(left.disclosure_date || ''))
    }
    return sorted
  }, [rows, filters])

  const update = (key) => (event) => setFilters((current) => ({ ...current, [key]: event.target.value }))
  const volumeByMonth = useMemo(() => monthlyVolume(rows), [rows])

  return <>
    <ScreenNavigation />
    <div className="page-head">
      <div>
        <span className="eyebrow">STOCK Act &amp; OGE 278-T disclosures</span>
        <h1 className="page-title">Political <span className="accent">trade alert</span></h1>
        <p className="page-sub">
          Senate, House, and executive-branch (OGE Form 278-T, including the President) trade disclosures,
          collected weekly from Financial Modeling Prep and the public House/Senate/executive-branch disclosure
          datasets – all mirrors of the same Clerk, eFD, and OGE filings. Flags are computed directly from the
          disclosure data – a late filing, an options trade, an unusually large or clustered position, a repeat
          pattern – not a claim that any trade was improper. Where a plain stock purchase has enough price
          history, "since purchase" shows how the stock has actually performed – a price fact, not a claim about
          why it moved or a recommendation to trade.
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
      <div className="card etf-state" role="alert"><strong>Political trades screen unavailable</strong><span>{error.message}</span></div>
    ) : <>
      {data && data.status === 'partial' && (
        // Rows are real but incomplete: at least one source answered and at least one did
        // not, so what follows understates the week rather than describing it.
        <div className="card etf-state" role="alert">
          <strong>Collected from some sources only</strong>
          <span>{`Some disclosures below may be missing – ${(data.collection?.failures || []).join('; ')}`}</span>
        </div>
      )}

      <SignalsPanel signals={data?.signals} />
      <TopTickersPanel tickers={data?.top_tickers} />

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

      <BarTimeline
        points={volumeByMonth}
        yLabel="Disclosed volume"
        yFormatter={compactMoney}
        caption="Disclosed trade volume by month, midpoint of each disclosure's reported amount range"
      />

      <ResponsiveControlPanel label="Filter and sort" title="Filter disclosures"><div className="screen-filters" aria-label="Disclosure filters">
        <label>Chamber
          <select value={filters.chamber} onChange={update('chamber')}>
            <option value="all">All</option>
            <option value="senate">Senate</option>
            <option value="house">House</option>
            <option value="executive">Executive branch</option>
          </select>
        </label>
        <label>Flag
          <select value={filters.flag} onChange={update('flag')}>
            <option value="all">All</option>
            {Object.entries(FLAG_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>
        <label>Signal
          <select value={filters.signal} onChange={update('signal')}>
            <option value="all">All</option>
            {SIGNAL_TIERS.map((tier) => <option key={tier.id} value={tier.id}>{tier.label}</option>)}
          </select>
        </label>
        <label>Sort by
          <select value={filters.sort} onChange={update('sort')}>
            <option value="disclosed">Most recently disclosed</option>
            <option value="amount">Largest reported amount</option>
            <option value="performance">Best performance since purchase</option>
            <option value="signal">Highest weighted signal</option>
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
                <span><b>{row.asset_description || 'Issuer unavailable'}</b><small>{row.representative || 'Representative unavailable'} \u00b7 {filerRole(row)}</small></span>
              </details>) },
            { key: 'signal_strength', label: 'Signal', numeric: true,
              cell: (row) => <SignalBadge strength={row.signal_strength} stats={lookupPerformance(row.representative)} /> },
            { key: 'transaction_type', label: 'Type', cell: (row) => row.transaction_type || '\u2013' },
            { key: 'amount', label: 'Size', numeric: true, cell: (row) => <span className="mono">{row.amount || '\u2013'}</span> },
            { key: 'transaction_date', label: 'Traded', cell: (row) => <span className="mono">{row.transaction_date || '\u2013'}</span> },
            { key: 'filing_delay_days', label: 'Filed after',
              cell: (row) => <span className="mono">{row.filing_delay_days != null ? `${row.filing_delay_days}d` : '\u2013'}</span> },
            { key: 'return_since_purchase_pct', label: 'Since purchase', numeric: true,
              cell: (row) => row.return_since_purchase_pct != null
                ? <Move pct={row.return_since_purchase_pct} />
                : <span className="mono faint-cell">–</span> },
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
