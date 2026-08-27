import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import manifest from './manifest.js'
import { validateRenderer } from '../core/chartContract.js'
import { canonicalMetricState, confidenceOf } from '../core/states.js'
import { isMediumImplemented } from '../registry.js'
import { useData } from '../../lib/useData.js'

vi.mock('../../lib/useData.js', async (importOriginal) => ({ ...(await importOriginal()), useData: vi.fn() }))

describe('gallery manifest', () => {
  it('declares the required shape — the default medium', () => {
    expect(manifest.id).toBe('gallery')
    expect(manifest.colorScheme).toBe('light')
    expect(manifest.entry).not.toBeNull()
  })

  it('is discoverable through the registry', () => {
    expect(isMediumImplemented('gallery')).toBe(true)
  })

  it('implements every chart-contract type', async () => {
    const renderer = await manifest.loadRenderer()
    expect(validateRenderer(renderer)).toEqual({ valid: true, missing: [] })
  })

  it('renders real rough.js paths, not flat SVG primitives, for bar', async () => {
    const renderer = await manifest.loadRenderer()
    const { container } = render(renderer.bar({ values: [10, 5], metricId: 'test', ariaLabel: 'bar' }))
    expect(container.querySelectorAll('path').length).toBeGreaterThan(0)
  })

  it('rough.js geometry is deterministic for the same metricId — screenshots never churn', async () => {
    const renderer = await manifest.loadRenderer()
    const first = render(renderer.line({ values: [1, 2, 3], metricId: 'same-id', ariaLabel: 'a' })).container.innerHTML
    const second = render(renderer.line({ values: [1, 2, 3], metricId: 'same-id', ariaLabel: 'a' })).container.innerHTML
    expect(first).toBe(second)
  })

  it('accumulating state draws with higher roughness than established (state-adjacent device)', async () => {
    const renderer = await manifest.loadRenderer()
    const established = render(renderer.bar({ values: [10], metricId: 'x', state: { state: 'established' }, ariaLabel: 'a' })).container.innerHTML
    const accumulating = render(renderer.bar({ values: [10], metricId: 'x', state: { state: 'accumulating' }, ariaLabel: 'a' })).container.innerHTML
    expect(established).not.toBe(accumulating)
  })
})

describe('gallery components', () => {
  const { LabelFrame, EmptyState, Container } = manifest.components

  it('LabelFrame renders the wall label with provenance, present with zero exceptions', () => {
    const metric = { id: 'x', label: 'X', status: 'ready', breached: false, reads: 'A read.' }
    render(<LabelFrame parts={{ title: 'X', mediumLine: 'monthly', read: metric.reads, reference: null, provenance: 'signal_metrics.json', state: canonicalMetricState(metric), confidence: confidenceOf({ metric }), reason: null, action: null }} capabilityId="x" />)
    expect(screen.getByText('signal_metrics.json', { exact: false })).toBeInTheDocument()
  })

  it('gilt frame is reserved for the primary work only', () => {
    const { container: primaryContainer } = render(<Container primary state={{ state: 'established' }}>x</Container>)
    expect(primaryContainer.querySelector('[data-gallery-frame]')).toHaveAttribute('data-primary', 'true')
    const { container: plainContainer } = render(<Container state={{ state: 'established' }}>x</Container>)
    expect(plainContainer.querySelector('[data-gallery-frame]')).not.toHaveAttribute('data-primary')
  })

  it('EmptyState is an empty frame carrying the reason — the museum "under conservation" device', () => {
    render(<EmptyState reason="Publication gate closed." />)
    expect(screen.getByRole('alert')).toHaveTextContent('Publication gate closed.')
  })
})

describe('gallery entry', () => {
  it('the foyer reads the live as-of date', () => {
    useData.mockReturnValue({ data: { generated_at: '2026-08-25T00:00:00Z' }, loading: false })
    render(<manifest.entry.Component onContinue={() => {}} />)
    expect(screen.getByText(/Open through/)).toHaveTextContent('8/25/2026')
  })
})
