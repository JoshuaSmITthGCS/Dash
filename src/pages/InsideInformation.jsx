import { useMemo, useState } from 'react'
import { useData } from '../lib/useData'
import { useScreenRefresh } from '../lib/useScreenRefresh'
import { Empty, Loading, RefreshProgress } from '../components/Bits'
import Icon from '../components/Icons.jsx'
import { ScreenNavigation } from './ResearchScreen'
import DataTable from '../components/DataTable.jsx'

const INSTITUTIONAL_FLAG_LABELS = {
  CLUSTER_ACCUMULATION: 'Cluster accumulation',
  CLUSTER_DISTRIBUTION: 'Cluster distribution',
}

const CONGRESS_FLAG_LABELS = {
  EXTRAORDINARY_BUY: 'First trade in a small, unfamiliar company',
  CLUSTER_TRADE: '3+ representatives, 14-day span',
  BUY_SELL_FLIP: 'Round trip within 60 days',
}

function FlagChip({ label, tone }) {
  return <span className={tone ? `chip ${tone}` : 'chip'}>{label}</span>
}

export default function InsideInformation() {
  const { data, loading, error, reload } = useData('screens/inside-information.json')
  const refresh = useScreenRefresh('inside-information', reload)
  const [sort, setSort] = useState('score')
  const rows = data?.results || []

  const sorted = useMemo(() => {
    const next = [...rows]
    if (sort === 'institutional') {
      next.sort((left, right) => (right.institutional_points || 0) - (left.institutional_points || 0))
    } else if (sort === 'congress') {
      next.sort((left, right) => (right.political_points || 0) - (left.political_points || 0))
    } else {
      next.sort((left, right) => (right.score || 0) - (left.score || 0))
    }
    return next
  }, [rows, sort])

  return <>
    <ScreenNavigation />
    <div className="page-head">
      <div>
        <span className="eyebrow">Congress + institutional 13F, merged</span>
        <h1 className="page-title">Inside <span className="accent">information</span></h1>
        <p className="page-sub">
          Congressional STOCK Act disclosures and curated active-manager Schedule 13F filings, combined into one
          view and shown only where the underlying screen already flagged the activity as rare or notable – a
          cluster of managers moving together, several representatives trading the same name in a short span, a
          round trip, or a representative's first-ever trade in a small, unfamiliar company. Not a claim that any
          of this activity was informed or improper; see the individual Politics and Institutional screens for the
          full, unfiltered disclosures.
        </p>
      </div>
      {refresh.available && (
        <div className="page-actions">
          <button className="secondary-button" onClick={refresh.requestRefresh} disabled={refresh.refreshing}
            title="Re-merge the last published congress and institutional 13F screens">
            <Icon name="sync" size={17} className={refresh.refreshing ? 'refresh-spin' : ''} />
            {refresh.refreshing ? 'Merging…' : 'Re-run merge'}
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
      <div className="card etf-state" role="alert"><strong>Inside Information screen unavailable</strong><span>{error.message}</span></div>
    ) : <>
      {data && data.status !== 'success' && (
        <div className="card etf-state" role="alert">
          <strong>{data.status === 'skipped' ? 'Merge did not run' : 'Merge did not complete'}</strong>
          <span>Neither the Politics nor the Institutional screen has published results yet.</span>
        </div>
      )}

      {data && data.status === 'success' && (
        <div className="grid congress-kpi-grid">
          <div className="card kpi">
            <div className="kpi-label">Tickers with disclosed activity</div>
            <div className="kpi-value">{data.ranked_count ?? '–'}</div>
          </div>
          <div className="card kpi">
            <div className="kpi-label">Notable (shown below)</div>
            <div className="kpi-value">{data.notable_count ?? '–'}</div>
            <div className="kpi-note">rare/flagged activity only</div>
          </div>
        </div>
      )}

      <div className="screen-filters" aria-label="Inside information sort">
        <label>Sort by
          <select value={sort} onChange={(event) => setSort(event.target.value)}>
            <option value="score">Combined score</option>
            <option value="institutional">Institutional points</option>
            <option value="congress">Congressional points</option>
          </select>
        </label>
      </div>

      {!sorted.length ? (
        <Empty note={data && data.status !== 'success'
          ? 'Nothing to show – the last merge did not complete.'
          : 'No notable activity right now – most disclosed trading is routine and stays on the individual Politics and Institutional screens.'} />
      ) : (
        <DataTable
          rows={sorted}
          getKey={(row) => row.ticker}
          columns={[
            { key: 'ticker', label: 'Ticker', cell: (row) => <b>{row.ticker}</b> },
            { key: 'score', label: 'Combined score', numeric: true,
              cell: (row) => <span className="mono">{row.score?.toFixed(2) ?? '–'}</span> },
            { key: 'institutional_flag', label: 'Institutional', cell: (row) => (
              row.institutional_flag && INSTITUTIONAL_FLAG_LABELS[row.institutional_flag]
                ? <FlagChip label={INSTITUTIONAL_FLAG_LABELS[row.institutional_flag]}
                    tone={row.institutional_flag === 'CLUSTER_ACCUMULATION' ? 'pos' : 'neg'} />
                : <span className="mono text-faint">–</span>
            ) },
            { key: 'congress_flags', label: 'Congressional', cell: (row) => (
              row.congress_flags?.length
                ? <div className="congress-flag-row">
                    {row.congress_flags.map((flag) => (
                      <FlagChip key={flag} label={CONGRESS_FLAG_LABELS[flag] || flag} />
                    ))}
                  </div>
                : <span className="mono text-faint">–</span>
            ) },
            { key: 'members_buying', label: 'Members buying', numeric: true,
              cell: (row) => <span className="mono">{row.members_buying ?? '–'}</span> },
            { key: 'managers_added', label: 'Managers added', numeric: true,
              cell: (row) => <span className="mono">{row.managers_added ?? '–'}</span> },
          ]}
          mobile={{
            titleColumn: 'ticker',
            title: (row) => row.ticker,
            subtitle: (row) => `score ${row.score?.toFixed(2) ?? '–'}`,
          }}
        />
      )}

      <p className="disclaimer">
        {data?.disclaimer || 'Research only, not investment advice.'} Schema {data?.schema_version} · model {data?.model_version}.
      </p>
    </>}
  </>
}
