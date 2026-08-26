import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import WallLabel from './WallLabel.jsx'
import { MediumProvider } from './MediumContext.jsx'

// A minimal fake medium — real mediums supply their own LabelFrame in Phase 2b; this proves
// the contract works generically for any medium that implements it.
function FakeLabelFrame({ parts, capabilityId, children }) {
  return (
    <section data-testid="fake-label" data-capability-id={capabilityId}>
      <h3>{parts.title}</h3>
      {parts.mediumLine && <p data-testid="medium-line">{parts.mediumLine}</p>}
      {parts.read && <p data-testid="read">{parts.read}</p>}
      <p data-testid="state">{parts.state.state}</p>
      <p data-testid="confidence">{parts.confidence.level}</p>
      {parts.reason && <p data-testid="reason">{parts.reason}</p>}
      {parts.previous != null && <p data-testid="previous">{parts.previous}</p>}
      <p data-testid="headline">{parts.headline.headline}</p>
      {parts.confidenceInterval && <p data-testid="confidence-interval">{parts.confidenceInterval.join(',')}</p>}
      {children}
    </section>
  )
}

const fakeManifest = { components: { LabelFrame: FakeLabelFrame } }

function renderWithMedium(ui, manifest = fakeManifest) {
  return render(<MediumProvider value={manifest}>{ui}</MediumProvider>)
}

describe('WallLabel', () => {
  it('derives every wall-label part from the metric row and renders through the medium', () => {
    renderWithMedium(
      <WallLabel metric={{
        id: 'rank_ic_1d', label: 'Rank IC (1d)', reads: 'Spearman correlation of score against forward return.',
        unit: 'correlation', cadence: 'Weekly', kill_threshold: 'Mean IC < 0.02', status: 'ready', breached: true,
      }} />
    )
    expect(screen.getByText('Rank IC (1d)')).toBeInTheDocument()
    expect(screen.getByTestId('medium-line')).toHaveTextContent('correlation · Weekly')
    expect(screen.getByTestId('read')).toHaveTextContent('Spearman correlation')
    expect(screen.getByTestId('state')).toHaveTextContent('breached')
  })

  it('passes through a genuinely published previous value, additive and optional', () => {
    renderWithMedium(<WallLabel metric={{ id: 'x', label: 'X', status: 'ready', previous_value: 0.42 }} />)
    expect(screen.getByTestId('previous')).toHaveTextContent('0.42')
  })

  it('derives a headline via headlineFor — never a declarative sentence for an accumulating metric', () => {
    renderWithMedium(<WallLabel metric={{ id: 'x', label: 'Rank IC', status: 'provisional', observations: 17, required_observations: 24, cadence: 'Weekly' }} />)
    expect(screen.getByTestId('headline')).toHaveTextContent('Is')
    expect(screen.getByTestId('headline')).toHaveTextContent('17 of 24')
  })

  it('passes through a genuinely published bootstrap confidence interval, additive and optional', () => {
    renderWithMedium(<WallLabel metric={{ id: 'ic_bootstrap_ci', label: 'Bootstrap IC CI', status: 'ready', detail: { ic_ci_95: [-0.01, 0.0777] } }} />)
    expect(screen.getByTestId('confidence-interval')).toHaveTextContent('-0.01,0.0777')
  })

  it('never fabricates a confidence interval when the metric does not publish one', () => {
    renderWithMedium(<WallLabel metric={{ id: 'x', label: 'X', status: 'ready' }} />)
    expect(screen.queryByTestId('confidence-interval')).not.toBeInTheDocument()
  })

  it('never fabricates a previous value when the metric does not publish one', () => {
    renderWithMedium(<WallLabel metric={{ id: 'x', label: 'X', status: 'ready' }} />)
    expect(screen.queryByTestId('previous')).not.toBeInTheDocument()
  })

  it('never emits a numeral or label the metric did not publish (blank fields stay blank)', () => {
    renderWithMedium(<WallLabel metric={{ id: 'pbo', label: 'PBO', status: 'provisional', breached: false }} />)
    expect(screen.queryByTestId('medium-line')).not.toBeInTheDocument()
    expect(screen.queryByTestId('read')).not.toBeInTheDocument()
  })

  it('sets data-capability-id derived from the metric id', () => {
    renderWithMedium(<WallLabel metric={{ id: 'deflated_sharpe', label: 'Deflated Sharpe', status: 'ready' }} />)
    expect(screen.getByTestId('fake-label')).toHaveAttribute('data-capability-id', 'metric.report.deflated-sharpe')
  })

  it('respects an explicit capabilityId override', () => {
    renderWithMedium(<WallLabel metric={{ id: 'x', label: 'X', status: 'ready' }} capabilityId="figure.home.custom" />)
    expect(screen.getByTestId('fake-label')).toHaveAttribute('data-capability-id', 'figure.home.custom')
  })

  it('renders an unavailable metric with its reason, never a zero', () => {
    renderWithMedium(<WallLabel metric={{ id: 'x', label: 'X', status: 'unavailable', status_message: 'No data yet.' }} />)
    expect(screen.getByTestId('state')).toHaveTextContent('unavailable')
    expect(screen.getByTestId('reason')).toHaveTextContent('No data yet.')
  })

  it('falls back to a legible plain render when the medium has no LabelFrame yet (dev-time)', () => {
    renderWithMedium(<WallLabel metric={{ id: 'x', label: 'In Progress Metric', status: 'ready', reads: 'A read.' }} />, { components: {} })
    expect(screen.getByText('In Progress Metric')).toBeInTheDocument()
    expect(screen.getByText('A read.')).toBeInTheDocument()
  })

  it('throws a clear error when rendered outside a MediumProvider', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    expect(() => render(<WallLabel metric={{ id: 'x', label: 'X', status: 'ready' }} />)).toThrow(/MediumProvider/)
    spy.mockRestore()
  })
})
