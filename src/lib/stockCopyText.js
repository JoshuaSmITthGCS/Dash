import { resolvedMetricSections } from './resolvedMetricSections.js'
import { getRecommendation } from './recommendation.js'
import { watchlistGuidance } from './watchlistGuidance.js'

// One-button plain-text export of everything the stock detail sheet actually shows for a
// company: identity, score, guidance, theme exposure, setup quality, factor bars, KPIs, the
// shadow policy comparison, the independent business-thesis/timeliness layers, every resolved
// metric section (same filtering resolvedMetricSections applies to the live panel, so this can
// never show a number the screen itself withheld), the exact score reconciliation and
// metric-level evidence, the section radar, score components, fundamental categories, evidence
// for/against, score modifiers, insider Form 4 activity, disclosed Congressional/institutional
// positioning when published for this ticker, and applicability/data-quality exceptions. Meant
// to be pasted somewhere else entirely - a note, a spreadsheet, another tool - so it reads as
// plain lines, not markup.

const signed = (value, digits = 1) => `${value >= 0 ? '+' : ''}${value.toFixed(digits)}%`
const signedPoints = (value) => `${value >= 0 ? '+' : '−'}${Math.abs(value).toFixed(1)}`
const title = (value = '') => String(value)
  .replace(/_/g, ' ')
  .replace(/\b\w/g, (letter) => letter.toUpperCase())
const pctFmt = (value) => (value == null ? '–' : `${Math.round(value * 100)}%`)
const scoreFmt = (value) => (Number.isFinite(value) ? Math.round(value) : '–')

function ordinal(value) {
  const rounded = Math.round(value)
  const remainder = rounded % 100
  if (remainder >= 11 && remainder <= 13) return `${rounded}th`
  return `${rounded}${{ 1: 'st', 2: 'nd', 3: 'rd' }[rounded % 10] || 'th'}`
}

function rawMetricValue(metric) {
  if (metric.raw_value == null) return 'unavailable'
  if (metric.format === 'percent') return `${(metric.raw_value * 100).toFixed(1)}%`
  if (metric.format === 'multiple') return `${Number(metric.raw_value).toFixed(1)}x`
  return Number(metric.raw_value).toFixed(2)
}

// `theme_exposure` rows are published as {theme_id, display_name, theme_exposure_score, ...};
// the older `exposure_score`/`score` spellings are kept as fallbacks for saved snapshots. Kept
// as a local copy rather than a shared import - see StockDetailSheet.jsx's identical note on
// why these small pure helpers are replicated per call site instead of centralized.
const themeExposureScore = (entry) =>
  Number(entry?.theme_exposure_score ?? entry?.exposure_score ?? entry?.score)
const themeExposureName = (entry) =>
  entry?.display_name || entry?.theme_id || entry?.theme || entry?.name

function primaryTheme(stock) {
  const themes = Array.isArray(stock.theme_exposure) ? stock.theme_exposure : []
  if (!themes.length) return null
  return themes.slice().sort((left, right) =>
    (themeExposureScore(right) || 0) - (themeExposureScore(left) || 0))[0]
}

function layerDetail(layer) {
  if (!layer || layer.effective_score == null) {
    return layer?.unavailable_reason || 'No inputs resolved, so no score is published'
  }
  return `${scoreFmt(layer.effective_score)} effective · ${pctFmt(layer.evidence_weight_resolved)} of evidence weight resolved`
}

function headerLines(stock) {
  const lines = [`${stock.ticker} — ${stock.name || 'Name unavailable'}`]
  const place = [stock.industry || stock.sector, stock.sector && stock.industry ? stock.sector : null]
    .filter(Boolean).join(' · ')
  if (place) lines.push(place)
  const dataAsOf = stock.generated_at || stock.recommendation_v2?.generated_at
  if (dataAsOf) lines.push(`As of ${String(dataAsOf).slice(0, 10)}`)
  const score = stock.score
  lines.push(score == null
    ? 'Research score: not published'
    : `Research score: ${Math.round(score)}${stock.stance ? ` (${stock.stance})` : ''}`)
  if (typeof stock.data_coverage === 'number' && Number.isFinite(stock.data_coverage)) {
    lines.push(`Data coverage: ${Math.round(stock.data_coverage * 100)}%`)
  }
  return lines
}

function guidanceLines(recommendation) {
  if (!recommendation) return []
  const lines = ['', 'GUIDANCE',
    `  ${recommendation.action || 'WATCH'}${recommendation.suggestedTrimPct > 0 ? ` ${recommendation.suggestedTrimPct}%` : ''}`]
  if (recommendation.summary) lines.push(`  ${recommendation.summary}`)
  if (recommendation.reasons?.length) lines.push(...recommendation.reasons.map((reason) => `  - ${reason}`))
  return lines
}

function themeLines(stock) {
  const theme = primaryTheme(stock)
  const themeName = themeExposureName(theme) || 'No material theme identified'
  const themeScore = theme ? themeExposureScore(theme) : undefined
  const otherThemes = (Array.isArray(stock.theme_exposure) ? stock.theme_exposure : [])
    .filter((entry) => entry !== theme && Number.isFinite(themeExposureScore(entry)))
  const detail = !Number.isFinite(themeScore)
    ? 'No material long-term theme exposure is published for this company.'
    : `${themeScore.toFixed(0)} out of 100. Theme exposure stays independent from the research score.`
  return ['', 'THEME EXPOSURE', `  ${themeName}`,
    `  ${detail}${otherThemes.length ? ` Also exposed to ${otherThemes.map(themeExposureName).join(', ')}.` : ''}`]
}

function setupQualityLines(stock) {
  const guidance = watchlistGuidance(stock, null, null, {})
  if (!guidance) return []
  const lines = ['', 'SETUP QUALITY', `  ${guidance.setupLabel}: ${guidance.setupScore}/100`]
  guidance.subscores.forEach((item) => lines.push(`    ${item.label}: ${Math.round(item.value * 100)}`))
  if (guidance.hardBlocked) lines.push(`  ${guidance.hardBlockReasons.join('. ')}.`)
  return lines
}

function factorBarLines(stock) {
  const bars = stock.explainability?.factor_bars
  if (!bars || !Object.keys(bars).length) return []
  const lines = ['', 'FACTOR SUMMARY']
  Object.entries(bars).forEach(([key, value]) => lines.push(`  ${key}: ${value == null ? 'N/A' : Math.round(value)}`))
  return lines
}

function kpiLines(stock) {
  const technical = stock.technical_detail || {}
  const lines = []
  if (stock.price) lines.push(`Price: $${Number(stock.price).toFixed(2)}`)
  if (stock.market_cap) lines.push(`Market cap: $${(stock.market_cap / 1e9).toFixed(1)}B`)
  if (typeof technical.return_20d === 'number') lines.push(`20-day move: ${signed(technical.return_20d)}`)
  if (typeof technical.return_252d === 'number') lines.push(`1-year move: ${signed(technical.return_252d)}`)
  if (typeof stock.earnings_surprise === 'number') lines.push(`Earnings vs. estimate: ${signed(stock.earnings_surprise)}`)
  return lines
}

function policyComparisonLines(stock, legacy) {
  const shadow = stock.recommendation_v2
  if (!shadow) return []
  const company = shadow.company?.action || {}
  const position = shadow.position_action || {}
  const structural = shadow.company_structural_state || shadow.company?.structural || {}
  const timeliness = shadow.company_timeliness_state || shadow.company?.timeliness || {}
  const portfolio = shadow.portfolio_fit_state || shadow.portfolio_fit || {}
  const ruleState = shadow.position_rule_state || {}
  const dataQuality = shadow.data_quality || {}
  const flagged = (shadow.company?.deterioration_groups || []).filter((group) => group.flagged)
  const lines = ['', `POLICY COMPARISON (shadow · ${shadow.model_version || 'unversioned'})`]
  lines.push(`  Active legacy policy: ${legacy?.action || 'Unavailable'}${legacy?.suggestedTrimPct ? ` ${legacy.suggestedTrimPct}%` : ''}`)
  lines.push(`  Shadow company action: ${title(company.label)}`)
  lines.push(`  Shadow position action: ${title(position.label)}${position.trim_percent > 0 ? ` ${Math.round(position.trim_percent * 100)}%` : ''}`)
  lines.push(`  Structural: ${title(structural.classification || 'unavailable')} (${layerDetail(structural)})`)
  lines.push(`  Timeliness: ${title(timeliness.classification || 'unavailable')} (${layerDetail(timeliness)})`)
  lines.push(`  Portfolio fit: ${portfolio.current_weight ? title(portfolio.classification) : 'Not assessed'}`)
  lines.push(`  Position rules: ${title(ruleState.classification || 'unavailable')}${ruleState.profile ? ` (profile: ${title(ruleState.profile)})` : ''}`)
  lines.push(`  Company evidence: ${pctFmt(dataQuality.evidence_weight_resolved)} of evidence weight resolved · ${pctFmt(dataQuality.data_coverage)} data coverage`)
  lines.push(`  ${flagged.length} of 3 independent deterioration groups flagged`)
  const reasons = [...(company.reason_codes || []), ...(position.reason_codes || [])]
    .filter((reason, index, all) => all.indexOf(reason) === index)
  if (reasons.length) lines.push(...reasons.map((reason) => `  - ${title(reason)}`))
  return lines
}

function analysisLayerLines(label, layer, description) {
  if (!layer) return []
  const lines = [`  ${label.toUpperCase()}`]
  if (layer.effective_score == null) {
    lines.push(`    Not measured: ${layer.unavailable_reason || 'This layer has no resolved inputs, so no score is published for it.'}`)
    return lines
  }
  lines.push(`    ${Math.round(layer.effective_score)} (${String(layer.classification).replace(/_/g, ' ')}) — ${description}`)
  lines.push(`    Raw: ${layer.raw_score == null ? 'Unavailable' : Math.round(layer.raw_score)} · Data coverage: ${Math.round((layer.coverage || 0) * 100)}% · Evidence weight resolved: ${Math.round((layer.evidence_weight_resolved || 0) * 100)}%`)
  if (layer.evidence_weight_resolved < 0.4) lines.push('    Insufficient evidence: this layer cannot issue prescriptive company guidance.')
  return lines
}

function businessThesisLines(stock) {
  const analysis = stock.analysis_v2
  if (!analysis) return []
  return ['', 'BUSINESS THESIS (independent decision layers)',
    ...analysisLayerLines('Business thesis', analysis.structural, 'Structural quality and valuation. Position stops do not change this result.'),
    ...analysisLayerLines('Earnings timeliness', analysis.timeliness, 'Forward estimates, revisions, surprises, and guidance – separate from trailing growth.'),
  ]
}

function peerValuationLines(stock) {
  const percentile = stock.valuation_percentile
  if (!percentile) return []
  if (percentile.peer_context) {
    return ['', `Valuation score ${percentile.peer_context.tier_phrase} ${percentile.peer_group_label} (${percentile.peer_context.tier_count} of ${percentile.peer_context.peer_count_with_valid_data} names). Ranks this model's valuation composite, not a price multiple.`]
  }
  return ['', `No peer comparison published: ${percentile.peer_count_with_valid_data} valid ${percentile.peer_group_label} peers, below the ${percentile.minimum_peer_count} needed to rank against.`]
}

function metricSectionLines(stock) {
  const rendered = resolvedMetricSections(stock)
  if (!rendered.length) return []
  const lines = ['', 'METRICS']
  rendered.forEach((section) => {
    lines.push('', section.title.toUpperCase())
    if (section.note) lines.push(`  ${section.note}`)
    section.resolved.forEach((metric) => {
      lines.push(`  ${metric.label}: ${metric.format(metric.value)}`)
      if (metric.why) lines.push(`    ${metric.why}`)
    })
  })
  return lines
}

function reconciliationLines(stock) {
  const explainability = stock.explainability
  if (!explainability) return []
  const variant = explainability.active_variant || 'champion'
  const attribution = explainability.attribution?.[variant]
  const lines = []
  if (attribution) {
    lines.push('', `EXACT RECONCILIATION (why the ${variant} score is ${attribution.final_score?.toFixed(1) ?? 'unavailable'})`)
    if (typeof attribution.final_score === 'number' && typeof stock.score === 'number'
      && Math.abs(attribution.final_score - stock.score) >= 0.05) {
      const divergence = attribution.final_score - stock.score
      lines.push(`  This reconciles the ${variant} variant, not the published score of ${stock.score.toFixed(1)} — a difference of ${divergence > 0 ? '+' : ''}${divergence.toFixed(1)} points.`)
    }
    lines.push(`  Start from neutral: ${attribution.base?.toFixed(1) ?? '–'}`)
    const evidenceLines = [
      ...(attribution.evidence || []),
      { key: 'confidence', label: 'confidence shrinkage', points: attribution.confidence_shrinkage_points },
      ...(attribution.modifiers || []),
    ].filter((line) => line.key !== 'score_rounding' || Math.abs(line.points || 0) >= 0.01)
    evidenceLines.forEach((line) => lines.push(`  ${line.label}: ${signedPoints(line.points || 0)}`))
    lines.push(`  Final score: ${attribution.final_score?.toFixed(1) ?? '–'}`)
  }

  const metrics = explainability.metrics?.[variant] || []
  if (metrics.length) {
    lines.push('', 'METRIC-LEVEL EVIDENCE')
    metrics.forEach((metric) => {
      const peer = metric.sector_percentile == null
        ? 'peer percentile is accumulating'
        : `${ordinal(metric.sector_percentile)} percentile in ${metric.normalization_scope === 'sector' ? (stock.sector || 'its sector') : 'the full universe'}`
      let peerMeaning = ''
      if (metric.sector_percentile != null && metric.direction === 'lower_is_better') {
        peerMeaning = metric.sector_percentile >= 50 ? ', so expensive relative to peers' : ', so cheap relative to peers'
      }
      const own = !metric.own_history_status
        ? 'own-history comparison does not apply'
        : metric.own_history_percentile == null
          ? `${metric.own_history_observations || 0} own-history observations accumulated`
          : `${ordinal(metric.own_history_percentile)} percentile versus its own ${metric.own_history_years}-year history`
      lines.push(`  ${metric.label} ${rawMetricValue(metric)}, ${peer}${peerMeaning}, ${own}, worth ${signedPoints(metric.final_point_contribution)} points.`)
    })
  }

  const history = explainability.score_history
  if (history) {
    lines.push('', 'SCORE HISTORY')
    const points = (history.points || []).filter((point) => Number.isFinite(point.champion_score))
    if (history.status === 'available' && points.length >= 2) {
      const driver = history.largest_category_driver
      lines.push(`  Score moved from ${points[0].champion_score.toFixed(0)} to ${points.at(-1).champion_score.toFixed(0)}${driver ? `, driven mainly by ${driver.category.replace(/_/g, ' ')}` : ''}.`)
    } else {
      lines.push(`  Accumulating: ${history.stored_months || 0} of ${history.required_months || 6} stored months.`)
    }
  }

  if (explainability.anomalies?.length) {
    lines.push('', 'DIVERGENCE FLAGS')
    explainability.anomalies.forEach((flag) => lines.push(`  ${flag.message}`))
  }

  return lines
}

function sectionRadarLines(stock) {
  const source = stock.fundamental_categories || stock.analysis_v2?.structural?.categories || stock.scores || {}
  const entries = Object.entries(source).filter(([, value]) => Number.isFinite(Number(value))).slice(0, 8)
  if (entries.length < 3) return []
  const lines = ['', 'SECTION RADAR (research profile)']
  entries.forEach(([key, value]) => lines.push(`  ${key.replace(/_/g, ' ')}: ${Math.round(Number(value))}`))
  return lines
}

function scoreComponentsLines(stock) {
  const components = stock.components
  if (!components || !Object.keys(components).length) return []
  const lines = ['', 'SCORE COMPONENTS']
  Object.entries(components).forEach(([key, value]) => lines.push(`  ${key.replace(/_/g, ' ')}: ${value == null ? '–' : Math.round(value)}`))
  return lines
}

function fundamentalCategoriesLines(stock) {
  const categories = stock.fundamental_categories
  if (!categories || !Object.keys(categories).length) return []
  const lines = ['', 'FUNDAMENTAL CATEGORIES']
  Object.entries(categories).forEach(([key, value]) => {
    const evidence = stock.fundamental_detail?.category_coverage?.[key]
    const coverageNote = evidence && evidence.metrics_applicable > 0 ? ` (${evidence.metrics_used}/${evidence.metrics_applicable} metrics)` : ''
    lines.push(`  ${key.replace(/_/g, ' ')}: ${value == null ? '–' : Math.round(value)}${coverageNote}`)
  })
  return lines
}

function modifiersLines(stock) {
  if (!stock.modifiers?.notes?.length) return []
  const lines = ['', `SCORE MODIFIERS (${signedPoints(stock.modifiers.total || 0)} pts)`]
  stock.modifiers.notes.forEach((note) => lines.push(`  ${note}`))
  lines.push(`  Applied on top of the ${stock.base_score ?? '–'} evidence score. Modifiers refine a ranking; they never outweigh the fundamentals behind it.`)
  return lines
}

function insiderActivityLines(insider) {
  const buys = insider?.recent_acquisitions || 0
  const sells = insider?.recent_disposals || 0
  if (!insider?.records_reviewed || (!buys && !sells)) return []
  return [
    '', 'INSIDER ACTIVITY (Form 4)',
    `  ${buys} buy${buys === 1 ? '' : 's'} · ${sells} sell${sells === 1 ? '' : 's'} ` +
      `(${insider.records_reviewed} filing${insider.records_reviewed === 1 ? '' : 's'} reviewed)`,
  ]
}

const CONGRESS_FLAG_LABELS = {
  EXTRAORDINARY_BUY: 'First trade in a small, unfamiliar company',
  CLUSTER_TRADE: '3+ representatives, 14-day span',
  BUY_SELL_FLIP: 'Round trip within 60 days',
}

function disclosedPositioningLines(info) {
  if (!info) return []
  const lines = ['', 'DISCLOSED POSITIONING (Congress / institutional)']
  if (info.institutional_flag) {
    lines.push(`  ${info.institutional_flag === 'CLUSTER_ACCUMULATION'
      ? 'Curated managers accumulating' : 'Curated managers distributing'}`)
  }
  ;(info.congress_flags || []).forEach((flag) => {
    lines.push(`  ${CONGRESS_FLAG_LABELS[flag] || flag}`)
  })
  if (typeof info.score === 'number') lines.push(`  Combined score: ${info.score.toFixed(2)}`)
  return lines
}

function strengthsAndRisksLines(stock) {
  const lines = []
  if (stock.strengths?.length) {
    lines.push('', 'EVIDENCE FOR', ...stock.strengths.map((item) => `  + ${item}`))
  }
  if (stock.risks?.length) {
    lines.push('', 'RISKS / GAPS', ...stock.risks.map((item) => `  - ${item}`))
  }
  return lines
}

function applicabilityExceptionsLines(stock) {
  const status = stock.analysis_v2?.metric_status || {}
  const exceptions = Object.entries(status).filter(([, detail]) => detail.status !== 'applied')
  if (!exceptions.length) return []
  const lines = ['', 'APPLICABILITY AND DATA-QUALITY EXCEPTIONS']
  exceptions.forEach(([metric, detail]) => {
    lines.push(`  ${metric.replace(/_/g, ' ')} (${detail.status}): ${detail.reason || (detail.replaced_by ? `Replaced by ${detail.replaced_by.replace(/_/g, ' ')}` : 'No canonical observation available.')}`)
  })
  return lines
}

function disclaimerLines() {
  return ['', 'Disclaimer: Algorithmic research from quantitative metrics, not financial advice. Verify the filings and your own suitability before acting.']
}

/**
 * @param {object} stock - a research row (research/portfolio_coverage/screen_universe shape)
 * @param {object} [insideInfo] - screens/inside-information.json's by_ticker[stock.ticker] entry
 * @returns {string} plain text, ready for the clipboard
 */
export function buildStockCopyText(stock, insideInfo) {
  if (!stock?.ticker) return ''
  const recommendation = getRecommendation(stock)
  return [
    ...headerLines(stock),
    ...guidanceLines(recommendation),
    ...themeLines(stock),
    ...setupQualityLines(stock),
    ...factorBarLines(stock),
    ...kpiLines(stock),
    ...policyComparisonLines(stock, recommendation),
    ...businessThesisLines(stock),
    ...peerValuationLines(stock),
    ...metricSectionLines(stock),
    ...reconciliationLines(stock),
    ...sectionRadarLines(stock),
    ...scoreComponentsLines(stock),
    ...fundamentalCategoriesLines(stock),
    ...strengthsAndRisksLines(stock),
    ...modifiersLines(stock),
    ...insiderActivityLines(stock.insider_activity),
    ...disclosedPositioningLines(insideInfo),
    ...applicabilityExceptionsLines(stock),
    ...disclaimerLines(),
  ].join('\n')
}
