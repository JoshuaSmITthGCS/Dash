import { useMemo, useState } from 'react'
import { useData } from '../lib/useData'
import { Empty, Loading } from '../components/Bits'
import { ScreenNavigation } from './ResearchScreen'
import ResultCards from '../components/ResultCards.jsx'
import { ResponsiveControlPanel } from '../components/MobileSheet.jsx'

const FLAG_LABELS = {
  CLUSTER_ACCUMULATION: 'Cluster accumulation',
  ACCUMULATION: 'Accumulation',
  DISTRIBUTION: 'Distribution',
  CLUSTER_DISTRIBUTION: 'Cluster distribution',
}

const pct = (value) => value == null ? '–' : `${value >= 0 ? '+' : ''}${(value * 100).toFixed(1)}%`

function FlagChip({ flag }) {
  if (!flag) return <span className="mono" style={{ color: 'var(--text-faint)' }}>–</span>
  return <span className={`chip ${flag.includes('ACCUMULATION') ? 'pos' : 'neg'}`}>
    {FLAG_LABELS[flag] || flag}
  </span>
}

export default function InstitutionalActivity() {
  const { data, loading, error } = useData('screens/institutional-13f.json')
  const [filters, setFilters] = useState({ flag: 'all', sort: 'recent' })
  const rows = data?.results || []

  const filtered = useMemo(() => {
    let next = rows
    if (filters.flag !== 'all') next = next.filter((row) => row.flag === filters.flag)
    const sorted = [...next]
    if (filters.sort === 'breadth') {
      sorted.sort((left, right) =>
        ((right.managers_added || 0) - (right.managers_dropped || 0)) -
        ((left.managers_added || 0) - (left.managers_dropped || 0)))
    } else {
      sorted.sort((left, right) => (right.as_of || '').localeCompare(left.as_of || ''))
    }
    return sorted
  }, [rows, filters])

  const update = (key) => (event) => setFilters((current) => ({ ...current, [key]: event.target.value }))

  return <>
    <ScreenNavigation />
    <div className="page-head">
      <div>
        <span className="eyebrow">SEC Form 13F-HR</span>
        <h1 className="page-title">Institutional <span className="accent">accumulation</span></h1>
        <p className="page-sub">
          Quarter-over-quarter position changes among a curated list of publicly traded, actively managed
          institutional filers – not the full 13F universe, and not index funds or private-equity managers, whose
          position changes track index membership or take-private deals rather than conviction. A flag reports how
          many of those curated managers added or cut a position; it is not a prediction and not investment advice.
        </p>
      </div>
    </div>

    {loading ? <Loading /> : error ? (
      <div className="card etf-state" role="alert"><strong>Institutional 13F screen unavailable</strong><span>{error.message}</span></div>
    ) : <>
      {data && data.status !== 'success' && (
        <div className="card etf-state" role="alert">
          <strong>{data.status === 'skipped' ? 'Collection did not run' : 'Collection did not complete'}</strong>
          <span>{data.degraded_reason || 'The last run published no holdings. Nothing below reflects current 13F filings.'}</span>
        </div>
      )}

      {data && data.status === 'success' && (
        <div className="grid congress-kpi-grid">
          <div className="card kpi">
            <div className="kpi-label">Managers reviewed</div>
            <div className="kpi-value">{data.managers_reviewed ?? '–'}</div>
            <div className="kpi-note">of {data.managers_configured ?? '–'} configured</div>
          </div>
          <div className="card kpi">
            <div className="kpi-label">Tickers flagged</div>
            <div className="kpi-value">{rows.length.toLocaleString('en-US')}</div>
          </div>
          <div className="card kpi">
            <div className="kpi-label">CUSIPs mapped</div>
            <div className="kpi-value">{data.cusips_mapped ?? '–'}</div>
            <div className="kpi-note">of {data.cusips_seen ?? '–'} seen</div>
          </div>
          <div className="card kpi">
            <div className="kpi-label">Amendments seen</div>
            <div className="kpi-value">{data.amendments_seen ?? '–'}</div>
            <div className="kpi-note">13F-HR/A revisions</div>
          </div>
        </div>
      )}

      <ResponsiveControlPanel label="Filter and sort" title="Filter results"><div className="screen-filters" aria-label="Institutional activity filters">
        <label>Flag
          <select value={filters.flag} onChange={update('flag')}>
            <option value="all">All</option>
            {Object.entries(FLAG_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>
        <label>Sort by
          <select value={filters.sort} onChange={update('sort')}>
            <option value="recent">Most recently filed</option>
            <option value="breadth">Largest manager breadth</option>
          </select>
        </label>
      </div></ResponsiveControlPanel>

      {!filtered.length ? (
        <Empty note={rows.length ? 'No results match these filters.'
          : data && data.status !== 'success'
            ? 'Nothing to show – the last collection run did not complete, so this is not a statement that no manager moved a position.'
            : 'No flagged activity yet – this screen updates monthly.'} />
      ) : (
        <>
        <ResultCards rows={filtered} getKey={(row, index) => `${row.ticker}-${row.cusip}-${index}`}
          title={(row) => row.ticker || 'Unknown ticker'}
          subtitle={(row) => row.cusip}
          fields={[
            { label: 'Managers added', value: (row) => row.managers_added ?? '–' },
            { label: 'Managers dropped', value: (row) => row.managers_dropped ?? '–' },
            { label: 'Share change', value: (row) => pct(row.share_change_pct) },
            { label: 'Flag', value: (row) => <FlagChip flag={row.flag} /> },
          ]} />
        <div className="research-table card">
          <table>
            <thead>
              <tr>
                <th>Ticker</th><th>CUSIP</th>
                <th className="num">Managers added</th><th className="num">Managers dropped</th>
                <th className="num">Share change</th><th>Flag</th><th>Filed</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((row, index) => (
                <tr key={`${row.ticker}-${row.cusip}-${index}`}>
                  <td><b>{row.ticker || '–'}</b></td>
                  <td className="mono" style={{ color: 'var(--text-faint)' }}>{row.cusip || '–'}</td>
                  <td className="mono num">{row.managers_added ?? '–'}</td>
                  <td className="mono num">{row.managers_dropped ?? '–'}</td>
                  <td className="num">{pct(row.share_change_pct)}</td>
                  <td><FlagChip flag={row.flag} /></td>
                  <td className="mono">{row.as_of || '–'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        </>
      )}

      <p className="disclaimer">
        {data?.disclaimer || 'Research only, not investment advice.'} Schema {data?.schema_version} · model {data?.model_version}.
      </p>
    </>}
  </>
}
