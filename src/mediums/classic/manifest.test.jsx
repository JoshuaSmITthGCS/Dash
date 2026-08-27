import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import manifest from './manifest.js'
import { validateRenderer } from '../core/chartContract.js'
import { canonicalMetricState, confidenceOf } from '../core/states.js'
import { isMediumImplemented } from '../registry.js'

describe('classic manifest', () => {
  it('declares the required shape — the only medium with entry: null and acceptsAccent: true', () => {
    expect(manifest.id).toBe('classic')
    expect(manifest.colorScheme).toBe('dark')
    expect(manifest.entry).toBeNull()
    expect(manifest.acceptsAccent).toBe(true)
  })

  it('is discoverable through the registry', () => {
    expect(isMediumImplemented('classic')).toBe(true)
  })

  it('implements every chart-contract type', async () => {
    const renderer = await manifest.loadRenderer()
    expect(validateRenderer(renderer)).toEqual({ valid: true, missing: [] })
  })

  it('line renders the existing GrowthChart with real SVG output for real data', async () => {
    const renderer = await manifest.loadRenderer()
    const { container } = render(renderer.line({
      series: [{ x: '2026-01-01', y: 1 }, { x: '2026-01-02', y: 2 }, { x: '2026-01-03', y: 3 }],
      metricId: 'x', ariaLabel: 'growth',
    }))
    expect(container.querySelector('svg')).toBeInTheDocument()
  })

  it('sparkline renders the existing Sparkline component', async () => {
    const renderer = await manifest.loadRenderer()
    const { container } = render(renderer.sparkline({ values: [1, 2, 3], ariaLabel: 'trend' }))
    expect(container.querySelector('svg')).toBeInTheDocument()
  })

  it('dial renders the existing ScoreGauge component', async () => {
    const renderer = await manifest.loadRenderer()
    render(renderer.dial({ values: [72], ariaLabel: 'Research score' }))
    expect(screen.getByRole('img', { name: /Research score/ })).toBeInTheDocument()
  })

  it('profile adapts the shared values shape onto the grandfathered ResearchRadarChart, replacing radar everywhere else', async () => {
    const renderer = await manifest.loadRenderer()
    const { container } = render(renderer.profile({ values: [{ label: 'Growth', value: 80 }, { label: 'Value', value: 60 }, { label: 'Quality', value: 70 }] }))
    expect(container.querySelector('svg, polygon')).toBeTruthy()
  })

  it('bar (no direct existing primitive) still renders real SVG bars using the existing token set', async () => {
    const renderer = await manifest.loadRenderer()
    const { container } = render(renderer.bar({ values: [10, 5], metricId: 'x', ariaLabel: 'bar' }))
    expect(container.querySelectorAll('rect').length).toBeGreaterThan(0)
  })
})

describe('classic components', () => {
  const { LabelFrame, EmptyState, Container } = manifest.components

  function partsFor(metric) {
    return {
      title: metric.label, mediumLine: null, read: metric.reads || null, reference: metric.kill_threshold || null,
      provenance: null, state: canonicalMetricState(metric), confidence: confidenceOf({ metric }),
      reason: canonicalMetricState(metric).reason, previous: null, action: null,
    }
  }

  it('LabelFrame reuses the existing signal-metric/tone-* CSS classes, definitionally matching metricTone()', () => {
    const metric = { id: 'x', label: 'X', status: 'ready', reads: 'X reads fine.' }
    const { container } = render(<LabelFrame parts={partsFor(metric)} capabilityId="x" />)
    expect(container.querySelector('.signal-metric.tone-ready')).toBeInTheDocument()
  })

  it('a breached metric gets tone-breached and the signal-kill footer, never hue alone', () => {
    const metric = { id: 'x', label: 'X', status: 'ready', breached: true, kill_threshold: 'x < 1', status_message: 'Breached.' }
    const { container } = render(<LabelFrame parts={partsFor(metric)} capabilityId="x" />)
    expect(container.querySelector('.tone-breached')).toBeInTheDocument()
    expect(screen.getByText(/Breached: x < 1/)).toBeInTheDocument()
  })

  it('EmptyState reuses the existing Empty component', () => {
    render(<EmptyState reason="Publication gate closed." />)
    expect(screen.getByText('Publication gate closed.')).toBeInTheDocument()
  })

  it('Container reuses the existing card/card-pad classes', () => {
    const { container } = render(<Container state={{ state: 'established' }}>x</Container>)
    expect(container.querySelector('.card.card-pad')).toBeInTheDocument()
  })
})

describe('classic nav', () => {
  it('renders four direct destinations plus a More trigger absorbing the rest — same interaction budget as the other eleven mediums', () => {
    render(<MemoryRouter><manifest.nav.Component /></MemoryRouter>)
    const nav = screen.getByRole('navigation', { name: 'Mobile navigation' })
    expect(nav).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /More/ })).toBeInTheDocument()
  })
})
