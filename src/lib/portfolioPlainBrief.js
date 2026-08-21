// Plain-English summary of the Data overview evidence — no ratios, no jargon. One paragraph
// a reader with no finance background can act on, shown above the detailed evidence sections.

import { combinedEvidence } from './metricAssessment.js'

const finite = (value) => Number.isFinite(value)

const VERDICT_PHRASE = {
  Strong: 'a strong picture',
  Healthy: 'a healthy picture',
  Mixed: 'a mixed picture — some good signs, some worth watching',
  Weak: 'more warning signs than good ones right now',
  Poor: 'a rough stretch on most measures',
  Inconclusive: 'not enough history yet for a confident read',
}

const VERDICT_TONE = {
  Strong: 'positive',
  Healthy: 'positive',
  Mixed: 'neutral',
  Inconclusive: 'neutral',
  Weak: 'caution',
  Poor: 'caution',
}

export function buildDataOverviewBrief({ performance, batting, metricModel, benchmarkLabel = 'the market' }) {
  if (!performance?.available) {
    const reason = performance?.reason ? performance.reason.replace(/^./, (char) => char.toLowerCase()) : 'more daily returns are needed'
    return { tone: 'neutral', text: `There isn't enough trading history yet to sum up performance in plain terms — ${reason} Check back as more days of data come in.` }
  }

  const returnPhrase = finite(performance.annualizedReturn)
    ? performance.annualizedReturn >= 0
      ? `has grown at roughly ${performance.annualizedReturn.toFixed(1)}% a year`
      : `has lost ground, down roughly ${Math.abs(performance.annualizedReturn).toFixed(1)}% a year`
    : 'has a return that can’t be annualized yet'

  let comparisonPhrase = ''
  if (batting?.available) {
    comparisonPhrase = batting.battingAveragePct >= 50
      ? ` It has kept pace with or beaten ${benchmarkLabel} in ${batting.wins} of the last ${batting.months} months.`
      : ` It has trailed ${benchmarkLabel} in most recent months, beating it in only ${batting.wins} of the last ${batting.months}.`
  } else if (finite(performance.informationRatio)) {
    comparisonPhrase = performance.informationRatio >= 0
      ? ` On average it has edged out ${benchmarkLabel} over this stretch.`
      : ` On average it has lagged ${benchmarkLabel} over this stretch.`
  }

  let riskPhrase = ''
  if (finite(performance.maxDrawdown)) {
    const worst = Math.abs(performance.maxDrawdown).toFixed(0)
    const current = finite(performance.currentDrawdown) ? Math.abs(performance.currentDrawdown) : null
    riskPhrase = current != null && current > 1
      ? ` The ride has been bumpy at times — the biggest dip was about ${worst}%, and it's currently sitting about ${current.toFixed(0)}% below its high point.`
      : ` The biggest dip along the way was about ${worst}%, but it's at or near a new high right now.`
  }

  const sections = [
    { id: 'standard', metrics: metricModel?.standard || [] },
    { id: 'comparison', metrics: metricModel?.comparison || [] },
    { id: 'fast', metrics: metricModel?.fast || [] },
  ]
  const overall = combinedEvidence(sections)
  const verdictPhrase = ` Putting it all together, the evidence points to ${VERDICT_PHRASE[overall.read] || 'a mixed picture'}.`

  return {
    tone: VERDICT_TONE[overall.read] || 'neutral',
    text: `Your portfolio ${returnPhrase} since it started.${comparisonPhrase}${riskPhrase}${verdictPhrase}`,
  }
}
