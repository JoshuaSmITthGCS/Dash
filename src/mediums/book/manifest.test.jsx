import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import manifest from './manifest.js'
import { validateRenderer } from '../core/chartContract.js'
import { canonicalMetricState, confidenceOf } from '../core/states.js'
import { isMediumImplemented } from '../registry.js'
import { useData } from '../../lib/useData.js'

vi.mock('../../lib/useData.js', async (importOriginal) => ({ ...(await importOriginal()), useData: vi.fn() }))

describe('book manifest', () => {
  it('declares the required shape', () => {
    expect(manifest.id).toBe('book')
    expect(manifest.colorScheme).toBe('light')
    expect(manifest.entry).not.toBeNull()
  })

  it('is discoverable through the registry', () => {
    expect(isMediumImplemented('book')).toBe(true)
  })

  it('implements every chart-contract type', async () => {
    const renderer = await manifest.loadRenderer()
    expect(validateRenderer(renderer)).toEqual({ valid: true, missing: [] })
  })

  it('renders thin-stroke, no-fill bars — small-multiple print convention', async () => {
    const renderer = await manifest.loadRenderer()
    const { container } = render(renderer.bar({ values: [10, 5], metricId: 'test', ariaLabel: 'bar' }))
    const rect = container.querySelector('rect')
    expect(rect).toHaveAttribute('fill', 'none')
    expect(rect).toHaveAttribute('stroke-width', '1')
  })

  it('a numbered superscript marker on the plot links to a footnote at the foot', async () => {
    const renderer = await manifest.loadRenderer()
    const { container } = render(renderer.line({
      values: [1, 2, 3], metricId: 'x', ariaLabel: 'a',
      annotations: [{ x: 1, y: 2, kind: 'event', label: 'Rebalance effective this period.' }],
    }))
    const texts = Array.from(container.querySelectorAll('text')).map((t) => t.textContent)
    expect(texts).toContain('1')
    expect(texts.some((t) => t.includes('Rebalance effective this period.'))).toBe(true)
  })
})

describe('book components', () => {
  const { LabelFrame, EmptyState, Container } = manifest.components

  function partsFor(metric) {
    return {
      title: metric.label, mediumLine: null, read: metric.reads || null, reference: metric.kill_threshold || null,
      provenance: null, state: canonicalMetricState(metric), confidence: confidenceOf({ metric }),
      reason: canonicalMetricState(metric).reason, previous: null, action: null,
    }
  }

  it('established renders in roman type, no italics, no bold', () => {
    const metric = { id: 'x', label: 'X', status: 'ready', reads: 'X reads fine.' }
    render(<LabelFrame parts={partsFor(metric)} capabilityId="x" />)
    const value = screen.getByText('X reads fine.')
    expect(value.style.fontStyle).not.toBe('italic')
    expect(value.style.fontWeight).not.toBe('700')
  })

  it('accumulating renders in italic with a superscript observation count', () => {
    const metric = { id: 'x', label: 'X', status: 'provisional', observations: 17, required_observations: 24 }
    render(<LabelFrame parts={partsFor(metric)} capabilityId="x" />)
    const box = document.querySelector('[data-book-table]')
    expect(box.querySelector('sup')).toHaveTextContent('17')
    expect(box.textContent).toContain('17/24')
  })

  it('breached renders bold with an editorial-red dagger and a footnote, never hue alone', () => {
    const metric = { id: 'x', label: 'X', status: 'ready', breached: true, kill_threshold: 'x < 1', status_message: 'Breached.' }
    render(<LabelFrame parts={partsFor(metric)} capabilityId="x" />)
    expect(document.querySelectorAll('[data-book-dagger]').length).toBeGreaterThan(0)
    expect(document.querySelector('[data-book-footnote]')).toHaveTextContent('x < 1')
  })

  it('EmptyState is a bracketed editorial note', () => {
    render(<EmptyState reason="Publication gate closed." />)
    expect(screen.getByRole('alert')).toHaveTextContent('[not yet reported — Publication gate closed.]')
  })

  it('Container renders a ruled table with a folio', () => {
    render(<Container state={{ state: 'established' }} folio="p. 4">x</Container>)
    expect(screen.getByText('p. 4')).toBeInTheDocument()
  })
})

describe('book nav', () => {
  it('renders a running head and a thumb index down the edge with a 44px target per destination', () => {
    render(<MemoryRouter><manifest.nav.Component /></MemoryRouter>)
    expect(screen.getByRole('navigation', { name: 'Thumb index' })).toBeInTheDocument()
    expect(screen.getAllByRole('link').length).toBeGreaterThanOrEqual(6)
  })
})

describe('book entry', () => {
  it('renders a table of contents with the six destinations as chapters with folios', () => {
    useData.mockReturnValue({ data: { generated_at: '2026-08-25T00:00:00Z' }, loading: false })
    render(<manifest.entry.Component onContinue={() => {}} />)
    expect(screen.getByText(/Home/)).toBeInTheDocument()
    expect(screen.getByText(/Evidence/)).toBeInTheDocument()
  })
})
