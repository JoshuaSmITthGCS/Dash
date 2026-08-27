import { readFileSync } from 'node:fs'
import path from 'node:path'
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import manifest from './manifest.js'
import { validateRenderer } from '../core/chartContract.js'
import { canonicalMetricState, confidenceOf } from '../core/states.js'
import { isMediumImplemented } from '../registry.js'

const tokensCss = readFileSync(path.join(import.meta.dirname, 'tokens.css'), 'utf8')

describe('ticker manifest', () => {
  it('declares the required shape', () => {
    expect(manifest.id).toBe('ticker')
    expect(manifest.entry).toBeNull()
    expect(manifest.motion.profile).toBe('governed-ticker')
    expect(manifest.motion.calmSetting).toBe(true) // fatigue risk, mandatory, never default
  })

  it('is discoverable through the registry', () => {
    expect(isMediumImplemented('ticker')).toBe(true)
  })

  it('implements every chart-contract type', async () => {
    const renderer = await manifest.loadRenderer()
    expect(validateRenderer(renderer)).toEqual({ valid: true, missing: [] })
  })
})

describe('ticker components', () => {
  const { LabelFrame, EmptyState, Container } = manifest.components

  it('LabelFrame renders a fixed-width status column with glyph + N/M', () => {
    const metric = { id: 'x', label: 'Momentum leg IC', status: 'accumulating', breached: false, observations: 17, required_observations: 24 }
    const state = canonicalMetricState(metric)
    render(<LabelFrame parts={{ title: metric.label, read: null, reference: null, state, confidence: confidenceOf({ metric }), reason: null, action: null }} capabilityId="x" />)
    expect(screen.getByTestId('status-column')).toHaveTextContent('17/24')
  })

  it('breach accent never shares the loss color token — the theme\'s own standing rule', () => {
    const breach = tokensCss.match(/--state-breach:\s*([^;]+);/)?.[1].trim()
    const loss = tokensCss.match(/--state-loss:\s*([^;]+);/)?.[1].trim()
    expect(breach).toBeTruthy()
    expect(loss).toBeTruthy()
    expect(breach).not.toBe(loss)
  })

  it('EmptyState uses the same row grammar as every other row (data-ticker-row), not a different widget', () => {
    render(<EmptyState reason="No data." />)
    expect(screen.getByRole('alert')).toHaveAttribute('data-ticker-row', 'true')
  })

  it('Container never renders a card — no radius/shadow styling hooks, just the row attribute', () => {
    const { container } = render(<Container state={{ state: 'established' }}>x</Container>)
    expect(container.firstChild).toHaveAttribute('data-ticker-row', 'true')
  })
})
