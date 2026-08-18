import { useState } from 'react'
import { availableScenarios, portfolioProjectedImpact, rankHoldingsByScenario } from '../lib/scenarioSensitivity.js'

const money = (value) => value == null ? '–' : `${value < 0 ? '-' : ''}$${Math.abs(value).toLocaleString('en-US', { maximumFractionDigits: 0 })}`
const pct = (value) => value == null ? '–' : `${value >= 0 ? '+' : ''}${value.toFixed(1)}%`

function ScenarioHoldingRow({ row }) {
  return (
    <li className={row.projectedReturnPct < 0 ? 'negative' : 'positive'}>
      <div>
        <strong>{row.ticker}</strong>
        <small>{row.sector ? row.sector.replace(/_/g, ' ') : 'Sector unclassified'} · beta {row.beta.toFixed(2)}</small>
      </div>
      <div className="scenario-holding-figures">
        <b>{pct(row.projectedReturnPct)}</b>
        <small>{money(row.projectedDollarImpact)}</small>
      </div>
    </li>
  )
}

function ScenarioHoldingList({ title, rows }) {
  if (!rows.length) return null
  return (
    <div className="scenario-holding-column">
      <h3>{title}</h3>
      <ul className="scenario-holding-list">
        {rows.map((row) => <ScenarioHoldingRow key={row.ticker} row={row} />)}
      </ul>
    </div>
  )
}

/**
 * "If the bubble popped, which of my holdings would take the hit?"
 *
 * Reuses two things already published rather than computing anything new: each holding's own
 * market beta (report.json's technical_detail.beta) and the real market move each named
 * scenario produced (pipeline/stress_scenarios.py, published in signal_metrics.json). A beta
 * times a market move is a linear estimate of systematic exposure, not a forecast of what any
 * one holding will actually do -- it says nothing about news specific to that company.
 */
export default function ScenarioSensitivityPanel({ holdings, signalMetrics }) {
  const scenarios = availableScenarios(signalMetrics)
  const [selectedId, setSelectedId] = useState(null)
  const scenario = scenarios.find((row) => row.id === selectedId) || scenarios[0]

  if (!scenarios.length) {
    return (
      <section className="card etf-state scenario-sensitivity-empty" role="status">
        <strong>Scenario sensitivity unavailable</strong>
        <span>Run <code>python pipeline/signal_metrics.py</code> to publish the scenario projections this reads.</span>
      </section>
    )
  }

  const ranked = rankHoldingsByScenario(holdings?.portfolioPositions, scenario.marketReturnPct)
  if (!ranked.length) {
    return (
      <section className="card etf-state scenario-sensitivity-empty" role="status">
        <strong>No holding has a measured beta yet</strong>
        <span>Beta publishes once a holding's research row has enough price history -- add holdings or wait for the next research refresh.</span>
      </section>
    )
  }

  const portfolioImpact = portfolioProjectedImpact(ranked)
  const mostExposed = ranked.slice(0, 5)
  const leastExposed = ranked.length > 5 ? ranked.slice(-5).reverse() : []

  return (
    <section className="scenario-sensitivity" aria-labelledby="scenario-sensitivity-title">
      <header className="section-heading">
        <div>
          <span className="eyebrow">If it happened again</span>
          <h2 id="scenario-sensitivity-title">Which holdings would take the hit?</h2>
          <p>{scenario.description} Projected through each holding's own measured market beta -- a linear estimate, not a guarantee.</p>
        </div>
      </header>

      <div className="scenario-picker" role="tablist" aria-label="Scenario">
        {scenarios.map((row) => (
          <button
            key={row.id}
            type="button"
            role="tab"
            aria-selected={row.id === scenario.id}
            className={row.id === scenario.id ? 'active' : ''}
            onClick={() => setSelectedId(row.id)}
          >
            {row.label}
          </button>
        ))}
      </div>

      {portfolioImpact && (
        <div className="scenario-portfolio-impact">
          <span className="eyebrow">Whole portfolio, value-weighted</span>
          <strong className={portfolioImpact.weightedReturnPct < 0 ? 'negative' : 'positive'}>
            {pct(portfolioImpact.weightedReturnPct)}
          </strong>
          <small>{money(portfolioImpact.totalDollarImpact)} across {portfolioImpact.positionsIncluded} priced holding{portfolioImpact.positionsIncluded === 1 ? '' : 's'}</small>
        </div>
      )}

      <div className="scenario-holding-columns">
        <ScenarioHoldingList title="Most exposed" rows={mostExposed} />
        <ScenarioHoldingList title="Least exposed" rows={leastExposed} />
      </div>
    </section>
  )
}
