import { readFile, writeFile } from 'node:fs/promises'
import settings from '../pipeline/config/settings.json' with { type: 'json' }
import { factorRegression } from '../src/lib/factorAnalytics.js'

const factorPayload = JSON.parse(await readFile(new URL('../public/data/factors/french.json', import.meta.url), 'utf8'))
const configuredWeights = settings.factor_data.sample_portfolio_weights
const histories = await Promise.all(Object.entries(configuredWeights).map(async ([ticker, weight]) => {
  const payload = JSON.parse(await readFile(new URL(`../public/data/etf/${ticker}.json`, import.meta.url), 'utf8'))
  const monthEnds = new Map()
  for (const row of payload.price_series?.fund || []) {
    if (row.date && Number.isFinite(Number(row.adjusted_close))) {
      monthEnds.set(row.date.slice(0, 7), { date: row.date, value: Number(row.adjusted_close) })
    }
  }
  return { ticker, weight, monthEnds }
}))

const commonMonths = [...histories[0].monthEnds.keys()]
  .filter((month) => month >= settings.factor_data.sample_portfolio_start_month)
  .filter((month) => histories.every((history) => history.monthEnds.has(month)))
  .sort()
const starting = Object.fromEntries(histories.map((history) => [
  history.ticker,
  history.monthEnds.get(commonMonths[0]).value,
]))
const series = {
  dates: commonMonths.map((month) => histories[0].monthEnds.get(month).date),
  values: commonMonths.map((month) => histories.reduce((sum, history) => (
    sum + history.weight * history.monthEnds.get(month).value / starting[history.ticker]
  ), 0)),
}
const regression = factorRegression(series, factorPayload)
const report = {
  generated_at: new Date().toISOString(),
  sample_portfolio: {
    weights: configuredWeights,
    construction: 'Static starting weights applied to adjusted-close total-return histories. Weights drift with performance.',
    source: 'Committed ETF histories and the Kenneth R. French Data Library factor cache',
  },
  regression: {
    ...regression,
    alpha_interpretation: regression.alphaTStatistic != null && Math.abs(regression.alphaTStatistic) >= 2
      ? 'The alpha t-statistic clears 2 in absolute value, but it remains a historical estimate.'
      : 'The alpha t-statistic is under 2 in absolute value and means nothing statistically.',
  },
}

await writeFile(new URL('../pipeline/reports/factor_regression_sample.json', import.meta.url), `${JSON.stringify(report, null, 2)}\n`)
process.stdout.write(`${JSON.stringify(report, null, 2)}\n`)
if (!regression.available) process.exitCode = 1
