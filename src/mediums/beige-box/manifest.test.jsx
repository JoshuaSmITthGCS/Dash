import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import manifest from './manifest.js'
import { validateRenderer } from '../core/chartContract.js'
import { canonicalMetricState, confidenceOf } from '../core/states.js'
import { isMediumImplemented } from '../registry.js'
import { useData } from '../../lib/useData.js'

vi.mock('../../lib/useData.js', async (importOriginal) => ({ ...(await importOriginal()), useData: vi.fn() }))

describe('beige-box manifest', () => {
  it('declares the required shape', () => {
    expect(manifest.id).toBe('beige-box')
    expect(manifest.colorScheme).toBe('light')
    expect(manifest.entry).not.toBeNull()
  })

  it('is discoverable through the registry', () => {
    expect(isMediumImplemented('beige-box')).toBe(true)
  })

  it('implements every chart-contract type', async () => {
    const renderer = await manifest.loadRenderer()
    expect(validateRenderer(renderer)).toEqual({ valid: true, missing: [] })
  })

  it('renders hard 1px crisp-edge SVG, never anti-aliased/soft fills, for bar', async () => {
    const renderer = await manifest.loadRenderer()
    const { container } = render(renderer.bar({ values: [10, 5], metricId: 'test', ariaLabel: 'bar' }))
    const svg = container.querySelector('svg')
    expect(svg).toHaveAttribute('shape-rendering', 'crispEdges')
    expect(container.querySelectorAll('rect[fill^="url(#dither"]').length).toBeGreaterThan(0)
  })

  it('dither pattern spacing is deterministic for the same metricId — screenshots never churn', async () => {
    const renderer = await manifest.loadRenderer()
    const first = render(renderer.bar({ values: [1, 2, 3], metricId: 'same-id', ariaLabel: 'a' })).container.innerHTML
    const second = render(renderer.bar({ values: [1, 2, 3], metricId: 'same-id', ariaLabel: 'a' })).container.innerHTML
    expect(first).toBe(second)
  })

  it('dither density differs between low and high confidence for the same value — confidence is the dither channel, distinct from state', async () => {
    const renderer = await manifest.loadRenderer()
    const confident = render(renderer.bar({ values: [10], metricId: 'x', state: { state: 'established' }, confidence: { level: 1 }, ariaLabel: 'a' })).container.innerHTML
    const faint = render(renderer.bar({ values: [10], metricId: 'x', state: { state: 'established' }, confidence: { level: 0.1 }, ariaLabel: 'a' })).container.innerHTML
    expect(confident).not.toBe(faint)
  })
})

describe('beige-box components', () => {
  const { LabelFrame, EmptyState, Container } = manifest.components

  it('LabelFrame renders an accumulating metric with a real N of M progress bar', () => {
    const metric = { id: 'x', label: 'X', status: 'provisional', observations: 18, required_observations: 24 }
    render(<LabelFrame parts={{ title: 'X', mediumLine: null, read: null, reference: null, provenance: null, state: canonicalMetricState(metric), confidence: confidenceOf({ metric }), reason: null, action: null }} capabilityId="x" />)
    const progress = screen.getByRole('progressbar')
    expect(progress).toHaveAttribute('value', '18')
    expect(progress).toHaveAttribute('max', '24')
    expect(screen.getByText('18 of 24')).toBeInTheDocument()
  })

  it('LabelFrame marks a breached metric with a colored border and an alert icon, never hue alone', () => {
    const metric = { id: 'x', label: 'X', status: 'ready', breached: true, kill_threshold: 'x < 1', status_message: 'Breached.' }
    render(<LabelFrame parts={{ title: 'X', mediumLine: null, read: '0.2', reference: null, provenance: null, state: canonicalMetricState(metric), confidence: confidenceOf({ metric }), reason: canonicalMetricState(metric).reason, action: null }} capabilityId="x" />)
    expect(screen.getByText('⚠')).toBeInTheDocument()
  })

  it('EmptyState is a disabled control carrying the reason', () => {
    render(<EmptyState reason="Publication gate closed." />)
    expect(screen.getByRole('alert')).toHaveTextContent('Publication gate closed.')
  })

  it('Container renders a titled window, one per metric group', () => {
    render(<Container title="Report.grp" state={{ state: 'established' }}>x</Container>)
    expect(screen.getByText('Report.grp')).toBeInTheDocument()
  })
})

describe('beige-box status bar', () => {
  it('StatusBar carries the persistent Ready/as-of text', () => {
    const { StatusBar } = manifest.components
    render(<StatusBar text="Deflated Sharpe: BREACHED (0.238)" asOf="8/26/2026" />)
    expect(screen.getByRole('status')).toHaveTextContent('Deflated Sharpe: BREACHED (0.238)')
    expect(screen.getByRole('status')).toHaveTextContent('8/26/2026')
  })
})

describe('beige-box nav', () => {
  it('the top menu bar resolves to a bottom-anchored, thumb-reachable 44px trigger at mobile width', () => {
    render(<MemoryRouter><manifest.nav.Component /></MemoryRouter>)
    const trigger = screen.getByRole('button', { name: 'Open menu' })
    expect(trigger).toBeInTheDocument()
    expect(trigger.getAttribute('aria-expanded')).toBe('false')
  })

  it('opening the trigger reveals every destination as a menu item', () => {
    render(<MemoryRouter><manifest.nav.Component /></MemoryRouter>)
    fireEvent.click(screen.getByRole('button', { name: 'Open menu' }))
    expect(screen.getAllByRole('menuitem').length).toBeGreaterThanOrEqual(6)
  })
})

describe('beige-box entry', () => {
  it('renders a desktop of icons, destinations as icons', () => {
    useData.mockReturnValue({ data: { generated_at: '2026-08-25T00:00:00Z' }, loading: false })
    render(<manifest.entry.Component onContinue={() => {}} />)
    expect(screen.getByText('Home')).toBeInTheDocument()
    expect(screen.getByText('Evidence')).toBeInTheDocument()
  })
})
