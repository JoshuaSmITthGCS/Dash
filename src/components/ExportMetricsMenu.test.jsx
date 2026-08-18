import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ExportMetricsMenu from './ExportMetricsMenu'

const baseProps = {
  holdings: { portfolioPositions: [{ ticker: 'AAPL', shares: 10 }], actionable: [] },
  analytics: { performance: { sharpe: 1.1 } },
  benchmarks: { selectedBenchmarkLabel: 'S&P 500' },
  signalMetrics: { metrics: [] },
  monteCarlo: { status: 'ready' },
  scope: 'since_algorithm',
}

describe('ExportMetricsMenu', () => {
  beforeEach(() => {
    Object.assign(navigator, { clipboard: { writeText: vi.fn().mockResolvedValue(undefined) } })
    globalThis.URL.createObjectURL = vi.fn(() => 'blob:mock')
    globalThis.URL.revokeObjectURL = vi.fn()
  })

  it('shows the currently selected scope', () => {
    render(<ExportMetricsMenu {...baseProps} />)
    expect(screen.getByText('Since algorithm activation')).toBeInTheDocument()
  })

  it('copies the full snapshot to the clipboard as JSON', async () => {
    render(<ExportMetricsMenu {...baseProps} />)
    fireEvent.click(screen.getByText('Copy all metrics to clipboard'))
    await waitFor(() => expect(navigator.clipboard.writeText).toHaveBeenCalledTimes(1))
    const payload = JSON.parse(navigator.clipboard.writeText.mock.calls[0][0])
    expect(payload.holdings.positions).toEqual(baseProps.holdings.portfolioPositions)
    expect(payload.portfolio_analytics).toEqual(baseProps.analytics)
    expect(await screen.findByText('Copied to clipboard')).toBeInTheDocument()
  })

  it('triggers a JSON download', () => {
    render(<ExportMetricsMenu {...baseProps} />)
    fireEvent.click(screen.getByText('Download all metrics (JSON)'))
    expect(globalThis.URL.createObjectURL).toHaveBeenCalledTimes(1)
    expect(screen.getByText('Download started')).toBeInTheDocument()
  })

  it('reports a clipboard failure rather than silently doing nothing', async () => {
    navigator.clipboard.writeText.mockRejectedValueOnce(new Error('denied'))
    render(<ExportMetricsMenu {...baseProps} />)
    fireEvent.click(screen.getByText('Copy all metrics to clipboard'))
    expect(await screen.findByText(/Copy failed/)).toBeInTheDocument()
  })
})
