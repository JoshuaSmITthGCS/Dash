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
    // Daily dates 30 days apart in real time land on the last 31 points (index length-31..length-1).
    expect(screen.getByText(dates.at(-31))).toBeInTheDocument()
    expect(screen.queryByText(dates[0])).not.toBeInTheDocument()
  })

  it('offers short 1W / 5D / 1D ranges when the data is daily', () => {
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

    fireEvent.click(screen.getByRole('button', { name: '1D' }))
    // A 1-day window on daily data is a two-point line: yesterday's close and today's.
    expect(screen.getAllByText(dates.at(-2)).length).toBeGreaterThan(0)
    expect(screen.queryByText(dates.at(-3))).not.toBeInTheDocument()
  })
})
