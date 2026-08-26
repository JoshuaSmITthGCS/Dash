import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import manifest from './manifest.js'
import { validateRenderer } from '../core/chartContract.js'
import { canonicalMetricState, confidenceOf } from '../core/states.js'
import { headlineFor } from '../core/headline.js'
import { isMediumImplemented } from '../registry.js'
import { useData } from '../../lib/useData.js'

vi.mock('../../lib/useData.js', async (importOriginal) => ({ ...(await importOriginal()), useData: vi.fn() }))

describe('star-chart manifest', () => {
  it('declares the required shape — a calm medium', () => {
    expect(manifest.id).toBe('star-chart')
    expect(manifest.colorScheme).toBe('dark')
    expect(manifest.motion.calmSetting).toBe(true)
    expect(manifest.entry).not.toBeNull()
  })

  it('is discoverable through the registry', () => {
    expect(isMediumImplemented('star-chart')).toBe(true)
  })

  it('implements every chart-contract type', async () => {
    const renderer = await manifest.loadRenderer()
    expect(validateRenderer(renderer)).toEqual({ valid: true, missing: [] })
  })

  it('scales scatter marks by area (sqrt of value), never by radius directly', async () => {
    const renderer = await manifest.loadRenderer()
    const { container } = render(renderer.scatter({
      series: [{ x: 0, y: 0, magnitude: 1 }, { x: 1, y: 1, magnitude: 4 }],
      metricId: 'x', ariaLabel: 'a',
    }))
    const circles = container.querySelectorAll('circle')
    const r0 = parseFloat(circles[0].getAttribute('r'))
    const r1 = parseFloat(circles[1].getAttribute('r'))
    // magnitude 4x -> sqrt(4)=2x radius delta from base, not a flat 4x radius.
    expect(r1).toBeGreaterThan(r0)
    expect(r1).toBeLessThan(r0 * 4)
  })
})

describe('star-chart components', () => {
  const { LabelFrame, EmptyState, Container } = manifest.components

  function partsFor(metric) {
    return {
      title: metric.label, mediumLine: null, read: metric.reads ?? String(metric.value ?? ''), reference: metric.kill_threshold || null,
      provenance: null, state: canonicalMetricState(metric), confidence: confidenceOf({ metric }),
      reason: canonicalMetricState(metric).reason, previous: null, headline: headlineFor(metric),
      confidenceInterval: metric.detail?.ic_ci_95 ?? null, action: null,
    }
  }

  it('plots every metric at a deterministic coordinate — same capabilityId, same position every render', () => {
    const metric = { id: 'x', label: 'X', status: 'ready', value: 5 }
    const first = render(<LabelFrame parts={partsFor(metric)} capabilityId="metric.report.x" />).container.querySelector('circle')
    const second = render(<LabelFrame parts={partsFor(metric)} capabilityId="metric.report.x" />).container.querySelector('circle')
    expect(first.getAttribute('cx')).toBe(second.getAttribute('cx'))
    expect(first.getAttribute('cy')).toBe(second.getAttribute('cy'))
  })

  it('accumulating renders an open (unfilled) circle with the N of M count printed beside it', () => {
    const metric = { id: 'x', label: 'X', status: 'provisional', observations: 17, required_observations: 24 }
    render(<LabelFrame parts={partsFor(metric)} capabilityId="x" />)
    const circle = document.querySelector('circle')
    expect(circle).toHaveAttribute('fill', 'none')
    expect(screen.getByText('17 of 24')).toBeInTheDocument()
  })

  it('breached renders a cross-hair notation over the mark, never hue alone', () => {
    const metric = { id: 'x', label: 'X', status: 'ready', breached: true, kill_threshold: 'x < 1', status_message: 'Breached.', value: 3 }
    render(<LabelFrame parts={partsFor(metric)} capabilityId="x" />)
    expect(document.querySelectorAll('line[stroke="var(--state-breach)"]').length).toBeGreaterThanOrEqual(2)
  })

  it('renders an error ellipse instead of a circle when a real bootstrap CI is published', () => {
    const metric = { id: 'ic_bootstrap_ci', label: 'Bootstrap IC CI', status: 'ready', value: 0.03, detail: { ic_ci_95: [-0.01, 0.0777] } }
    render(<LabelFrame parts={partsFor(metric)} capabilityId="x" />)
    expect(document.querySelector('ellipse')).toBeInTheDocument()
  })

  it('unavailable renders no mark at all — a catalogued position, coordinate reserved, reason in the legend', () => {
    const metric = { id: 'x', label: 'X', status: 'unavailable', status_message: 'No data yet.' }
    render(<LabelFrame parts={partsFor(metric)} capabilityId="x" />)
    expect(document.querySelector('circle')).not.toBeInTheDocument()
    expect(document.querySelector('ellipse')).not.toBeInTheDocument()
    expect(screen.getByText(/catalogued, unplotted/)).toHaveTextContent('No data yet.')
  })

  it('confidence renders as a seeing-conditions band, a separate channel from the four marks', () => {
    const metric = { id: 'x', label: 'X', status: 'ready', value: 1 }
    render(<LabelFrame parts={partsFor(metric)} capabilityId="x" />)
    expect(screen.getByText(/^Seeing:/)).toBeInTheDocument()
  })

  it('EmptyState is a catalogued position with nothing plotted', () => {
    render(<EmptyState reason="Publication gate closed." />)
    expect(screen.getByRole('alert')).toHaveTextContent('catalogued, unplotted')
    expect(screen.getByRole('alert')).toHaveTextContent('Publication gate closed.')
    expect(screen.getByRole('alert').querySelector('circle')).not.toBeInTheDocument()
  })

  it('Container is a faint graticule, never a filled card', () => {
    const { container } = render(<Container state={{ state: 'established' }}>x</Container>)
    const plate = container.querySelector('[data-sc-plate]')
    expect(plate).toBeInTheDocument()
  })
})

describe('star-chart nav', () => {
  it('the corner legend is persistent and doubles as navigation, never collapsed', () => {
    render(<MemoryRouter><manifest.nav.Component /></MemoryRouter>)
    const legend = screen.getByRole('navigation', { name: 'Legend' })
    expect(legend).toBeInTheDocument()
    expect(screen.getAllByRole('link').length).toBeGreaterThanOrEqual(6)
  })
})

describe('star-chart entry', () => {
  it('renders a plate index by epoch', () => {
    useData.mockReturnValue({ data: { generated_at: '2026-08-25T00:00:00Z' }, loading: false })
    render(<manifest.entry.Component onContinue={() => {}} />)
    expect(screen.getAllByText(/^Plate [IV]+$/).length).toBe(6)
    expect(screen.getByText(/Epoch:/)).toBeInTheDocument()
  })
})
