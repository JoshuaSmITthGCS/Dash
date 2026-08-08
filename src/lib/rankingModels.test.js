import { describe, expect, it } from 'vitest'
import {
  RANKING_MODELS, buildPeerIndex, isRankingModel, modelCoverage, modelReason, moderationScore,
  peerPercentile, rankByModel, scoreRow, thesisBreak,
} from './rankingModels'
import { modeConfidence } from './modeConfidence'

const row = (ticker, overrides = {}) => ({
  ticker,
  sector: 'Technology',
  industry: 'Semiconductors',
  components: { fundamentals: 70 },
  fundamental_categories: { valuation: 70 },
  fundamental_detail: { coverage: 0.9 },
  sector_valuation_percentile: 70,
  technical_detail: {
    return_5d: 2, return_20d: 6, return_60d: 10, return_252d: 30,
    momentum_12_1: 70, momentum_12_1_pct: 25, relative_strength_20d: 3,
    volume_confirmation: 60, risk_adjusted: 65, drawdown_60d: -10,
    pct_from_52w_high: -8,
  },
  analyst_count: 12,
  analyst_rating: 2.0,
  analyst_target_upside: 15,
  operating_margin: 0.2,
  operating_margin_trend: 0.03,
  free_cash_flow_yield: 0.05,
  interest_coverage: 9,
  revenue_growth: 0.12,
  net_buyback_yield: 0.02,
  fcf_growth_3y: 0.1,
  ...overrides,
})

const withEvidence = (ticker, evidenceSummary, overrides = {}) => row(ticker, {
  evidence_summary: { event_count: 1, ...evidenceSummary },
  ...overrides,
})

describe('peer-relative normalization', () => {
  it('ranks a company against its own industry when the sample supports it', () => {
    const peers = Array.from({ length: 10 }, (_, i) => row(`P${i}`, { operating_margin: i / 100 }))
    const index = buildPeerIndex(peers)

    const best = peerPercentile(index, peers[9], (r) => r.operating_margin)

    expect(best.level).toBe('industry')
    expect(best.value).toBeGreaterThan(90)
  })

  it('falls back to a wider group rather than ranking against two peers', () => {
    // A three-name industry is noise dressed as precision.
    const tiny = [
      row('A', { industry: 'Tiny', operating_margin: 0.1 }),
      row('B', { industry: 'Tiny', operating_margin: 0.2 }),
      ...Array.from({ length: 10 }, (_, i) => row(`S${i}`, { industry: 'Other', operating_margin: i / 50 })),
    ]
    const index = buildPeerIndex(tiny)

    expect(peerPercentile(index, tiny[0], (r) => r.operating_margin).level).toBe('sector')
  })

  it('inverts the rank when lower is better', () => {
    const peers = Array.from({ length: 10 }, (_, i) => row(`P${i}`, { debt_to_equity: i }))
    const index = buildPeerIndex(peers)

    const leastLevered = peerPercentile(index, peers[0], (r) => r.debt_to_equity, { higherIsBetter: false })

    expect(leastLevered.value).toBeGreaterThan(90)
  })

  it('scores both extremes down on a two-tailed metric', () => {
    const peers = Array.from({ length: 11 }, (_, i) => row(`P${i}`, { asset_growth: i / 10 }))
    const index = buildPeerIndex(peers)
    const read = (r) => r.asset_growth

    expect(moderationScore(index, peers[5], read).value).toBeGreaterThan(moderationScore(index, peers[0], read).value)
    expect(moderationScore(index, peers[5], read).value).toBeGreaterThan(moderationScore(index, peers[10], read).value)
  })

  it('returns null rather than a middling 50 when there is no usable sample', () => {
    const index = buildPeerIndex([row('ONLY', { operating_margin: 0.3 })])

    expect(peerPercentile(index, index.rows[0], (r) => r.operating_margin)).toBeNull()
  })
})

describe('inapplicable components are dropped, not zeroed', () => {
  it('renormalizes over the components that applied', () => {
    // An insurer reports no free-cash-flow yield or interest coverage in this shape. Scoring
    // those as zero would rank it down for the shape of its balance sheet.
    const insurer = row('AIG', {
      industry: 'Insurance', free_cash_flow_yield: null, interest_coverage: null,
    })
    const peers = [insurer, ...Array.from({ length: 9 }, (_, i) => row(`P${i}`, { industry: 'Insurance' }))]
    const index = buildPeerIndex(peers)

    const scored = scoreRow(index, insurer, 'fundamentals')

    expect(scored.droppedComponents.map((item) => item.key)).toContain('cash_quality')
    expect(scored.coverage).toBeLessThan(1)
    expect(scored.raw).toBeGreaterThan(0)
    expect(scored.components.reduce((sum, item) => sum + item.contribution, 0)).toBeCloseTo(100, 0)
  })

  it('a company missing a metric is not ranked below one that reports it badly', () => {
    const peers = Array.from({ length: 9 }, (_, i) => row(`P${i}`, { operating_margin: 0.1 + i / 100 }))
    const missing = row('MISSING', { operating_margin: null })
    const terrible = row('TERRIBLE', { operating_margin: -0.5 })
    const index = buildPeerIndex([...peers, missing, terrible])

    expect(scoreRow(index, missing, 'fundamentals').raw)
      .toBeGreaterThan(scoreRow(index, terrible, 'fundamentals').raw)
  })
})

describe('confidence shrinks every model score', () => {
  it('pulls a high raw score toward neutral when the evidence behind it is thin', () => {
    const thin = withEvidence('THIN', { news_score: 95, dominant_age_trading_days: 0 })
    delete thin.estimate_detail
    const index = buildPeerIndex([thin])

    const scored = scoreRow(index, thin, 'catalyst')

    expect(scored.raw).toBeGreaterThan(80)
    expect(scored.score).toBeLessThan(scored.raw)
    expect(scored.confidence).toBeLessThan(1)
  })

  it('leaves a well-evidenced score close to its raw value', () => {
    const solid = withEvidence('SOLID', {
      news_score: 90, dominant_age_trading_days: 0,
      insider_score: 85, insider_freshest_age_trading_days: 2,
      expectation_score: 80, expectation_inputs_resolved: 3,
    })
    const index = buildPeerIndex([solid])

    const scored = scoreRow(index, solid, 'catalyst')

    expect(scored.confidence).toBeGreaterThan(0.9)
    expect(Math.abs(scored.score - scored.raw)).toBeLessThan(6)
  })

  it('a thin 95 cannot outrank a well-evidenced 80', () => {
    const thin = withEvidence('THIN', { news_score: 99, dominant_age_trading_days: 0 })
    const solid = withEvidence('SOLID', {
      news_score: 78, dominant_age_trading_days: 0,
      insider_score: 80, insider_freshest_age_trading_days: 1,
      expectation_score: 76, expectation_inputs_resolved: 3,
    })

    const ranked = rankByModel([thin, solid], 'catalyst', 20)

    expect(ranked[0].ticker).toBe('SOLID')
  })
})

describe('mode-specific confidence', () => {
  it('reads high on momentum and low on long-term research for the same row', () => {
    // Flawless price history, no resolved accounting - the case a single global confidence
    // number describes wrongly in both directions.
    const priceOnly = row('VRT', {
      components: {}, fundamental_detail: null, sector_valuation_percentile: null,
      free_cash_flow: null, return_on_equity: null, analyst_count: 0,
    })

    expect(modeConfidence(priceOnly, 'momentum').percent).toBeGreaterThan(80)
    expect(modeConfidence(priceOnly, 'research').percent).toBeLessThan(40)
  })

  it('names the weakest inputs so a low number can be explained', () => {
    const noEvidence = row('QUIET')

    const confidence = modeConfidence(noEvidence, 'catalyst')

    expect(confidence.percent).toBeLessThan(30)
    expect(confidence.weakest.map((item) => item.label)).toContain('news events')
  })

  it('discounts a stale catalyst even though the field is populated', () => {
    const fresh = withEvidence('FRESH', { news_score: 80, dominant_age_trading_days: 0 })
    const stale = withEvidence('STALE', { news_score: 80, dominant_age_trading_days: 40 })

    expect(modeConfidence(fresh, 'catalyst').percent)
      .toBeGreaterThan(modeConfidence(stale, 'catalyst').percent)
  })
})

describe('reversal thesis-break gate', () => {
  const falling = (overrides) => row('FALL', {
    technical_detail: {
      return_5d: 3, return_20d: -15, drawdown_60d: -28, pct_from_52w_high: -30,
    },
    ...overrides,
  })

  it('caps a bounce that follows negative guidance news', () => {
    const knife = falling({
      evidence_summary: {
        event_count: 1, news_score: 12,
        dominant_event: 'Company cuts FY guidance 25%', dominant_event_types: ['guidance'],
      },
    })
    const clean = falling({
      evidence_summary: { event_count: 1, news_score: 55, dominant_event_types: ['product'] },
    })
    const index = buildPeerIndex([knife, clean])

    const capped = scoreRow(index, knife, 'reversal')
    const uncapped = scoreRow(index, clean, 'reversal')

    expect(capped.cap.reason).toMatch(/guidance/)
    expect(capped.raw).toBeLessThanOrEqual(45)
    expect(uncapped.raw).toBeGreaterThan(capped.raw)
  })

  it('does not treat a guidance RAISE as a broken thesis', () => {
    const raised = falling({
      evidence_summary: { event_count: 1, news_score: 88, dominant_event_types: ['guidance'] },
    })

    expect(thesisBreak(raised)).toBeNull()
  })

  it('keeps the capped name visible with its reason rather than deleting it', () => {
    const knife = falling({
      evidence_summary: { event_count: 1, news_score: 10, dominant_event_types: ['restatement'] },
    })

    const ranked = rankByModel([knife], 'reversal', 20)

    expect(ranked).toHaveLength(1)
    expect(ranked[0].modelScore.cap.reason).toMatch(/restatement/)
  })

  it('refuses a bounce on a business below the fundamentals floor', () => {
    const deteriorating = falling({ components: { fundamentals: 30 } })
    const index = buildPeerIndex([deteriorating])

    expect(scoreRow(index, deteriorating, 'reversal')).toBeNull()
  })
})

describe('analyst conviction reads change, not level', () => {
  it('ranks a rising-estimate name above a higher-consensus static one', () => {
    const revising = row('REVISING', {
      analyst_rating: 2.4, analyst_target_upside: 8,
      estimate_detail: { revision_breadth_30d: 0.8, eps_revision_30d_pct: 0.14, net_upgrades_90d: 3 },
    })
    const static_ = row('STATIC', {
      analyst_rating: 1.4, analyst_target_upside: 10, estimate_detail: {},
    })

    const ranked = rankByModel([revising, static_], 'analystConviction', 20)

    expect(ranked[0].ticker).toBe('REVISING')
  })

  it('still requires three analysts before saying anything', () => {
    const index = buildPeerIndex([row('THIN', { analyst_count: 2 })])

    expect(scoreRow(index, index.rows[0], 'analystConviction')).toBeNull()
  })
})

describe('peer read-through refuses the weakest company in a hot industry', () => {
  const connected = (overrides) => row('CONN', {
    theme_exposure: [{ display_name: 'AI', theme_exposure_score: 90, opportunity_score: 80, eligible: true }],
    ...overrides,
  })

  it('excludes a name whose own expectations are being revised down', () => {
    const sinking = connected({ evidence_summary: { event_count: 1, expectation_score: 20 } })
    const index = buildPeerIndex([sinking])

    expect(scoreRow(index, sinking, 'tailwind')).toBeNull()
  })

  it('excludes a name whose own recent material news is negative', () => {
    const bad = connected({ evidence_summary: { event_count: 1, news_score: 20 } })
    const index = buildPeerIndex([bad])

    expect(scoreRow(index, bad, 'tailwind')).toBeNull()
  })

  it('rewards the laggard, not the name that already ran', () => {
    const lagging = connected({
      ticker: 'LAG', technical_detail: { ...row('x').technical_detail, relative_strength_20d: -8 },
    })
    const alreadyRan = connected({
      ticker: 'RAN', technical_detail: { ...row('x').technical_detail, relative_strength_20d: 18 },
    })

    const ranked = rankByModel([lagging, alreadyRan], 'tailwind', 20)

    expect(ranked[0].ticker).toBe('LAG')
  })
})

describe('catalyst model', () => {
  it('excludes a row with no dated evidence at all', () => {
    const index = buildPeerIndex([row('QUIET')])

    expect(scoreRow(index, index.rows[0], 'catalyst')).toBeNull()
  })

  it('excludes evidence that resolved but says nothing directional', () => {
    const neutral = withEvidence('NEUTRAL', { news_score: 51, insider_score: 50 })
    const index = buildPeerIndex([neutral])

    expect(scoreRow(index, neutral, 'catalyst')).toBeNull()
  })

  it('lets a weak long-term score rank top on a genuine catalyst', () => {
    const mediocre = withEvidence('MEDIOCRE', {
      news_score: 92, dominant_age_trading_days: 0,
      insider_score: 80, insider_freshest_age_trading_days: 2,
      expectation_score: 78, expectation_inputs_resolved: 3,
    }, { components: { fundamentals: 40 }, sector_valuation_percentile: 20 })
    const compounder = row('COMPOUNDER', { components: { fundamentals: 95 } })

    const ranked = rankByModel([mediocre, compounder], 'catalyst', 20)

    expect(ranked.map((item) => item.ticker)).toEqual(['MEDIOCRE'])
  })
})

describe('model coverage', () => {
  it('counts why each excluded row was excluded', () => {
    const rows = [
      row('OK', { technical_detail: { return_5d: 3, return_20d: -10, drawdown_60d: -20 } }),
      row('NODD', { technical_detail: { return_5d: 3, return_20d: -10 } }),
      row('NODD2', { technical_detail: { return_5d: 3, return_20d: -10 } }),
      row('UP', { technical_detail: { return_5d: 3, return_20d: 10, drawdown_60d: -5 } }),
    ]

    const coverage = modelCoverage(rows, 'reversal')

    expect(coverage.scanned).toBe(4)
    expect(coverage.qualified).toBe(1)
    expect(coverage.binding.reason).toMatch(/60-day drawdown/)
    expect(coverage.binding.count).toBe(2)
  })
})

describe('model registry', () => {
  it('exposes every model with declared weights that sum to one', () => {
    for (const [key, model] of Object.entries(RANKING_MODELS)) {
      const total = model.components.reduce((sum, [, , weight]) => sum + weight, 0)
      expect(total, key).toBeCloseTo(1, 5)
      expect(isRankingModel(key)).toBe(true)
      expect(model.question, key).toBeTruthy()
    }
  })

  it('never scores a fund under a per-security model', () => {
    const index = buildPeerIndex([row('VOO', { is_etf: true })])

    expect(scoreRow(index, { ...row('VOO'), is_etf: true }, 'fundamentals')).toBeNull()
  })

  it('states the strongest contributors as the reason', () => {
    const peers = Array.from({ length: 10 }, (_, i) => row(`P${i}`, { operating_margin: i / 50 }))
    const [top] = rankByModel(peers, 'fundamentals', 1)

    expect(modelReason(top)).toMatch(/\w+ \d+/)
  })

  it('scores nothing at all rather than guessing when there are no peers to rank against', () => {
    // A percentile over a sample of one is not a measurement.
    expect(rankByModel([row('ALONE')], 'fundamentals', 1)).toEqual([])
  })
})
