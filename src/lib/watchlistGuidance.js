import { bullBearScore } from './bullBearScore'

function finite(value) {
  return typeof value === 'number' && Number.isFinite(value)
}

export function watchlistGuidance(stock, budget = null, maxPositionPct = 5) {
  if (!stock) return null
  const thesis = bullBearScore(stock)
  const technical = stock.technical_detail || {}
  const blockedAction = ['TRIM', 'SELL'].includes(stock.recommendation?.action)
  const buySetup = Boolean(
    thesis
    && thesis.score >= 5.5
    && stock.score >= 65
    && stock.confidence >= 0.5
    && technical.return_20d > 0
    && !blockedAction
  )

  const target = finite(stock.analyst_consensus_target)
    && stock.analyst_consensus_target > 0
    ? stock.analyst_consensus_target
    : null
  const analystCount = finite(stock.analyst_count) ? stock.analyst_count : null
  const validBudget = finite(budget) && budget > 0
  const validPct = finite(maxPositionPct) && maxPositionPct > 0
  const allocation = buySetup && validBudget && validPct
    ? budget * Math.min(maxPositionPct, 100) / 100
    : 0
  const shares = allocation > 0 && finite(stock.price) && stock.price > 0
    ? Math.floor((allocation / stock.price) * 1000) / 1000
    : 0

  return {
    verdict: buySetup ? 'BUY SETUP' : "DON'T BUY YET",
    buySetup,
    thesisScore: thesis?.score ?? null,
    target,
    analystCount,
    targetUpside: target && finite(stock.price) && stock.price > 0
      ? (target / stock.price - 1) * 100
      : null,
    allocation,
    shares,
  }
}

