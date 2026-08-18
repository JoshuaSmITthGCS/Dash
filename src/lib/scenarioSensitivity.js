// Ranks the user's own holdings by how hard a market-wide scenario would likely hit them,
// using each holding's own already-published market beta (report.json's
// technical_detail.beta) times the scenario's real -- or hypothetical -- market move. Same
// linear-projection method pipeline/stress_scenarios.py already uses at the strategy level,
// applied per holding instead. A beta times a market move is an estimate, not a measurement:
// it says nothing about idiosyncratic, company-specific risk.

const NAMED_SCENARIO_IDS = ['scenario_gfc_2008', 'scenario_covid_2020', 'scenario_rate_shock_2022']
// Deliberately excludes scenario_hypothetical_rates: this ranking projects each holding
// through its own *equity* beta (beta to SPY), and a rate shock is sized in basis points, not
// a percent market move -- there is no dimensionally sound way to run a stock's equity beta
// through a rate shock. The pipeline's rate-shock projection uses the whole book's beta to
// TLT instead, which is not published per holding; showing this scenario here would mean
// silently substituting the wrong beta for the question being asked.
const HYPOTHETICAL_SCENARIO_IDS = ['scenario_hypothetical_spy']

function describeScenario(row) {
  if (row.id === 'scenario_hypothetical_spy') {
    const shock = row.detail?.shock_pct
    return `A hypothetical ${shock >= 0 ? '+' : ''}${shock}% move in the S&P 500.`
  }
  return row.detail?.description || row.label
}

/** Every scenario signal_metrics.json published and is actually ready to project through. */
export function availableScenarios(signalMetrics) {
  const metrics = signalMetrics?.metrics || []
  return [...NAMED_SCENARIO_IDS, ...HYPOTHETICAL_SCENARIO_IDS]
    .map((id) => metrics.find((row) => row.id === id))
    .filter((row) => row && row.status === 'ready' && row.detail)
    .map((row) => ({
      id: row.id,
      label: row.label,
      isHypothetical: HYPOTHETICAL_SCENARIO_IDS.includes(row.id),
      marketReturnPct: row.detail.spy_return_pct ?? row.detail.shock_pct ?? null,
      detail: row.detail,
      description: describeScenario(row),
    }))
    .filter((row) => Number.isFinite(row.marketReturnPct))
}

/** Every priced holding with a measured beta, projected through one scenario's market
 * return and sorted worst (most negative) first -- "most exposed" at the top. */
export function rankHoldingsByScenario(positions, marketReturnPct) {
  if (!Number.isFinite(marketReturnPct)) return []
  return (positions || [])
    .map((position) => {
      const beta = position.priceInfo?.technical_detail?.beta
      if (!Number.isFinite(beta)) return null
      const projectedReturnPct = beta * marketReturnPct
      const projectedDollarImpact = Number.isFinite(position.currentValue)
        ? position.currentValue * (projectedReturnPct / 100)
        : null
      return {
        ticker: position.ticker,
        name: position.priceInfo?.name || position.ticker,
        sector: position.priceInfo?.sector || null,
        beta,
        allocationPct: position.allocationPct,
        currentValue: position.currentValue,
        projectedReturnPct,
        projectedDollarImpact,
      }
    })
    .filter(Boolean)
    .sort((a, b) => a.projectedReturnPct - b.projectedReturnPct)
}

/** Value-weighted portfolio-level read, from the same per-holding projections -- so the
 * headline number and the ranked list beneath it are provably the same arithmetic. */
export function portfolioProjectedImpact(ranked) {
  const priced = (ranked || []).filter((row) => Number.isFinite(row.currentValue) && row.currentValue > 0)
  const totalValue = priced.reduce((sum, row) => sum + row.currentValue, 0)
  if (!totalValue) return null
  const weightedReturnPct = priced.reduce(
    (sum, row) => sum + row.projectedReturnPct * (row.currentValue / totalValue), 0)
  const totalDollarImpact = priced.reduce((sum, row) => sum + (row.projectedDollarImpact || 0), 0)
  return { weightedReturnPct, totalDollarImpact, totalValue, positionsIncluded: priced.length }
}
