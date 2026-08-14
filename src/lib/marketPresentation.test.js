import { describe, expect, it } from 'vitest'
import { dailyMove, marketType, rankDailySectors, rankDailyStocks } from './marketPresentation.js'

const row = (ticker, sector, previous, current) => ({
  ticker,
  sector,
  history: { closes: [previous, current] },
})

describe('market presentation helpers', () => {
  it('prefers a live price and previous close when both are available', () => {
    expect(dailyMove({ price: 105, previousClose: 100, history: { closes: [90, 95] } })).toMatchObject({
      available: true,
      delta: 5,
      pct: 5,
    })
  })

  it('ranks stocks and sector averages by the latest daily move', () => {
    const rows = [
      row('AAA', 'Technology', 100, 110),
      row('BBB', 'Technology', 100, 102),
      row('CCC', 'Energy', 100, 96),
    ]
    expect(rankDailyStocks(rows).map((item) => item.ticker)).toEqual(['AAA', 'BBB', 'CCC'])
    expect(rankDailySectors(rows).map((item) => item.sector)).toEqual(['Technology', 'Energy'])
  })

  it('classifies clearly positive breadth as risk-on', () => {
    const rows = [row('A', 'Tech', 100, 103), row('B', 'Health', 100, 102), row('C', 'Energy', 100, 99)]
    expect(marketType(rows)).toMatchObject({ label: 'Risk-on session', tone: 'positive' })
  })
})
