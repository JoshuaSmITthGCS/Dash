import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import ScoreExplainability, { FactorBars } from './ScoreExplainability.jsx'

const attribution = (score) => ({
  base: 50,
  evidence: [{ key: 'valuation', label: 'valuation', points: 8 }],
  confidence_shrinkage_points: -2,
  modifiers: [{ key: 'expectations', label: 'expectations', points: score - 56 }],
  final_score: score,
})

const stock = {
  ticker: 'AAA',
  sector: 'Technology',
  explainability: {
    active_variant: 'champion',
    attribution: { champion: attribution(62), challenger: attribution(58) },
    factor_bars: { value: 70, quality: 80, growth: 60, momentum: 55, sentiment: 50, risk: 65 },
    metrics: {
      champion: [{
        metric: 'ev_to_ebitda', label: 'EV to EBITDA', raw_value: 24.1, format: 'multiple',
        sector_percentile: 78, normalization_scope: 'sector', direction: 'lower_is_better',
        own_history_percentile: 40, own_history_years: 5, own_history_status: 'scored',
        final_point_contribution: -2.6,
      }],
      challenger: [],
    },
    score_history: { status: 'accumulating', stored_months: 2, required_months: 6, points: [] },
    anomalies: [],
  },
}

describe('score explainability', () => {
  it('renders six glanceable factor bars', () => {
    render(<FactorBars bars={stock.explainability.factor_bars} />)
    expect(screen.getByLabelText('Research factor summary').children).toHaveLength(6)
  })

  it('shows peer and own-history context and switches score variants', () => {
    render(<ScoreExplainability stock={stock} />)
    expect(screen.getByText(/24.1x, 78th percentile in Technology, so expensive relative to peers/)).toBeInTheDocument()
    expect(screen.getByText(/40th percentile versus its own 5-year history/)).toBeInTheDocument()
    expect(screen.getByText(/2 of 6 stored months/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'challenger' }))
    expect(screen.getByText('Why the score is 58.0')).toBeInTheDocument()
  })
})
