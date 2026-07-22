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

// Valuation pills: PEG / Fwd P/E / P/S with quality coloring.
export function MetricPills({ peg, forward_pe, price_to_sales, isEtf }) {
  if (isEtf) return <div className="chip">ETF — valuation metrics N/A</div>
  const pegClass = peg == null ? '' : peg > 0 && peg <= 1.5 ? 'good' : peg > 2.5 ? 'rich' : ''
  const psClass = price_to_sales == null ? '' : price_to_sales <= 2 ? 'good' : price_to_sales > 12 ? 'rich' : ''
  const feClass = forward_pe == null ? '' : forward_pe > 0 && forward_pe <= 15 ? 'good' : forward_pe > 40 ? 'rich' : ''
  return (
    <div className="metrics">
      <div className={`metric ${pegClass}`}><b>{peg ?? '—'}</b><span>PEG</span></div>
      <div className={`metric ${feClass}`}><b>{forward_pe ?? '—'}</b><span>Fwd P/E</span></div>
      <div className={`metric ${psClass}`}><b>{price_to_sales ?? '—'}</b><span>P/S</span></div>
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
