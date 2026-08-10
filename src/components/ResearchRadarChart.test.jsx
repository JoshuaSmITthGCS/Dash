import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import ResearchRadarChart, { radarEntries } from './ResearchRadarChart'

describe('ResearchRadarChart', () => {
  it('plots the categories that produced this page\'s score, not another model\'s', () => {
    // Globus Medical published growth at 64.6 while the v2 structural layer read 81.7. Both
    // were rendered as "Growth" on one page, on one scale, with nothing marking them apart.
    const entries = radarEntries({
      fundamental_categories: { valuation: 78, growth: 64.6, financial_health: 100 },
      analysis_v2: { structural: { categories: { valuation: 78.3, growth: 81.7, financial_health: 100 } } },
    })
    expect(entries.find((entry) => entry.key === 'growth').value).toBe(64.6)
  })

  it('falls back to the structural layer only when the published categories are absent', () => {
    const entries = radarEntries({
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
