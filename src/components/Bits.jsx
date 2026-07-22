import { tierClass, fmtPct } from '../lib/useData'

export function Tier({ label }) {
  if (!label) return null
  return <span className={`tier ${tierClass(label)}`}>{label}</span>
}

const FACTOR_LABELS = {
  track_record: 'Track record',
  committee_relevance: 'Committee',
  cluster_detection: 'Cluster',
  trade_size: 'Trade size',
  direction_recency: 'Recency',
  policy_catalyst: 'Policy catalyst',
}
const FACTOR_MAX = {
  track_record: 25, committee_relevance: 20, cluster_detection: 20,
  trade_size: 15, direction_recency: 10, policy_catalyst: 10,
}

// Shows WHY a signal scored what it did — bars per factor.
export function ScoreBreakdown({ breakdown }) {
  if (!breakdown) return null
  return (
    <div style={{ display: 'grid', gap: 7 }}>
      {Object.entries(breakdown).map(([k, v]) => (
        <div className="bar-row" key={k}>
          <span className="bar-lab">{FACTOR_LABELS[k] || k}</span>
          <span className="bar-track">
            <span className="bar-fill" style={{ width: `${(v / FACTOR_MAX[k]) * 100}%` }} />
          </span>
          <span className="bar-val">{v}</span>
        </div>
      ))}
    </div>
  )
}

// Fundamental snapshot: valuation, profitability, cash generation, and balance-sheet health.
export function MetricPills({ peg, forward_pe, price_to_sales, price_to_book,
  return_on_equity, free_cash_flow_yield, debt_to_equity, current_ratio,
  fundamental_coverage, isEtf }) {
  if (isEtf) return <div className="chip">ETF — corporate fundamentals N/A</div>
  const pegClass = peg == null ? '' : peg > 0 && peg <= 1.5 ? 'good' : peg > 2.5 ? 'rich' : ''
  const pbClass = price_to_book == null ? '' : price_to_book <= 3 ? 'good' : price_to_book > 10 ? 'rich' : ''
  const roeClass = return_on_equity == null ? '' : return_on_equity >= 0.15 ? 'good' : return_on_equity < 0 ? 'rich' : ''
  const fcfClass = free_cash_flow_yield == null ? '' : free_cash_flow_yield >= 0.05 ? 'good' : free_cash_flow_yield < 0 ? 'rich' : ''
  const debtClass = debt_to_equity == null ? '' : debt_to_equity <= 1 ? 'good' : debt_to_equity > 2 ? 'rich' : ''
  const currentClass = current_ratio == null ? '' : current_ratio >= 1 ? 'good' : current_ratio < 0.75 ? 'rich' : ''
  const pct = (value) => value == null ? '—' : `${(value * 100).toFixed(1)}%`
  return (
    <div className="metrics" aria-label="Fundamental metrics">
      <div className={`metric ${pegClass}`}><b>{peg ?? '—'}</b><span>PEG</span></div>
      <div className="metric"><b>{forward_pe ?? '—'}</b><span>Fwd P/E</span></div>
      <div className="metric"><b>{price_to_sales ?? '—'}</b><span>P/S</span></div>
      <div className={`metric ${pbClass}`}><b>{price_to_book ?? '—'}</b><span>P/B</span></div>
      <div className={`metric ${roeClass}`}><b>{pct(return_on_equity)}</b><span>ROE</span></div>
      <div className={`metric ${fcfClass}`}><b>{pct(free_cash_flow_yield)}</b><span>FCF yield</span></div>
      <div className={`metric ${debtClass}`}><b>{debt_to_equity ?? '—'}</b><span>D/E</span></div>
      <div className={`metric ${currentClass}`}><b>{current_ratio ?? '—'}</b><span>Current</span></div>
      {fundamental_coverage != null && <div className="metric coverage"><b>{Math.round(fundamental_coverage * 100)}%</b><span>Coverage</span></div>}
    </div>
  )
}

export function Move({ pct }) {
  if (pct == null) return <span className="mono">—</span>
  return <span className={`mono ${pct >= 0 ? 'pos' : 'neg'}`}>{fmtPct(pct)}</span>
}

export function Lag({ days }) {
  if (days == null) return null
  return <span className="lag">trade filed ~{days}d ago</span>
}

export function Loading({ label = 'loading data' }) {
  return <div className="card card-pad" style={{ color: 'var(--text-faint)', fontFamily: 'var(--font-mono)', fontSize: 12 }}>◍ {label}…</div>
}

export function Empty({ note }) {
  return <div className="card card-pad" style={{ color: 'var(--text-faint)', fontFamily: 'var(--font-mono)', fontSize: 12 }}>{note || 'No data yet — run the pipeline.'}</div>
}
