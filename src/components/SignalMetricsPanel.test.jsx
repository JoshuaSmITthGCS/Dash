import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import SignalMetricsPanel from './SignalMetricsPanel'
import { defaultOpenGroups, metricTone, splitBySampleRequirement } from '../lib/signalMetrics'
import published from '../../public/data/validation/signal_metrics.json'

const report = {
  groups: [
    { id: 'signal', letter: 'A', title: 'Signal quality', summary: 'Does it predict.', requires_live_sample: false },
    { id: 'distribution', letter: 'E', title: 'Distribution shape', summary: 'Tails.', requires_live_sample: true },
  ],
  cadence: [{ frequency: 'Weekly', items: 'Rolling IC, turnover' }],
  live_sample: { days: 18, refreshes: 21, first_date: '2026-07-20', last_date: '2026-08-13' },
  summary: { total: 3, ready: 1, breached: 1, sample_free_total: 2, sample_free_ready: 1, needs_sample_total: 1 },
  metrics: [
    {
      id: 'rank_ic_21d', group: 'signal', label: 'Rank IC (21d)', value: 0.031, display: '0.031',
      reads: 'Spearman of score against forward return.', kill_threshold: 'Mean IC < 0.02',
      breached: false, cadence: 'Weekly', requires_live_sample: false, status: 'ready',
      observations: 58, required_observations: null, backtest_reference: null, detail: null,
    },
    {
      id: 'per_leg_ic', group: 'signal', label: 'Per-leg IC', value: 2, display: '2 of 8 legs below 0.02',
      reads: 'Which legs predict alone.', kill_threshold: 'Any leg IC below 0.02',
      breached: true, cadence: 'Monthly', requires_live_sample: false, status: 'ready',
      observations: 58, backtest_reference: null,
    },
    {
      id: 'omega', group: 'distribution', label: 'Omega ratio', value: null, display: null,
      reads: 'Gains over losses against cash.', kill_threshold: null, breached: false,
      cadence: 'Quarterly', requires_live_sample: true, status: 'accumulating',
      status_message: '18 live days of 120.', observations: 18, required_observations: 120,
      backtest_reference: 1.24,
    },
  ],
}

describe('signal metric splitting', () => {
  it('separates what backtest data answers from what needs a live sample', () => {
    const [now, sample] = splitBySampleRequirement(report)
    expect(now.total).toBe(2)
    expect(now.groups.map((group) => group.id)).toEqual(['signal'])
    expect(sample.total).toBe(1)
    expect(sample.groups.map((group) => group.id)).toEqual(['distribution'])
    // An empty group must not render as a heading with nothing under it.
    expect(now.groups.some((group) => group.metrics.length === 0)).toBe(false)
  })

  it('counts only metrics that actually carry a reading', () => {
    const [now, sample] = splitBySampleRequirement(report)
    expect(now.read).toBe(2)
    expect(now.breached).toBe(1)
    expect(sample.read).toBe(0)
  })

  it('ranks a breached threshold above a healthy status', () => {
    expect(metricTone({ status: 'ready', breached: true })).toBe('breached')
    expect(metricTone({ status: 'ready', breached: false })).toBe('ready')
    expect(metricTone({ status: 'accumulating' })).toBe('accumulating')
    expect(metricTone({ status: 'awaiting_input' })).toBe('pending')
  })

  it('opens any group holding a breached metric so it is never hidden', () => {
    const [now] = splitBySampleRequirement(report)
    expect(defaultOpenGroups(now).has('signal')).toBe(true)
  })
})

describe('SignalMetricsPanel', () => {
  it('shows both buckets with their own progress counts', () => {
    render(<SignalMetricsPanel report={report} />)
    expect(screen.getByText('Computable now')).toBeInTheDocument()
    expect(screen.getByText('Needs live sample')).toBeInTheDocument()
    expect(screen.getByText(/18 live days \(2026-07-20 to 2026-08-13\) across 21 recorded refreshes/)).toBeInTheDocument()
  })

  it('marks a breached kill threshold rather than reporting the value alone', () => {
    render(<SignalMetricsPanel report={report} />)
    expect(screen.getByText('2 of 8 legs below 0.02')).toBeInTheDocument()
    expect(screen.getByText(/Breached: Any leg IC below 0.02/)).toBeInTheDocument()
  })

  it('labels a backtest number on a sample-gated metric as not a live reading', () => {
    render(<SignalMetricsPanel report={report} />)
    const omega = screen.getByText('Omega ratio').closest('article')
    expect(within(omega).getByText(/Not a live reading/)).toBeInTheDocument()
    expect(within(omega).getByText(/18 live days of 120/)).toBeInTheDocument()
  })

  it('renders the artifact the pipeline actually publishes', () => {
    // Guards the contract between pipeline/signal_metrics.py and this panel: a renamed
    // field there would otherwise show up as a silently empty section here.
    render(<SignalMetricsPanel report={published} />)
    expect(screen.getByText('Distribution shape')).toBeInTheDocument()
    // Cost splits across both buckets: breakeven alpha is backtest arithmetic, fill quality
    // is not. The group heading appears under each, scoped by its bucket.
    expect(screen.getAllByText('Cost and capacity')).toHaveLength(2)
    const [now, sample] = splitBySampleRequirement(published)
    expect(now.total + sample.total).toBe(published.metrics.length)
    expect(now.read).toBeGreaterThan(0)
  })

  it('draws a bullet chart only for metrics the pipeline gave a real numeric threshold', () => {
    render(<SignalMetricsPanel report={published} />)
    // feature_psi carries a threshold but no value yet (awaiting its live sample) --
    // rightly excluded, since there is nothing to draw a bullet against.
    const withThreshold = published.metrics.filter(
      (metric) => metric.kill_threshold_value != null && typeof metric.value === 'number',
    )
    const withoutThreshold = published.metrics.filter(
      (metric) => metric.kill_threshold_value == null && metric.kill_threshold,
    )
    expect(withThreshold.length).toBeGreaterThan(0)
    expect(withoutThreshold.length).toBeGreaterThan(0) // e.g. quantile_spread, per_leg_ic
    withThreshold.forEach((metric) => {
      const card = screen.getByText(metric.label).closest('article')
      expect(card.querySelector('.signal-metric-bullet')).not.toBeNull()
    })
    withoutThreshold.forEach((metric) => {
      const card = screen.getByText(metric.label).closest('article')
      expect(card.querySelector('.signal-metric-bullet')).toBeNull()
    })
  })

  it('says which command publishes the artifact when it is missing', () => {
    render(<SignalMetricsPanel report={null} error={{ message: 'not found' }} />)
    expect(screen.getByText(/pipeline\/signal_metrics.py/)).toBeInTheDocument()
  })
})
