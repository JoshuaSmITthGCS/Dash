import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import ResearchRadarChart, { radarEntries } from './ResearchRadarChart'

describe('ResearchRadarChart', () => {
  it('prefers canonical structural categories and clamps scores to the chart scale', () => {
    const entries = radarEntries({
      fundamental_categories: { valuation: 20, growth: 30, quality: 40 },
      analysis_v2: { structural: { categories: { valuation: 112, growth: -4, financial_health: 72 } } },
    })
    expect(entries.map((entry) => entry.value)).toEqual([100, 0, 72])
  })

  it('renders an accessible numeric alternative to the radar shape', () => {
    render(<ResearchRadarChart stock={{
      ticker: 'TEST',
      fundamental_categories: { valuation: 80, profitability: 70, growth: 60 },
    }} />)
    expect(screen.getByLabelText(/TEST section scores/i)).toBeInTheDocument()
    expect(screen.getByText('Valuation')).toBeInTheDocument()
    expect(screen.getByText('80')).toBeInTheDocument()
  })
})
