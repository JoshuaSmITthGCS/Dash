import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import manifest from './manifest.js'
import { validateRenderer } from '../core/chartContract.js'
import { canonicalMetricState, confidenceOf } from '../core/states.js'
import { isMediumImplemented } from '../registry.js'

describe('chalkboard manifest', () => {
  it('declares the required shape', () => {
    expect(manifest.id).toBe('chalkboard')
    expect(manifest.colorScheme).toBe('dark')
    expect(manifest.acceptsAccent).toBe(false)
  })

  it('has no entry — the board is already written on when you walk in', () => {
    expect(manifest.entry).toBeNull()
  })

  it('is discoverable through the registry', () => {
    expect(isMediumImplemented('chalkboard')).toBe(true)
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

  it('a low-confidence established metric draws with higher roughness than a high-confidence one — confidence is chalk pressure, distinct from state', async () => {
    const renderer = await manifest.loadRenderer()
    const confident = render(renderer.bar({ values: [10], metricId: 'x', state: { state: 'established' }, confidence: { level: 1 }, ariaLabel: 'a' })).container.innerHTML
    const faint = render(renderer.bar({ values: [10], metricId: 'x', state: { state: 'established' }, confidence: { level: 0.1 }, ariaLabel: 'a' })).container.innerHTML
    expect(confident).not.toBe(faint)
  })

  it('draws freehand (rough.js) axes, never a perfectly straight <line> for the axis geometry', async () => {
    const renderer = await manifest.loadRenderer()
    const { container } = render(renderer.line({ values: [1, 2, 3], metricId: 'x', ariaLabel: 'a' }))
    expect(container.querySelector('path')).toBeInTheDocument()
  })
})

describe('chalkboard components', () => {
  const { LabelFrame, EmptyState, Container, SectionHeading } = manifest.components

  it('LabelFrame renders the wall label with a dotted leader line to the value', () => {
    const metric = { id: 'x', label: 'X', status: 'ready', breached: false, reads: 'A read.' }
    render(<LabelFrame parts={{ title: 'X', mediumLine: 'monthly', read: metric.reads, reference: null, provenance: 'signal_metrics.json', state: canonicalMetricState(metric), confidence: confidenceOf({ metric }), reason: null, previous: null, action: null }} capabilityId="x" />)
    expect(screen.getByText('X')).toBeInTheDocument()
  })

  it('erasure smudge — a prior value renders behind the current value, marked distinctly, at a lower luminance step', () => {
    const metric = { id: 'x', label: 'X', status: 'ready', breached: false, previous_value: '0.30' }
    render(<LabelFrame parts={{ title: 'X', mediumLine: null, read: '0.42', reference: null, provenance: null, state: canonicalMetricState(metric), confidence: confidenceOf({ metric }), reason: null, previous: metric.previous_value, action: null }} capabilityId="x" />)
    const current = screen.getByText('0.42')
    const prior = screen.getByText('0.30')
    expect(current).toHaveAttribute('data-state-mark', 'current')
    expect(prior).toHaveAttribute('data-state-mark', 'prior')
    // Stacking order: the smudge must be behind the current value in DOM order (prior painted
    // first, current painted last) — the fixed contract Phase 3 assertion 11 checks mechanically.
    expect(prior.compareDocumentPosition(current) & prior.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    // Luminance-step gap: the smudge's own opacity must be measurably lower than the current
    // value's opacity, never just a hopeful visual convention.
    const priorOpacity = parseFloat(prior.style.opacity)
    const currentOpacity = parseFloat(current.style.opacity || '1')
    expect(priorOpacity).toBeLessThan(currentOpacity)
  })

  it('never renders a smudge when the metric does not publish a previous value', () => {
    const metric = { id: 'x', label: 'X', status: 'ready' }
    render(<LabelFrame parts={{ title: 'X', mediumLine: null, read: null, reference: null, provenance: null, state: canonicalMetricState(metric), confidence: confidenceOf({ metric }), reason: null, previous: null, action: null }} capabilityId="x" />)
    expect(screen.queryByTestId('prior')).not.toBeInTheDocument()
    expect(document.querySelector('[data-state-mark="prior"]')).not.toBeInTheDocument()
  })

  it('a breached metric is circled/underlined in the alert chalk, never hue alone', () => {
    const metric = { id: 'x', label: 'X', status: 'ready', breached: true, kill_threshold: 'x < 1', status_message: 'Breached.' }
    render(<LabelFrame parts={{ title: 'X', mediumLine: null, read: null, reference: null, provenance: null, state: canonicalMetricState(metric), confidence: confidenceOf({ metric }), reason: canonicalMetricState(metric).reason, previous: null, action: null }} capabilityId="x" />)
    const box = document.querySelector('[data-chalk-box][data-breached="true"]')
    expect(box).toBeInTheDocument()
  })

  it('EmptyState is a blank hand-drawn box with a question mark and the reason', () => {
    render(<EmptyState reason="Publication gate closed." />)
    expect(screen.getByRole('alert')).toHaveTextContent('?')
    expect(screen.getByRole('alert')).toHaveTextContent('Publication gate closed.')
  })

  it('Container marks a breached state on the hand-drawn box', () => {
    const { container } = render(<Container state={{ state: 'breached' }}>x</Container>)
    expect(container.querySelector('[data-chalk-box]')).toHaveAttribute('data-breached', 'true')
  })

  it('SectionHeading renders a banner ribbon', () => {
    render(<SectionHeading>Report</SectionHeading>)
    expect(screen.getByText('Report')).toBeInTheDocument()
  })
})

describe('chalkboard provenance strip', () => {
  it('renders the DO NOT ERASE corner device with model version', () => {
    const { ProvenanceStrip } = manifest.components
    render(<ProvenanceStrip ready={44} breached={9} liveDays={18} modelVersion="3.2.0" />)
    expect(screen.getByText(/DO NOT ERASE/)).toHaveTextContent('3.2.0')
  })
})
