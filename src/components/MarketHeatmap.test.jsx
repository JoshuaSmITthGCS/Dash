import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import MarketHeatmap, { buildPortfolioSectorHeatmap } from './MarketHeatmap.jsx'

const position = (ticker, sector, currentValue, previousClose, price) => ({
  ticker,
  currentValue,
  priceInfo: { sector, previousClose, price },
})

describe('portfolio sector heatmap', () => {
  it('sizes sectors by portfolio allocation and weights their daily return by holding value', () => {
    const sectors = buildPortfolioSectorHeatmap([
      position('AAA', 'Technology', 60, 100, 110),
      position('BBB', 'Technology', 20, 100, 90),
      position('CCC', 'Energy', 20, 100, 95),
    ])

    expect(sectors).toEqual([
      expect.objectContaining({ sector: 'Technology', allocationPct: 80, avgChange: 5 }),
      expect.objectContaining({ sector: 'Energy', allocationPct: 20, avgChange: -5 }),
    ])
  })

  it('uses green for gains, red for losses, and exposes allocation in text', () => {
    const { container } = render(<MarketHeatmap positions={[
      position('AAA', 'Technology', 75, 100, 110),
      position('BBB', 'Energy', 25, 100, 90),
    ]} />)

    expect(screen.getByRole('img')).toHaveAccessibleName(/Technology 75.0% allocation, \+10.00%/)
    expect(screen.getByRole('img')).toHaveAccessibleName(/Energy 25.0% allocation, -10.00%/)
    expect(container.querySelector('[data-sector="Technology"]')).toHaveAttribute('data-tone', 'positive')
    expect(container.querySelector('[data-sector="Energy"]')).toHaveAttribute('data-tone', 'negative')
    expect(container.querySelector('[data-sector="Technology"]')).toHaveAttribute('data-allocation-pct', '75.0')
  })

  it('keeps unchanged and unavailable sectors neutral', () => {
    const { container } = render(<MarketHeatmap positions={[
      position('FLAT', 'Utilities', 50, 100, 100),
      { ticker: 'WAIT', currentValue: 50, priceInfo: { sector: 'Health Care' } },
    ]} />)

    expect(container.querySelector('[data-sector="Utilities"]')).toHaveAttribute('data-tone', 'neutral')
    expect(container.querySelector('[data-sector="Health Care"]')).toHaveAttribute('data-tone', 'neutral')
  })
})
