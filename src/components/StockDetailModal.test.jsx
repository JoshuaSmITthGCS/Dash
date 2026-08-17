import { mergeResearchStock, themeExposureName, themeExposureScore } from './StockDetailModal.jsx'

describe('theme exposure entries', () => {
  const published = {
    theme_id: 'ai_infrastructure', display_name: 'AI Infrastructure Buildout',
    theme_exposure_score: 74, opportunity_score: 71, eligible: true,
  }

  it('reads the name and score the pipeline publishes', () => {
    expect(themeExposureName(published)).toBe('AI Infrastructure Buildout')
    expect(themeExposureScore(published)).toBe(74)
  })

  it('still reads snapshots saved under the older spellings', () => {
    expect(themeExposureName({ theme: 'AI', score: 60 })).toBe('AI')
    expect(themeExposureScore({ theme: 'AI', score: 60 })).toBe(60)
  })

  it('reports an absent score as not-a-number rather than zero exposure', () => {
    expect(Number.isFinite(themeExposureScore({ theme_id: 'x' }))).toBe(false)
  })
})

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
