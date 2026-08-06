import { useMemo, useState } from 'react'
import { useData } from '../lib/useData'
import { Empty, Loading, Move } from '../components/Bits'
import { ScreenNavigation } from './ResearchScreen'
import ResultCards from '../components/ResultCards.jsx'
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

function FlagChips({ flags }) {
  if (!flags?.length) return <span className="mono" style={{ color: 'var(--text-faint)' }}>–</span>
  return <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
    {flags.map((flag) => <span key={flag} className="chip">{FLAG_LABELS[flag] || flag}</span>)}
  </div>
}

export default function CongressTrades() {
  const { data, loading, error } = useData('screens/congress-trades.json')
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
          Senate and House trade disclosures from Financial Modeling Prep, collected weekly. Flags are computed
          directly from the disclosure data – a late filing, an options trade, an unusually large or clustered
          position, a repeat pattern – not a claim that any trade was improper. Where a plain stock purchase has
          enough price history, "since purchase" shows how the stock has actually performed – a price fact, not a
          claim about why it moved or a recommendation to trade.
        </p>
      </div>
    </div>

    {loading ? <Loading /> : error ? (
      <div className="card etf-state" role="alert"><strong>Congress trades screen unavailable</strong><span>{error.message}</span></div>
    ) : <>
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
        <Empty note={rows.length ? 'No disclosures match these filters.' : 'No disclosures collected yet – this screen updates weekly.'} />
      ) : (
        <>
        <ResultCards rows={filtered} getKey={(row, index) => `${row.representative}-${row.symbol}-${row.transaction_date}-${index}`}
          title={(row) => row.representative || 'Unknown representative'}
          subtitle={(row) => `${row.chamber || 'Chamber unavailable'}${row.district ? ` · ${row.district}` : ''}`}
          fields={[
            { label: 'Issuer', value: (row) => row.asset_description || row.symbol || '–' },
            { label: 'Type', value: (row) => row.transaction_type || '–' },
            { label: 'Size', value: (row) => row.amount || '–' },
            { label: 'Traded', value: (row) => row.transaction_date || '–' },
            { label: 'Filed after', value: (row) => row.filing_delay_days != null ? `${row.filing_delay_days}d` : '–' },
            { label: 'Since purchase', value: (row) => row.return_since_purchase_pct != null ? <Move pct={row.return_since_purchase_pct} /> : '–' },
            { label: 'Flags', value: (row) => <FlagChips flags={row.flags} /> },
          ]} />
        <div className="research-table card">
          <table>
            <thead>
              <tr>
                <th>Representative</th><th>Issuer</th><th>Type</th>
                <th className="num">Size</th><th>Traded</th><th>Filed after</th>
                <th className="num">Since purchase</th><th>Flags</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((row, index) => (
                <tr key={`${row.representative}-${row.symbol}-${row.transaction_date}-${index}`}>
                  <td>
                    <b>{row.representative || '–'}</b>
                    <small style={{ display: 'block', textTransform: 'capitalize', color: 'var(--text-faint)' }}>
                      {row.chamber}{row.district ? ` · ${row.district}` : ''}
                    </small>
                  </td>
                  <td>
                    <span>{row.asset_description || row.symbol || '–'}</span>
                    {row.symbol && <small className="mono" style={{ display: 'block', color: 'var(--text-faint)' }}>{row.symbol}</small>}
                  </td>
                  <td>{row.transaction_type || '–'}</td>
                  <td className="mono num">{row.amount || '–'}</td>
                  <td className="mono">{row.transaction_date || '–'}</td>
                  <td className="mono">{row.filing_delay_days != null ? `${row.filing_delay_days}d` : '–'}</td>
                  <td className="num">
                    {row.return_since_purchase_pct != null ? <Move pct={row.return_since_purchase_pct} /> : <span className="mono" style={{ color: 'var(--text-faint)' }}>–</span>}
                  </td>
                  <td><FlagChips flags={row.flags} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        </>
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
