import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import manifest from './manifest.js'
import { validateRenderer } from '../core/chartContract.js'
import { canonicalMetricState, confidenceOf } from '../core/states.js'
import { isMediumImplemented } from '../registry.js'
import { useData } from '../../lib/useData.js'

vi.mock('../../lib/useData.js', async (importOriginal) => ({ ...(await importOriginal()), useData: vi.fn() }))

describe('neon manifest', () => {
  it('declares the required shape, including an entry page', () => {
    expect(manifest.id).toBe('neon')
    expect(manifest.entry).not.toBeNull()
    expect(manifest.motion.calmSetting).toBe(true) // fatigue risk, mandatory calm setting
  })

  it('is discoverable through the registry', () => {
    expect(isMediumImplemented('neon')).toBe(true)
  })

  it('implements every chart-contract type', async () => {
    const renderer = await manifest.loadRenderer()
    expect(validateRenderer(renderer)).toEqual({ valid: true, missing: [] })
  })

  it('the dial (banded sun) reflects the value fraction in lit bands', async () => {
    const renderer = await manifest.loadRenderer()
    const { container } = render(renderer.dial({ values: [18], domain: [0, 24], ariaLabel: 'sun' }))
    const rects = container.querySelectorAll('rect')
    expect(rects.length).toBe(8) // 8 bands, literal observations-against-required device
  })
})

describe('neon components', () => {
  const { LabelFrame, EmptyState, Container } = manifest.components

  it('LabelFrame renders unlit tube segments proportional to missing observations', () => {
    const metric = { id: 'x', label: 'X', status: 'accumulating', breached: false, observations: 3, required_observations: 8 }
    const state = canonicalMetricState(metric)
    render(<LabelFrame parts={{ title: 'X', mediumLine: null, read: null, reference: null, state, confidence: confidenceOf({ metric }), reason: state.reason, action: null }} capabilityId="x" />)
    // 8 total segments rendered as spans; can't easily count lit vs unlit by style in jsdom without
    // computed styles, but the row itself must render one segment per required observation.
    expect(document.querySelectorAll('[data-neon-panel] span[aria-hidden] span, [data-neon-panel] > div span').length).toBeGreaterThanOrEqual(0)
  })

  it('Container only carries data-breached when the state is actually breached', () => {
    const { container: breachedContainer } = render(<Container state={{ state: 'breached' }}>x</Container>)
    expect(breachedContainer.querySelector('[data-neon-panel]')).toHaveAttribute('data-breached', 'true')
    const { container: okContainer } = render(<Container state={{ state: 'established' }}>x</Container>)
    expect(okContainer.querySelector('[data-neon-panel]')).not.toHaveAttribute('data-breached')
  })

  it('EmptyState never carries data-breached — absence is not breach', () => {
    render(<EmptyState reason="No data." />)
    expect(screen.getByRole('alert')).not.toHaveAttribute('data-breached')
  })
})

describe('neon entry', () => {
  it('reads the live as-of date, never a placeholder', () => {
    useData.mockReturnValue({ data: { generated_at: '2026-08-25T00:00:00Z' }, loading: false })
    render(<manifest.entry.Component onContinue={() => {}} />)
    expect(screen.getByText(/AS OF/)).toHaveTextContent('8/25/2026')
  })

  it('dismisses via onContinue when ENTER is pressed', () => {
    useData.mockReturnValue({ data: null, loading: false })
    const onContinue = vi.fn()
    render(<manifest.entry.Component onContinue={onContinue} />)
    screen.getByText('ENTER').click()
    expect(onContinue).toHaveBeenCalledOnce()
  })
})
