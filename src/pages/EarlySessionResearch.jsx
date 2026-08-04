import { useData } from '../lib/useData'
import { Loading } from '../components/Bits'
import { ScreenNavigation } from './ResearchScreen'

const titleCase = (value = '') => value.toLowerCase().replaceAll('_', ' ')

function StatusMark({ available, verdict }) {
  const conditional = available && verdict !== 'DAILY_CONTEXT_ONLY'
  const label = available ? (conditional ? 'Conditional' : 'Available') : 'Unavailable'
  return <span className={`gate-status ${available ? 'available' : 'unavailable'}`}>
    <span aria-hidden="true" />{label}
  </span>
}

export default function EarlySessionResearch() {
  const { data, loading, error } = useData('screens/early-session.json')
  const screens = Object.entries(data?.screens || {})

  return <>
    <ScreenNavigation />
    <div className="page-head early-session-head">
      <div><span className="eyebrow">Shadow mode · capability gated</span>
        <h1 className="page-title">Early-session reversals</h1>
        <p className="page-sub">Premarket and first-hour research stays off until the platform collects the market data needed to distinguish structure from stale snapshots.</p>
      </div>
      <div className="gate-summary" aria-label="Subsystem status"><span>Current verdict</span><strong>Gated</strong><small>0 live candidates</small></div>
    </div>

    {loading ? <Loading /> : error ? <div className="card etf-state" role="alert"><strong>Capability report unavailable</strong><span>{error.message}</span></div> : <>
      <section className="screen-gate-grid" aria-label="Early-session screen verdicts">
        {screens.map(([name, screen]) => <article className="screen-gate-card" key={name}>
          <div><span className="screen-gate-kicker">{name === 'premarket_reversal' ? 'Before open' : '09:30–10:30 ET'}</span>
            <h2>{titleCase(name)}</h2></div>
          <span className="screen-killed">Killed by data gate</span>
          <p>{screen.reason_code === 'NO_EXTENDED_HOURS_OHLCV'
            ? 'No timestamped extended-hours OHLCV is collected. Daily prior closes cannot stand in for premarket activity.'
            : 'No retained bars at 15-minute or finer granularity are collected, so first-hour structure cannot be observed.'}</p>
          <dl><div><dt>Fallback</dt><dd>{titleCase(screen.fallback)}</dd></div><div><dt>Candidates</dt><dd>{screen.candidate_count}</dd></div></dl>
        </article>)}
      </section>

      <section className="capability-section" aria-labelledby="capability-title">
        <div className="section-heading"><div><span className="eyebrow">Phase 0</span><h2 id="capability-title">Data capability matrix</h2></div>
          <p>Killed screens are a successful research outcome, not a pipeline error.</p></div>
        <div className="capability-list">
          {(data?.capabilities || []).map((row) => <article className="capability-row" key={row.capability}>
            <div className="capability-name"><StatusMark available={row.available} verdict={row.verdict} /><h3>{row.capability}</h3><p>{row.provider}</p></div>
            <div><span>Granularity</span><strong>{row.granularity}</strong></div>
            <div><span>Freshness</span><strong>{row.freshness}</strong></div>
            <div className="capability-verdict"><span>Verdict</span><strong>{titleCase(row.verdict)}</strong></div>
          </article>)}
        </div>
      </section>

      <aside className="research-guardrail" aria-label="Research guardrail"><div><span>Language guardrail</span><strong>Possible support zone · confirmation pending · failed reversal</strong></div><p>No trade execution, profit promise, “bottom,” or positive classifier is emitted from unavailable data.</p></aside>
      <p className="disclaimer">{data?.disclaimer} Schema {data?.schema_version} · model {data?.model_version}.</p>
    </>}
  </>
}
