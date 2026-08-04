import { useMemo, useState } from 'react'
import { useData } from '../lib/useData'
import { Empty, Loading } from '../components/Bits'
import { ScreenNavigation } from './ResearchScreen'

const FLAG_LABELS = {
  LATE_FILING: 'Late filing',
  OPTIONS_TRADE: 'Options trade',
  RARE_TRADER: 'Rare trader',
}

const money = (value) =>
  value == null ? '—' : `$${Number(value).toLocaleString('en-US', { maximumFractionDigits: 0 })}`

function FlagChips({ flags }) {
  if (!flags?.length) return <span className="mono" style={{ color: 'var(--text-faint)' }}>—</span>
  return <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
    {flags.map((flag) => <span key={flag} className="chip">{FLAG_LABELS[flag] || flag}</span>)}
  </div>
}

export default function CongressTrades() {
  const { data, loading, error } = useData('screens/congress-trades.json')
  const [filters, setFilters] = useState({ chamber: 'all', flag: 'all', sort: 'disclosed' })
  const rows = data?.results || []

  const filtered = useMemo(() => {
    let next = rows.filter((row) => filters.chamber === 'all' || row.chamber === filters.chamber)
    if (filters.flag !== 'all') next = next.filter((row) => (row.flags || []).includes(filters.flag))
    const sorted = [...next]
    if (filters.sort === 'amount') {
      sorted.sort((left, right) => (right.amount_upper || 0) - (left.amount_upper || 0))
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
          Senate and House trade disclosures from Financial Modeling Prep, collected weekly. Flags a filing that
          missed the STOCK Act's 45-day disclosure window, an options trade, or a representative's only disclosed
          trade in the accumulated history — not a claim that any trade was improper.
        </p>
      </div>
      <div className="result-count"><strong>{filtered.length}</strong><span>of {rows.length} disclosures</span></div>
    </div>

    {loading ? <Loading /> : error ? (
      <div className="card etf-state" role="alert"><strong>Congress trades screen unavailable</strong><span>{error.message}</span></div>
    ) : <>
      <div className="screen-filters" aria-label="Disclosure filters">
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
            <option value="LATE_FILING">Late filing</option>
            <option value="OPTIONS_TRADE">Options trade</option>
            <option value="RARE_TRADER">Rare trader</option>
          </select>
        </label>
        <label>Sort by
          <select value={filters.sort} onChange={update('sort')}>
            <option value="disclosed">Most recently disclosed</option>
            <option value="amount">Largest reported amount</option>
          </select>
        </label>
      </div>

      {!filtered.length ? (
        <Empty note={rows.length ? 'No disclosures match these filters.' : 'No disclosures collected yet — this screen updates weekly.'} />
      ) : (
        <div className="research-table card">
          <table>
            <thead>
              <tr>
                <th>Representative</th><th>Chamber</th><th>Ticker</th><th>Type</th>
                <th className="num">Amount</th><th>Traded</th><th>Disclosed</th><th>Flags</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((row, index) => (
                <tr key={`${row.representative}-${row.symbol}-${row.transaction_date}-${index}`}>
                  <td><b>{row.representative || '—'}</b>{row.district && <small> {row.district}</small>}</td>
                  <td style={{ textTransform: 'capitalize' }}>{row.chamber}</td>
                  <td className="mono">{row.symbol || '—'}</td>
                  <td>{row.transaction_type || '—'}</td>
                  <td className="mono num">{money(row.amount_upper)}</td>
                  <td className="mono">{row.transaction_date || '—'}</td>
                  <td className="mono">{row.disclosure_date || '—'}</td>
                  <td><FlagChips flags={row.flags} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="disclaimer">
        {data?.history_days != null && `${data.history_days} day(s) of accumulated history. `}
        Reported amounts are STOCK Act ranges, not exact figures — this table shows the range's upper bound.
        Research only, not investment advice. Schema {data?.schema_version} · model {data?.model_version}.
      </p>
    </>}
  </>
}
