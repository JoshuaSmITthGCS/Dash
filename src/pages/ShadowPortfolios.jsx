import { ScreenNavigation } from './ResearchScreen'
import { useData } from '../lib/useData'
import { Loading } from '../components/Bits'
import DataTable from '../components/DataTable.jsx'
import AutoOverviewLine from '../components/AutoOverviewLine.jsx'

const metric = (value, suffix = '', row, minimum = 1) => {
  if (value != null) return `${Number(value).toFixed(2)}${suffix}`
  if (!row?.snapshots) return 'Not started'
  if (!row?.observations) return 'First return pending'
  return `${row.observations}/${minimum} returns`
}

const windowLabel = (row) => row.window_start && row.window_end
  ? `${row.window_start} → ${row.window_end}`
  : 'No matched window yet'

// Every strategy's headline covers whatever stretch of market it happened to observe, and
// those stretches differ - a sleeve that started collecting two sessions later simply was
// not in the market for the move the others were. The aligned figure is the only one that
// can be read across rows, so it is labelled as the comparable number rather than left for
// the reader to reconstruct from mismatched windows.
const aligned = (row, field, suffix = '%') => {
  if (!row?.observations) return '—'
  const value = row.aligned?.[field]
  if (value == null) return 'Outside shared window'
  return `${Number(value).toFixed(2)}${suffix}`
}

const signedReturn = (value) => `${Number(value) >= 0 ? '+' : '−'}${Math.abs(Number(value)).toFixed(2)}%`

function rankingOverview(strategies, alignedWindow, annualizedMinimum) {
  const sessions = Number(alignedWindow?.observations) || 0
  const ranked = strategies
    .filter((row) => row.observations > 0 && row.aligned?.net_return != null && Number.isFinite(Number(row.aligned.net_return)))
    .sort((left, right) => Number(right.aligned.net_return) - Number(left.aligned.net_return))

  if (!sessions || ranked.length < 2) {
    const waiting = strategies.filter((row) => !row.observations).length
    const waitingNote = waiting
      ? ` ${waiting} of ${strategies.length} ${strategies.length === 1 ? 'strategy has' : 'strategies have'} not started.`
      : ''
    return {
      tone: 'caution',
      text: `No comparable ranking yet. At least two strategies need a return from the same aligned window before they can be ordered fairly.${waitingNote}`,
    }
  }

  const leader = ranked[0]
  const sessionLabel = `${sessions} shared session${sessions === 1 ? '' : 's'}`
  const caveat = sessions < annualizedMinimum
    ? `Treat the order as an early read; annualized statistics need ${annualizedMinimum} matched returns.`
    : 'No strategy is promotion-eligible until 36 monthly observations are complete.'
  return {
    tone: sessions < annualizedMinimum ? 'caution' : 'positive',
    text: `${leader.strategy} ranks #1 of ${ranked.length} on aligned net return at ${signedReturn(leader.aligned.net_return)} over ${sessionLabel}. ${caveat}`,
  }
}

export default function ShadowPortfolios() {
  const { data, loading, error } = useData('screens/shadow-portfolios.json')
  if (loading) return <><ScreenNavigation /><Loading /></>
  const strategies = data?.strategies || []
  const live = strategies.filter((row) => row.observations > 0)
  const snapshots = strategies.reduce((total, row) => total + (row.snapshots || 0), 0)
  const alignedWindow = data?.aligned_window || {}
  const annualizedMinimum = Math.max(...strategies.map((row) => row.annualized_metrics_minimum_observations || 0), 20)
  const overview = rankingOverview(strategies, alignedWindow, annualizedMinimum)
  return <><ScreenNavigation /><div className="page-head"><div><span className="eyebrow">Prospective validation</span>
    <h1 className="page-title">Shadow portfolio performance</h1><p className="page-sub">Immutable, net-of-cost observations. No strategy is promoted from implementation alone.</p></div></div>
    {error ? <div className="card etf-state" role="alert"><strong>Shadow results unavailable</strong><span>{error.message}</span></div> : <>
      <AutoOverviewLine tone={overview.tone}>{overview.text}</AutoOverviewLine>
      <section className="shadow-validation-summary" aria-label="Shadow validation collection status">
        <article><span>Reporting now</span><strong>{live.length}</strong><small>strategies with matched returns</small></article>
        <article><span>Immutable snapshots</span><strong>{snapshots}</strong><small>one per market session, never rewritten</small></article>
        <article><span>Comparable window</span><strong>{alignedWindow.window_start ? `${alignedWindow.window_start.slice(5)} → ${alignedWindow.window_end.slice(5)}` : 'Starting'}</strong><small>{alignedWindow.observations || 0} sessions every strategy observed</small></article>
        <article><span>Implementation cost</span><strong>{live[0]?.cost_bps ?? 20} bps</strong><small>spread plus slippage</small></article>
      </section>
      {alignedWindow.observations > 0 && <p className="disclaimer">Each card below reports a strategy over its own collection window, which differs by strategy. Use the aligned net return to compare them: it covers only the {alignedWindow.observations} session{alignedWindow.observations === 1 ? '' : 's'} every reporting strategy was in the market for.</p>}
      <DataTable
        className="shadow-performance-table"
        rows={strategies}
        getKey={(row) => row.strategy}
        defaultSort={{ key: 'aligned', dir: 'desc' }}
        columns={[
          { key: 'strategy', label: 'Strategy', sortValue: (row) => row.strategy,
            cell: (row) => <><b>{row.strategy}</b><small className="shadow-window">{windowLabel(row)}</small></> },
          { key: 'aligned', label: 'Aligned net return', numeric: true,
            sortValue: (row) => row.aligned?.net_return ?? null, cell: (row) => aligned(row, 'net_return') },
          { key: 'net_return', label: 'Net return (own window)', numeric: true,
            cell: (row) => metric(row.net_return, '%', row) },
          { key: 'cagr', label: 'CAGR', numeric: true,
            cell: (row) => metric(row.cagr, '%', row, annualizedMinimum) },
          { key: 'sharpe', label: 'Sharpe', numeric: true,
            cell: (row) => metric(row.sharpe, '', row, annualizedMinimum) },
          { key: 'sortino', label: 'Sortino', numeric: true,
            cell: (row) => metric(row.sortino, '', row, annualizedMinimum) },
          { key: 'max_drawdown', label: 'Max drawdown', numeric: true,
            cell: (row) => metric(row.max_drawdown, '%', row) },
          { key: 'turnover', label: 'Turnover', numeric: true,
            cell: (row) => metric(row.turnover, '%', row) },
          { key: 'composition_change', label: 'Coverage change', numeric: true,
            cell: (row) => row.composition_change != null ? `${Number(row.composition_change).toFixed(2)}% not traded` : '\u2014' },
          { key: 'observations', label: 'Observations', numeric: true,
            cell: (row) => <>{row.observations || 0}<small className="shadow-window">{row.snapshots || 0} snapshots</small></> },
          { key: 'evidence_status', label: 'Evidence status', sortable: false,
            cell: (row) => <span className={`shadow-evidence-status ${row.observations ? 'live' : ''}`}>{row.evidence_status || 'Insufficient observations'}</span> },
        ]}
        mobile={{
          titleColumn: 'strategy',
          title: (row) => row.strategy,
          subtitle: (row) => row.evidence_status || 'Insufficient observations',
        }}
      />
      </>}
    <p className="disclaimer">Signal comparisons use identical weighting and declared costs. A return is recorded only when the price tape advances to a new market session, so a refresh that re-reads the same closes adds no observation. Coverage change reports weight that entered because more of the universe became priced, which is disclosed rather than charged as turnover. Annualized statistics remain gated until {annualizedMinimum} matched returns exist; promotion remains gated until 36 monthly observations. Full-strategy comparisons are labeled separately.</p>
  </>
}
