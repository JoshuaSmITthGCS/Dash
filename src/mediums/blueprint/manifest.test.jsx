import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import manifest from './manifest.js'
import { validateRenderer } from '../core/chartContract.js'
import { canonicalMetricState, confidenceOf } from '../core/states.js'
import { isMediumImplemented } from '../registry.js'
import { useData } from '../../lib/useData.js'

vi.mock('../../lib/useData.js', async (importOriginal) => ({ ...(await importOriginal()), useData: vi.fn() }))

describe('blueprint manifest', () => {
  it('declares the required shape', () => {
    expect(manifest.id).toBe('blueprint')
    expect(manifest.colorScheme).toBe('dark')
    expect(manifest.entry).not.toBeNull()
  })

  it('is discoverable through the registry', () => {
    expect(isMediumImplemented('blueprint')).toBe(true)
  })

  it('implements every chart-contract type', async () => {
    const renderer = await manifest.loadRenderer()
    expect(validateRenderer(renderer)).toEqual({ valid: true, missing: [] })
  })

  it('renders a threshold as a dimension line with the limit value printed at the line end', async () => {
    const renderer = await manifest.loadRenderer()
    const { container } = render(renderer.line({
      values: [1, 2, 3], metricId: 'x', ariaLabel: 'a',
      thresholds: [{ value: 2.5, kind: 'kill', label: 'Kill' }],
    }))
    expect(container.querySelector('text')).toHaveTextContent('2.5')
  })

  it('renders a leader-line callout for an annotation, never a legend', async () => {
    const renderer = await manifest.loadRenderer()
    const { container } = render(renderer.line({
      values: [1, 2, 3], metricId: 'x', ariaLabel: 'a',
      annotations: [{ x: 1, y: 2, kind: 'event', label: 'Rebalance' }],
    }))
    const texts = Array.from(container.querySelectorAll('text')).map((t) => t.textContent)
    expect(texts).toContain('Rebalance')
  })

  it('draws a heavier stroke for higher confidence, a separate channel from the dash pattern', async () => {
    const renderer = await manifest.loadRenderer()
    const confident = render(renderer.bar({ values: [10], metricId: 'x', state: { state: 'established' }, confidence: { level: 1 }, ariaLabel: 'a' })).container.querySelector('rect')
    const faint = render(renderer.bar({ values: [10], metricId: 'x', state: { state: 'established' }, confidence: { level: 0.1 }, ariaLabel: 'a' })).container.querySelector('rect')
    expect(confident.getAttribute('stroke-width')).not.toBe(faint.getAttribute('stroke-width'))
  })
})

describe('blueprint components', () => {
  const { LabelFrame, EmptyState, Container } = manifest.components

  function partsFor(metric) {
    return {
      title: metric.label, mediumLine: null, read: metric.reads || null, reference: metric.kill_threshold || null,
      provenance: null, state: canonicalMetricState(metric), confidence: confidenceOf({ metric }),
      reason: canonicalMetricState(metric).reason, previous: null, action: null,
    }
  }

  it('accumulating renders a dashed construction line with the count dimensioned', () => {
    const metric = { id: 'x', label: 'X', status: 'provisional', observations: 17, required_observations: 24 }
    render(<LabelFrame parts={partsFor(metric)} capabilityId="x" />)
    const line = document.querySelector('[data-dimension-line]')
    expect(line).toHaveAttribute('data-state-pattern', 'dashed')
    expect(line).toHaveTextContent('17 / 24')
  })

  it('breached renders an out-of-tolerance mark, never hue alone', () => {
    const metric = { id: 'x', label: 'X', status: 'ready', breached: true, kill_threshold: 'x < 1', status_message: 'Breached.' }
    render(<LabelFrame parts={partsFor(metric)} capabilityId="x" />)
    const line = document.querySelector('[data-dimension-line]')
    expect(line).toHaveAttribute('data-state-pattern', 'hatched')
    expect(screen.getByText(/OUT OF TOLERANCE/)).toBeInTheDocument()
  })

  it('EmptyState is a not-yet-specified dimension — a dashed leader ending in "?"', () => {
    render(<EmptyState reason="Publication gate closed." />)
    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent('?')
    expect(alert).toHaveTextContent('Publication gate closed.')
  })

  it('Container renders a sheet with a zone coordinate mark', () => {
    render(<Container state={{ state: 'established' }} zone="B2">x</Container>)
    expect(screen.getByText('B2')).toBeInTheDocument()
  })
})

describe('blueprint provenance strip (title block)', () => {
  it('renders REV — UNPROMOTED rather than a false final revision, when a promotion disclosure is present', () => {
    const { ProvenanceStrip } = manifest.components
    render(<ProvenanceStrip ready={44} breached={9} liveDays={18} modelVersion="3.2.0" promotionText="No signal has been promoted." />)
    expect(screen.getByText(/UNPROMOTED/)).toBeInTheDocument()
  })
})

describe('blueprint nav', () => {
  it('renders zone tabs with plain-English labels alongside the coordinate marks', () => {
    render(<MemoryRouter><manifest.nav.Component /></MemoryRouter>)
    expect(screen.getByRole('navigation', { name: 'Zone tabs' })).toBeInTheDocument()
    expect(screen.getByText('A1')).toBeInTheDocument()
    expect(screen.getByText('HOME')).toBeInTheDocument()
  })
})

describe('blueprint entry', () => {
  it('renders a sheet index with revision states', () => {
    useData.mockReturnValue({ data: { generated_at: '2026-08-25T00:00:00Z' }, loading: false })
    render(<manifest.entry.Component onContinue={() => {}} />)
    expect(screen.getByText(/SHEET 01\/06/)).toBeInTheDocument()
    expect(screen.getAllByText(/REV\./).length).toBeGreaterThan(0)
  })
})
