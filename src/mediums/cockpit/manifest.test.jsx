import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import manifest from './manifest.js'
import { validateRenderer, CHART_TYPES } from '../core/chartContract.js'
import { canonicalMetricState, confidenceOf } from '../core/states.js'
import { isMediumImplemented, loadMedium } from '../registry.js'

describe('cockpit manifest', () => {
  it('declares the required shape', () => {
    expect(manifest.id).toBe('cockpit')
    expect(manifest.colorScheme).toBe('dark')
    expect(manifest.acceptsAccent).toBe(false)
    expect(manifest.entry).toBeNull() // DESIGN.md: no entry, no fake boot sequence
    expect(manifest.nav.model).toBe('bottom')
    expect(manifest.nav.settingsAffordance).toBe(true)
  })

  it('is now discoverable through the registry glob', () => {
    expect(isMediumImplemented('cockpit')).toBe(true)
  })

  it('loads through loadMedium() and matches the static import', async () => {
    const loaded = await loadMedium('cockpit')
    expect(loaded.id).toBe('cockpit')
  })

  it('implements every chart-contract type', async () => {
    const renderer = await manifest.loadRenderer()
    const result = validateRenderer(renderer)
    expect(result).toEqual({ valid: true, missing: [] })
  })

  it('the dial type renders a labeled scale, not a bare gauge', async () => {
    const renderer = await manifest.loadRenderer()
    const { container } = render(renderer.dial({ values: [0.6], domain: [0, 1], ariaLabel: 'test dial' }))
    const labels = container.querySelectorAll('text')
    expect(labels.length).toBeGreaterThan(0)
  })

  it('never implements radar', () => {
    expect(CHART_TYPES).not.toContain('radar')
  })
})

describe('cockpit components', () => {
  const { LabelFrame, EmptyState, Skeleton, ProvenanceStrip } = manifest.components

  it('LabelFrame renders the wall-label parts, breach tone included', () => {
    const metric = { id: 'deflated_sharpe', label: 'Deflated Sharpe', status: 'ready', breached: true, kill_threshold: 'DSR < 0.95', reads: 'Deflated Sharpe ratio.' }
    const parts = {
      title: metric.label, mediumLine: null, read: metric.reads, reference: metric.kill_threshold,
      provenance: 'signal_metrics.json', state: canonicalMetricState(metric), confidence: confidenceOf({ metric }),
      reason: canonicalMetricState(metric).reason, action: null,
    }
    render(<LabelFrame parts={parts} capabilityId="metric.report.deflated-sharpe" />)
    expect(screen.getByText('Deflated Sharpe')).toBeInTheDocument()
    expect(screen.getByText('LIMIT · DSR < 0.95')).toBeInTheDocument()
  })

  it('EmptyState prints the reason, never a spinner-only state', () => {
    render(<EmptyState reason="No data yet." />)
    expect(screen.getByRole('alert')).toHaveTextContent('No data yet.')
  })

  it('Skeleton uses a status role, not raw text "Loading"', () => {
    render(<Skeleton />)
    expect(screen.getByRole('status')).toBeInTheDocument()
  })

  it('ProvenanceStrip renders live counts, never hardcoded', () => {
    render(<ProvenanceStrip ready={44} breached={9} total={64} liveDays={18} modelVersion="3.2.0" promotionText="No signal has been promoted." />)
    const strip = screen.getByTestId('provenance-strip')
    expect(strip).toHaveTextContent('44 READY')
    expect(strip).toHaveTextContent('9 BREACHED')
    expect(strip).toHaveTextContent('18D LIVE')
    expect(strip).toHaveTextContent('No signal has been promoted.')
  })
})
