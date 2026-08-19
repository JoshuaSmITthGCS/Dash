import ProjectionFanChart from './ProjectionFanChart.jsx'
import InfoTag from './InfoTag.jsx'
import { formatAnnualReturnTarget } from '../lib/projectionEngine.js'

const percentileRows = [
  ['p10', '10th'],
  ['p25', '25th'],
  ['p50', 'Median'],
  ['p75', '75th'],
  ['p90', '90th'],
]

export default function ProjectionPanel({ state, source, money, annualReturnTargetPct, startAge = null, retirementAge = null, endAge = null, title = 'Range of simulated outcomes', assumptionNote = '', showSuccess = true }) {
  if (!source?.available) return <section className="projection-panel unavailable-panel">
    <strong>Projection unavailable</strong>
    <p>{source?.reason || 'Historical monthly returns are not available for this model.'}</p>
  </section>

  if (state.loading && !state.result) return <section className="projection-panel projection-loading" role="status">
    <span className="eyebrow">Historical simulation</span>
    <h2>{title}</h2>
    <p>Running 5,000 market paths off the main screen thread…</p>
  </section>

  if (state.error || !state.result?.available) return <section className="projection-panel unavailable-panel">
    <strong>Projection unavailable</strong>
    <p>{state.error || state.result?.reason || 'The historical simulation could not be completed.'}</p>
  </section>

  const result = state.result
  const hasWithdrawalPhase = result.withdrawalMonths > 0
  const displayedPercentiles = result.terminalPercentiles
  const terminalLabel = endAge != null ? `Ending balance at age ${endAge}` : retirementAge != null ? `Balance at age ${retirementAge}` : 'Terminal balance'
  const successPct = result.successProbability == null ? null : result.successProbability * 100
  const targetEvidence = source.baseline?.returnTargetEvidence

  return <section className="projection-panel" aria-labelledby="projection-panel-title">
    <header>
      <div><span className="eyebrow">Historical simulation</span><h2 id="projection-panel-title">{title}
        <InfoTag label={title}>
          <strong>{title}</strong>
          <p>A Monte Carlo simulation: {result.pathCount.toLocaleString()} randomly resampled paths
            built from monthly returns ({source.label}), not a forecast of any single
            outcome. The fan chart shows the spread between the 10th and 90th percentile paths, with
            the median (50th percentile) as the dotted line. Wider spread means more uncertainty at
            that point in time. Simulated outcomes are not predictions - see "Model and data
            disclosure" below for exactly what went into this run.</p>
        </InfoTag>
      </h2></div>
      <span className="projection-path-count">{result.pathCount.toLocaleString()} paths</span>
    </header>
    {assumptionNote && <p className="projection-assumption">{assumptionNote}</p>}
    {annualReturnTargetPct != null && <div className="projection-baseline-readout"><span>Annual return target</span><strong>{formatAnnualReturnTarget(annualReturnTargetPct)}</strong><small>{targetEvidence ? `${targetEvidence.lowerLabel} ${targetEvidence.lowerPct.toFixed(2)}% to ${targetEvidence.upperLabel} ${targetEvidence.upperPct.toFixed(2)}%` : 'Adjustable center for the dotted median path'}</small></div>}
    {source.benchmarkBased && <aside className="projection-source-warning" role="note"><strong>Short portfolio history</strong><span>{source.fallbackReason}</span></aside>}
    {showSuccess && hasWithdrawalPhase && <div className="projection-success" aria-label={`Retirement success probability ${successPct.toFixed(0)} percent`}>
      <span>Probability savings last to age {endAge}</span>
      <strong>{successPct.toFixed(0)}%</strong>
      <small>Median at retirement {money(result.retirementPercentiles.p50)}</small>
    </div>}
    <ProjectionFanChart fan={result.fan} startAge={startAge} retirementAge={retirementAge} money={money} />
    <div className="projection-percentile-heading"><strong>{terminalLabel}</strong><span>Wider outcomes show more uncertainty</span></div>
    <div className="projection-percentiles">
      {percentileRows.map(([key, label]) => <div key={key} className={key === 'p50' ? 'median' : ''}><span>{label}</span><strong>{money(displayedPercentiles[key])}</strong></div>)}
    </div>
    {hasWithdrawalPhase && <aside className="sequence-risk-callout">
      <strong>Sequence risk</strong>
      <span>At age {endAge}, the median path ends at {money(result.terminalPercentiles.p50)} and the 10th-percentile path ends at {money(result.terminalPercentiles.p10)}.</span>
      <p>The order of returns matters as much as the average during withdrawals.</p>
    </aside>}
    <details className="projection-disclosure">
      <summary>Model and data disclosure</summary>
      <p>{result.model} using {source.label} from {source.startDate} to {source.endDate}. The model ran {result.pathCount.toLocaleString()} paths and samples returns in consecutive {result.blockMonths}-month blocks. Monthly outcomes are centered on your adjustable {formatAnnualReturnTarget(annualReturnTargetPct)} annual return target. {source.fallbackReason || 'Portfolio history cleared the configured three-year gate.'} Simulated outcomes are not predictions.</p>
    </details>
  </section>
}
