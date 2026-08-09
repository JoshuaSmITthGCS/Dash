import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import RecommendationShadowPanel from './RecommendationShadowPanel'

describe('RecommendationShadowPanel', () => {
  it('shows legacy, company, and position decisions without collapsing them', () => {
    render(<RecommendationShadowPanel
      legacy={{ action: 'SELL', suggestedTrimPct: 100 }}
      shadow={{
        model_version: 'decision-v2.0.0',
        company_structural_state: { classification: 'strong', effective_score: 81, data_coverage: 0.84 },
        company_timeliness_state: { classification: 'weakening', effective_score: 43, data_coverage: 0.71 },
        portfolio_fit_state: { classification: 'near_target', reason_codes: [] },
        position_rule_state: { classification: 'hard_cost_basis_stop_breached', profile: 'default' },
        company: {
          action: { label: 'hold_existing_position', reason_codes: ['quality_watch'] },
          deterioration_groups: [],
        },
        position_action: {
          label: 'exit', trim_percent: 0, reason_namespace: 'position_rule',
          reason_codes: ['sell_position_hard_cost_basis_stop'],
        },
        data_quality: { score_confidence: 0.71, data_coverage: 0.8 },
      }}
    />)
    expect(screen.getByText('SELL 100%')).toBeInTheDocument()
    expect(screen.getByText('Hold Existing Position')).toBeInTheDocument()
    expect(screen.getByText('Exit')).toBeInTheDocument()
    expect(screen.getByText(/does not imply fundamental impairment/i)).toBeInTheDocument()
    expect(screen.getByText(/production behavior is unchanged/i)).toBeInTheDocument()
  })
})
