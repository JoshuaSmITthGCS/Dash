import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import SwingScreen from './SwingScreen'
import { useData } from '../lib/useData'
import { usePreferences } from '../lib/PreferencesContext.jsx'

vi.mock('../lib/useData', async (importOriginal) => ({ ...(await importOriginal()), useData: vi.fn() }))
vi.mock('../lib/PreferencesContext.jsx', () => ({ usePreferences: vi.fn() }))

beforeEach(() => usePreferences.mockReturnValue({ preferences: { mobileResearchView: 'compact' } }))

const leg = (z, applied = true, weight = 0.2) => ({ z, applied, weight, contribution: z * weight })

const row = (overrides = {}) => ({
  rank: 1, ticker: 'AAA', name: 'Alpha Inc', sector: 'Technology',
  composite_z: 1.42, percentile: 99.1, coverage: 0.7, market_cap: 8e9, price: 40,
  median_dollar_volume_60d: 4.2e8, eligibility: true, current_membership: true,
  legs: {
    pead_drift: leg(null, false, 0.3),
    analyst_revision: leg(1.9, true, 0.25),
    high_volume_premium: leg(1.1, true, 0.2),
    high_52w_proximity: leg(0.8, true, 0.15),
    short_term_reversal: leg(-0.4, true, 0.1),
  },
  dropped_legs: ['pead_drift'],
  short_interest: { suppressed: false, reasons: [], short_percent_of_float: 0.02, days_to_cover: 1.4 },
  pead_status: 'NO_SURPRISE_HISTORY',
  raw_factors: { return_20d: 6.4 },
  reason_codes: [],
  ...overrides,
})

const payload = (overrides = {}) => ({
  status: 'success', schema_version: '1.0.0', model_version: 'swing-v1.0.0',
  config_version: 'screens-v2.0.0',
  weights: {
    pead_drift: 0.3, analyst_revision: 0.25, high_volume_premium: 0.2,
    high_52w_proximity: 0.15, short_term_reversal: 0.1,
  },
  leg_coverage: {
    pead_drift: 0, analyst_revision: 0.99, high_volume_premium: 1,
    high_52w_proximity: 1, short_term_reversal: 0.98,
  },
  evidence: {
    pead_drift: {
      label: 'Post-earnings drift (SUE)', horizon: '1-8 weeks', direction: 'continuation of the surprise',
      citation: 'Bernard & Thomas, Journal of Accounting Research 1989', effect: 'CARs drift with the surprise',
      caveat: 'Strongest in small and illiquid names.',
    },
    analyst_revision: {
      label: 'Analyst revision (change, not level)', horizon: '1 week to 6 months', direction: 'direction of the revision',
      citation: 'Jegadeesh, Kim, Krische & Lee 2004', effect: 'The change in consensus predicts',
      caveat: 'The asymmetry favours the short side.',
    },
  },
  negative_screen: {
    label: 'Short interest / days-to-cover (negative screen)',
    citation: 'Boehmer, Jones & Zhang 2008', effect: '-1.16% over 20 trading days',
    caveat: 'A long-only book cannot take the short leg.',
  },
  decay_haircut: { out_of_sample: 0.26, post_publication: 0.58, source: 'McLean & Pontiff 2016', note: 'Decay is worst in illiquid names.' },
  thresholds: { reversal_minimum_dollar_volume: 25_000_000 },
  scored_count: 860, eligible_count: 779, suppressed_count: 55, published_suppressed_count: 23,
  results: [row()],
  ...overrides,
})

const renderScreen = () => render(<MemoryRouter><SwingScreen /></MemoryRouter>)

describe('SwingScreen', () => {
  it('ranks rows with every leg shown separately rather than one opaque score', () => {
    useData.mockReturnValue({ data: payload(), loading: false, error: null })

    renderScreen()

    expect(screen.getByRole('heading', { name: /Swing signals/ })).toBeVisible()
    expect(screen.getAllByText('AAA').length).toBeGreaterThan(0)
    expect(screen.getByRole('columnheader', { name: 'Revision' })).toBeVisible()
    expect(screen.getByRole('columnheader', { name: 'Reversal' })).toBeVisible()
    expect(screen.getAllByText('+1.90').length).toBeGreaterThan(0)
    expect(screen.getAllByText('-0.40').length).toBeGreaterThan(0)
  })

  it('shows a leg that did not resolve as absent, never as a zero', () => {
    useData.mockReturnValue({ data: payload(), loading: false, error: null })

    const { container } = renderScreen()

    const missing = container.querySelector('.swing-leg-missing')
    expect(missing).toHaveTextContent('–')
    expect(missing.getAttribute('title')).toMatch(/redistributed/)
  })

  it('states each leg’s citation, horizon and how much of the universe it resolved on', () => {
    useData.mockReturnValue({ data: payload(), loading: false, error: null })

    renderScreen()

    expect(screen.getByText(/Bernard & Thomas/)).toBeVisible()
    expect(screen.getByText('1-8 weeks · continuation of the surprise')).toBeVisible()
    // The 30%-weighted leg resolving on nothing is the single most important caveat on the
    // page, so it is stated rather than hidden behind an empty column.
    expect(screen.getByText('resolved on 0% of the universe')).toHaveClass('thin')
  })

  it('publishes the decay haircut beside the gross effect sizes', () => {
    useData.mockReturnValue({ data: payload(), loading: false, error: null })

    renderScreen()

    expect(screen.getByText(/58% lower after publication/)).toBeVisible()
    expect(screen.getByText(/McLean & Pontiff 2016/)).toBeVisible()
  })

  it('keeps a short-interest suppression visible with its reason instead of dropping it', () => {
    const suppressed = row({
      ticker: 'SHORTED', rank: 2, eligibility: false, percentile: null,
      short_interest: { suppressed: true, reasons: ['14.6% of float short', '6.8 days to cover'] },
      reason_codes: ['SHORT_INTEREST_SUPPRESSED'],
    })
    useData.mockReturnValue({ data: payload({ results: [row(), suppressed] }), loading: false, error: null })

    const { container } = renderScreen()

    expect(screen.getAllByText(/14.6% of float short/).length).toBeGreaterThan(0)
    expect(screen.getAllByText('SHORT_INTEREST_SUPPRESSED').length).toBeGreaterThan(0)
    expect(container.querySelectorAll('.swing-row-suppressed')).toHaveLength(1)
  })

  it('filters the suppressed names out on request', () => {
    const suppressed = row({
      ticker: 'SHORTED', rank: 2, eligibility: false,
      short_interest: { suppressed: true, reasons: ['14.6% of float short'] },
      reason_codes: ['SHORT_INTEREST_SUPPRESSED'],
    })
    useData.mockReturnValue({ data: payload({ results: [row(), suppressed] }), loading: false, error: null })

    renderScreen()
    fireEvent.change(screen.getAllByLabelText('Short interest')[0], { target: { value: 'exclude' } })

    expect(screen.queryByText('SHORTED')).toBeNull()
    expect(screen.getAllByText('AAA').length).toBeGreaterThan(0)
  })

  it('reports the reason code when the screen has nothing to publish', () => {
    useData.mockReturnValue({
      data: { status: 'unavailable', reason_code: 'INSUFFICIENT_PRICE_HISTORY', results: [] },
      loading: false, error: null,
    })

    renderScreen()

    expect(screen.getByText(/INSUFFICIENT_PRICE_HISTORY/)).toBeVisible()
  })
})
