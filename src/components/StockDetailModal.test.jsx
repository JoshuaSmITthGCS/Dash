import { mergeResearchStock } from './StockDetailModal.jsx'

describe('mergeResearchStock', () => {
  it('adds deep research fields without replacing a newer route price', () => {
    const supplied = {
      ticker: 'AAPL', price: 210,
      analysis_v2: { structural: { effective_score: 80 } },
    }
    const fullResearch = {
      research: [{
        ticker: 'AAPL', price: 200, modifiers: { total: 2 }, explainability: { attribution: {} },
        analysis_v2: { structural: { effective_score: 79 }, timeliness: { effective_score: 62 } },
      }],
    }

    expect(mergeResearchStock(supplied, fullResearch)).toMatchObject({
      price: 210,
      modifiers: { total: 2 },
      explainability: { attribution: {} },
      analysis_v2: {
        structural: { effective_score: 80 },
        timeliness: { effective_score: 62 },
      },
    })
  })

  it('keeps a lightweight row unchanged when no deeper row exists', () => {
    const supplied = { ticker: 'NEW', price: 12 }
    expect(mergeResearchStock(supplied, { research: [] })).toBe(supplied)
  })
})
