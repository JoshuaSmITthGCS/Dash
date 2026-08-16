import { useMemo, useState } from 'react'
import { useData } from '../lib/useData'
import { useScreenRefresh } from '../lib/useScreenRefresh'
import { Empty, Loading, RefreshProgress } from '../components/Bits'
import Icon from '../components/Icons.jsx'
import { ScreenNavigation } from './ResearchScreen'
import DataTable from '../components/DataTable.jsx'
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
  const { data, loading, error, reload } = useData('screens/institutional-13f.json')
  const refresh = useScreenRefresh('institutional', reload)
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
      {refresh.available && (
        <div className="page-actions">
          {/* This screen is on a monthly cron and the main research refresh does not
              collect it, so without this the only way to re-run it is to wait. */}
          <button className="secondary-button" onClick={refresh.requestRefresh} disabled={refresh.refreshing}
            title="Re-run the 13F collection now – it reads SEC EDGAR directly and takes a few minutes">
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
            {/* Mapping a CUSIP to a ticker is rate-limited, so a run can legitimately finish
                with some still unresolved. Saying so keeps a partial map from reading as a
                complete one - the unmapped holdings are absent from the table below. */}
            <div className="kpi-note">
              of {data.cusips_seen ?? '–'} seen
              {data.cusips_pending ? `, ${data.cusips_pending} awaiting lookup` : ''}
            </div>
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
        <DataTable
          rows={filtered}
          getKey={(row, index) => `${row.ticker}-${row.cusip}-${index}`}
          columns={[
            { key: 'ticker', label: 'Ticker', cell: (row) => <b>{row.ticker || '\u2013'}</b> },
            { key: 'cusip', label: 'CUSIP', cell: (row) => <span className="mono cusip-cell">{row.cusip || '\u2013'}</span> },
            { key: 'managers_added', label: 'Managers added', numeric: true,
              cell: (row) => <span className="mono">{row.managers_added ?? '\u2013'}</span> },
            { key: 'managers_dropped', label: 'Managers dropped', numeric: true,
              cell: (row) => <span className="mono">{row.managers_dropped ?? '\u2013'}</span> },
            { key: 'share_change_pct', label: 'Share change', numeric: true, cell: (row) => pct(row.share_change_pct) },
            { key: 'flag', label: 'Flag', cell: (row) => <FlagChip flag={row.flag} /> },
            { key: 'as_of', label: 'Filed', cell: (row) => <span className="mono">{row.as_of || '\u2013'}</span> },
          ]}
          mobile={{
            titleColumn: 'ticker',
            title: (row) => row.ticker || 'Unknown ticker',
            subtitle: (row) => row.cusip,
          }}
        />
      )}

      <p className="disclaimer">
        {data?.disclaimer || 'Research only, not investment advice.'} Schema {data?.schema_version} · model {data?.model_version}.
      </p>
    </>}
  </>
}
