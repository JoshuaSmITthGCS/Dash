import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import manifest from './manifest.js'
import { validateRenderer } from '../core/chartContract.js'
import { canonicalMetricState, confidenceOf } from '../core/states.js'
import { isMediumImplemented } from '../registry.js'
import { useData } from '../../lib/useData.js'

vi.mock('../../lib/useData.js', async (importOriginal) => ({ ...(await importOriginal()), useData: vi.fn() }))

describe('poster manifest', () => {
  it('declares the required shape', () => {
    expect(manifest.id).toBe('poster')
    expect(manifest.colorScheme).toBe('light')
    expect(manifest.motion.profile).toBe('none') // print doesn't move
    expect(manifest.nav.model).toBe('top') // masthead
  })

  it('is discoverable through the registry', () => {
    expect(isMediumImplemented('poster')).toBe(true)
  })

  it('implements every chart-contract type', async () => {
    const renderer = await manifest.loadRenderer()
    expect(validateRenderer(renderer)).toEqual({ valid: true, missing: [] })
  })

  it('bar renders halftone dot density, not a flat fill', async () => {
    const renderer = await manifest.loadRenderer()
    const { container } = render(renderer.bar({ values: [10, 5], metricId: 'test-bar', ariaLabel: 'bar' }))
    expect(container.querySelectorAll('circle').length).toBeGreaterThan(0)
    expect(container.querySelectorAll('rect').length).toBe(0)
  })

  it('halftone dot geometry is deterministic for the same metricId', async () => {
    const renderer = await manifest.loadRenderer()
    const first = render(renderer.bar({ values: [10], metricId: 'same-id', ariaLabel: 'a' })).container.innerHTML
    const second = render(renderer.bar({ values: [10], metricId: 'same-id', ariaLabel: 'a' })).container.innerHTML
    expect(first).toBe(second)
  })
})

describe('poster components', () => {
  const { LabelFrame, EmptyState } = manifest.components

  it('LabelFrame applies a capped, seeded registration offset — never on the text layer', () => {
    const metric = { id: 'x', label: 'X', status: 'ready', breached: false, reads: 'A read.' }
    const parts = { title: 'X', mediumLine: null, read: metric.reads, reference: null, state: canonicalMetricState(metric), confidence: confidenceOf({ metric }), reason: null, action: null }
    const { getByTestId, getByText } = render(<LabelFrame parts={parts} capabilityId="metric.report.x" />)
    const ghost = getByTestId('registration-ghost')
    expect(ghost.style.transform).toMatch(/translate\(-?\d+(\.\d+)?px, -?\d+(\.\d+)?px\)/)
    // the offset magnitude never exceeds the 1.5px cap
    const [dx, dy] = ghost.style.transform.match(/-?\d+\.?\d*/g).map(Number)
    expect(Math.hypot(dx, dy)).toBeLessThanOrEqual(1.5 + 0.01)
    // the real read text has no transform applied to it
    const readText = getByText('A read.')
    expect(readText.style.transform).toBe('')
  })

  it('EmptyState reads as literally unprinted', () => {
    render(<EmptyState reason="No plate published." />)
    expect(screen.getByText('UNPRINTED')).toBeInTheDocument()
    expect(screen.getByText('No plate published.')).toBeInTheDocument()
  })
})

describe('poster entry', () => {
  it('carries an issue number and the live as-of date', () => {
    useData.mockReturnValue({ data: { generated_at: '2026-08-25T00:00:00Z' }, loading: false })
    render(<manifest.entry.Component onContinue={() => {}} />)
    expect(screen.getByText('ISSUE 01')).toBeInTheDocument()
    expect(screen.getByText(/AS OF/)).toHaveTextContent('8/25/2026')
  })
})
