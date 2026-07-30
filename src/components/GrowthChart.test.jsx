import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import GrowthChart from './GrowthChart'

describe('GrowthChart zoom', () => {
  it('lets the user focus the chart on a recent time range', () => {
    const dates = Array.from({ length: 60 }, (_, index) =>
      new Date(Date.UTC(2025, 0, index + 1)).toISOString().slice(0, 10))
    const values = dates.map((_, index) => 100 + index)

    render(
      <GrowthChart
        dates={dates}
        series={[{ label: 'Holdings', values, color: 'green' }]}
        title="Portfolio"
        zoomable
      />,
    )

    expect(screen.getByRole('button', { name: '1M' })).toHaveAttribute('aria-pressed', 'false')
    fireEvent.click(screen.getByRole('button', { name: '1M' }))
    expect(screen.getByRole('button', { name: '1M' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByText(dates.at(-6))).toBeInTheDocument()
    expect(screen.queryByText(dates[0])).not.toBeInTheDocument()
  })
})
