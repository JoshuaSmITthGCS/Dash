import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import manifest from './manifest.js'
import { validateRenderer } from '../core/chartContract.js'
import { canonicalMetricState, confidenceOf } from '../core/states.js'
import { headlineFor } from '../core/headline.js'
import { isMediumImplemented } from '../registry.js'
import { useData } from '../../lib/useData.js'

vi.mock('../../lib/useData.js', async (importOriginal) => ({ ...(await importOriginal()), useData: vi.fn() }))

describe('newspaper manifest', () => {
  it('declares the required shape', () => {
    expect(manifest.id).toBe('newspaper')
    expect(manifest.colorScheme).toBe('light')
    expect(manifest.entry).not.toBeNull()
  })

  it('is discoverable through the registry', () => {
    expect(isMediumImplemented('newspaper')).toBe(true)
  })

  it('implements every chart-contract type', async () => {
    const renderer = await manifest.loadRenderer()
    expect(validateRenderer(renderer)).toEqual({ valid: true, missing: [] })
  })

  it('renders a text annotation (arrow + sentence), never a legend, for an annotated line', async () => {
    const renderer = await manifest.loadRenderer()
    const { container } = render(renderer.line({
      values: [1, 2, 3], metricId: 'x', ariaLabel: 'a',
      annotations: [{ x: 1, y: 2, kind: 'event', label: 'Earnings beat drove the jump.' }],
    }))
    expect(container.querySelector('text')).toHaveTextContent('Earnings beat drove the jump.')
    expect(container.querySelector('marker')).toBeInTheDocument()
  })
})

describe('newspaper components', () => {
  const { LabelFrame, EmptyState, Container } = manifest.components

  function partsFor(metric) {
    return {
      title: metric.label, mediumLine: null, read: metric.reads || null, reference: metric.kill_threshold || null,
      provenance: null, state: canonicalMetricState(metric), confidence: confidenceOf({ metric }),
      reason: canonicalMetricState(metric).reason, previous: null, headline: headlineFor(metric), action: null,
    }
  }

  it('renders the generated headline above the chart, never freehand copy', () => {
    const metric = { id: 'x', label: 'Momentum leg', status: 'ready', reads: 'Momentum leg has led the composite for six weeks.' }
    render(<LabelFrame parts={partsFor(metric)} capabilityId="x" />)
    expect(screen.getByText('Momentum leg has led the composite for six weeks.')).toBeInTheDocument()
  })

  it('an accumulating metric only ever gets an interrogative headline, never a declarative one', () => {
    const metric = { id: 'x', label: 'Rank IC', status: 'provisional', observations: 17, required_observations: 24, cadence: 'Weekly' }
    render(<LabelFrame parts={partsFor(metric)} capabilityId="x" />)
    expect(screen.getByText(/^Is /)).toBeInTheDocument()
    expect(screen.getByText(/17 of 24/)).toBeInTheDocument()
  })

  it('a breached metric renders a standfirst flag line above the headline', () => {
    const metric = { id: 'x', label: 'Deflated Sharpe', status: 'ready', breached: true, kill_threshold: 'Sharpe < 0.5', status_message: 'Breached.' }
    render(<LabelFrame parts={partsFor(metric)} capabilityId="x" />)
    const flag = document.querySelector('[data-standfirst]')
    expect(flag).toBeInTheDocument()
    expect(flag).toHaveTextContent('Breached: Sharpe < 0.5.')
  })

  it('renders a bylined confidence note as a separate line from the headline', () => {
    const metric = { id: 'x', label: 'X', status: 'ready', reads: 'X reads fine.' }
    render(<LabelFrame parts={partsFor(metric)} capabilityId="x" />)
    expect(screen.getByText(/^Confidence:/)).toBeInTheDocument()
  })

  it('EmptyState renders NOT YET REPORTED with the reason, wire-service style', () => {
    render(<EmptyState reason="Publication gate closed." />)
    expect(screen.getByRole('alert')).toHaveTextContent('NOT YET REPORTED')
    expect(screen.getByRole('alert')).toHaveTextContent('Publication gate closed.')
  })

  it('Container is a column rule, never a box', () => {
    const { container } = render(<Container state={{ state: 'established' }}>x</Container>)
    expect(container.querySelector('[data-column-rule]')).toBeInTheDocument()
  })
})

describe('newspaper entry', () => {
  it('the front page renders the actual top-ranked name as the lead story, never a placeholder', () => {
    useData.mockReturnValue({
      data: {
        generated_at: '2026-08-25T00:00:00Z',
        research: [
          { ticker: 'AAA', name: 'Aaa Corp', score: 55, stance: 'MIXED', recommendation: { action: 'HOLD' } },
          { ticker: 'BBB', name: 'Bbb Corp', score: 91, stance: 'ATTRACTIVE', recommendation: { action: 'WATCH' } },
        ],
      },
      loading: false,
    })
    render(<manifest.entry.Component onContinue={() => {}} />)
    expect(screen.getByText(/Bbb Corp \(BBB\)/)).toBeInTheDocument()
    expect(screen.getByText(/score 91/)).toBeInTheDocument()
  })
})
