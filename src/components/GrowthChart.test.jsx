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

  it('exposes exact values through a keyboard-operable tooltip', () => {
    render(<GrowthChart dates={['2025-01-01', '2025-01-02', '2025-01-03']} series={[{ label: 'Holdings', values: [100, 105, 110], color: 'green' }]} title="Portfolio" />)
    const chart = screen.getByRole('img', { name: /Portfolio/ })
    fireEvent.focus(chart)
    expect(screen.getAllByText('2025-01-03').length).toBeGreaterThan(1)
    expect(screen.getByText(/Holdings: \$110/)).toBeInTheDocument()
    fireEvent.keyDown(chart, { key: 'ArrowLeft' })
    expect(screen.getAllByText('2025-01-02').length).toBeGreaterThan(1)
  })

  it('supports the minimal home treatment without axis clutter', () => {
    const { container } = render(<GrowthChart minimal className="home-growth-chart" dates={['2025-01-01', '2025-01-02']} series={[{ label: 'Holdings', values: [100, 110], color: 'green', emphasis: true }]} />)
    expect(container.querySelector('.home-growth-chart')).toBeInTheDocument()
    expect(container.querySelectorAll('.chart-grid-line')).toHaveLength(0)
    expect(screen.getByRole('img')).toHaveAccessibleName(/Holdings: \$110/)
  })

  it('renders a separate latest-value needle without replacing the closing marker', () => {
    const { container } = render(<GrowthChart
      dates={['2025-01-01', '2025-01-02']}
      series={[{ label: 'Holdings', values: [100, 110], color: 'green', emphasis: true }]}
      endMarkers={[{ label: 'After-hours', value: 112, color: 'orange' }]}
    />)

    expect(container.querySelectorAll('.chart-series-primary circle')).toHaveLength(1)
    expect(container.querySelector('.chart-value-needle')).toBeInTheDocument()
    expect(screen.getByRole('img')).toHaveAccessibleName(/After-hours: \$112/)
    expect(screen.getByText('After-hours')).toBeInTheDocument()
  })

  it('reserves mobile chart space for an overlaid account summary', () => {
    const originalMatchMedia = window.matchMedia
    window.matchMedia = () => ({
      matches: true,
      addEventListener() {},
      removeEventListener() {},
    })

    const { container, unmount } = render(<GrowthChart
      minimal
      mobileHeight={360}
      mobileWidth={390}
      mobileTopInset={156}
      dates={['2025-01-01', '2025-01-02']}
      series={[{ label: 'Holdings', values: [100, 110], color: 'green', emphasis: true }]}
    />)
    expect(container.querySelector('svg')).toHaveAttribute('height', '360')
    expect(container.querySelector('svg')).toHaveAttribute('viewBox', '0 0 390 360')
    unmount()
    window.matchMedia = originalMatchMedia
  })
})
