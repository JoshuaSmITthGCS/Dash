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

// The table defaults to the plain columns. The per-leg scores, the composite z and the
// liquidity and short-interest detail are all still published, one click away, and these two
// helpers are how the tests reach them.
const showEveryNumber = () => fireEvent.click(screen.getByRole('button', { name: 'Every number' }))
const openMethod = () => { screen.getByText('How this works').closest('details').open = true }

describe('SwingScreen', () => {
  it('ranks rows with every leg shown separately rather than one opaque score', () => {
    useData.mockReturnValue({ data: payload(), loading: false, error: null })

    renderScreen()

    expect(screen.getByRole('heading', { name: /Swing signals/ })).toBeVisible()
    expect(screen.getAllByText('AAA').length).toBeGreaterThan(0)

    showEveryNumber()

    expect(screen.getByRole('columnheader', { name: 'Revisions' })).toBeVisible()
    expect(screen.getByRole('columnheader', { name: 'Pullback' })).toBeVisible()
    expect(screen.getAllByText('+1.90').length).toBeGreaterThan(0)
    expect(screen.getAllByText('-0.40').length).toBeGreaterThan(0)
  })

  it('shows a leg that did not resolve as absent, never as a zero', () => {
    useData.mockReturnValue({ data: payload(), loading: false, error: null })

    const { container } = renderScreen()
    showEveryNumber()

    const missing = container.querySelector('.swing-leg-missing')
    expect(missing).toHaveTextContent('–')
    // A missing leg contributes nothing at its declared weight - it does not rescale the
    // legs that resolved, which would put a thin row on a wider scale than a complete one.
    expect(missing.getAttribute('title')).toMatch(/contributes nothing at its declared weight/)
    expect(missing.getAttribute('title')).toMatch(/rather than rescaling/)
  })

  it('states each leg’s citation, horizon and how much of the universe it resolved on', () => {
    useData.mockReturnValue({ data: payload(), loading: false, error: null })

    renderScreen()
    openMethod()

    expect(screen.getByText(/Bernard & Thomas/)).toBeVisible()
    expect(screen.getByText('1-8 weeks · continuation of the surprise')).toBeVisible()
    // The 30%-weighted leg resolving on nothing is the single most important caveat on the
    // page, so it is stated rather than hidden behind an empty column.
    expect(screen.getByText('resolved on 0% of the universe')).toHaveClass('thin')
  })

  it('publishes the decay haircut beside the gross effect sizes', () => {
    useData.mockReturnValue({ data: payload(), loading: false, error: null })

    renderScreen()
    openMethod()

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
    showEveryNumber()

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

// ---------------------------------------------------------------------------
// Horizon tiers and sorting
// ---------------------------------------------------------------------------

const tierRow = (ticker, overrides = {}) => ({
  ...row(),
  ticker, name: `${ticker} Inc`,
  legs: {
    announcement_return: leg(1.5, true, 0.5),
    high_volume_premium: leg(0.9, true, 0.3),
    short_term_reversal: leg(-0.2, true, 0.2),
  },
  dropped_legs: [],
  ...overrides,
})

const tieredPayload = (overrides = {}) => payload({
  tier_order: ['F', 'M', 'S'],
  default_tier: 'S',
  alpha_assumption: { gross_bps_per_month: 8.8, note: 'Expected alpha is an assumption, not a measurement.' },
  evidence: {
    ...payload().evidence,
    announcement_return: {
      label: 'Announcement return (EAR)', horizon: '0 to +1 sessions', direction: 'continuation',
      citation: 'Brandt, Kishore, Santa-Clara & Venkatachalam', effect: '7.55%/yr abnormal',
      caveat: 'Needs no analyst estimate.',
    },
    high_volume_premium: {
      label: 'High-volume return premium', horizon: '1-4 weeks', direction: 'continuation',
      citation: 'Gervais, Kaniel & Mingelgrin 2001', effect: 'High volume appreciates',
      caveat: 'Investor recognition, not a risk premium.',
    },
    short_term_reversal: {
      label: 'Short-term reversal', horizon: '2-10 days', direction: 'contrarian',
      citation: 'Jegadeesh 1990', effect: '0.33%/month at t=1.37',
      caveat: 'The most capacity-constrained anomaly.',
    },
  },
  tiers: {
    F: {
      tier: 'F', label: '3-day swing', horizon_label: '2-5 sessions', target_hold_sessions: 3,
      weights: { announcement_return: 0.5, high_volume_premium: 0.3, short_term_reversal: 0.2 },
      decay_capture: { announcement_return: 1.0, high_volume_premium: 0.2, short_term_reversal: 0.6 },
      leg_coverage: { announcement_return: 0.33, high_volume_premium: 1, short_term_reversal: 1 },
      required_legs: ['announcement_return'], trigger_unresolved_count: 640,
      round_trips_per_year: 84, median_round_trip_bps: 4.4, expected_alpha_bps_per_period: 1.26,
      median_net_edge_bps: -3.1, book_clearing_cost: 0, book_count: 12,
      break_even_alpha_bps_per_month: 30.8,
      note: 'Event-triggered rather than a standing cross-sectional rank.',
      results: [
        tierRow('FAST', { rank: 1, composite_z: 2.1, economics_net_edge_bps: -3.1, economics_round_trip_bps: 4.4, economics_clears_cost: false, economics_expected_alpha_bps: 1.26 }),
        tierRow('CHEAP', { rank: 2, composite_z: 1.2, economics_net_edge_bps: 0.4, economics_round_trip_bps: 0.9, economics_clears_cost: true, economics_expected_alpha_bps: 1.26 }),
      ],
    },
    S: {
      tier: 'S', label: '13-week swing', horizon_label: '16-90 sessions', target_hold_sessions: 65,
      weights: { pead_drift: 0.3, announcement_return: 0.25, high_52w_proximity: 0.25, analyst_revision: 0.2 },
      decay_capture: { pead_drift: 0.62, announcement_return: 0.65, high_52w_proximity: 0.62, analyst_revision: 0.37 },
      leg_coverage: { pead_drift: 0.83, announcement_return: 0.95, high_52w_proximity: 1, analyst_revision: 0.99 },
      required_legs: [], trigger_unresolved_count: 0,
      round_trips_per_year: 3.9, median_round_trip_bps: 3.2, expected_alpha_bps_per_period: 27.24,
      median_net_edge_bps: 13.5, book_clearing_cost: 82, book_count: 82,
      break_even_alpha_bps_per_month: 1.7,
      note: 'The only tier whose cost budget is comfortable.',
      results: [tierRow('SLOW', { rank: 1, economics_net_edge_bps: 13.5, economics_round_trip_bps: 3.2, economics_clears_cost: true, economics_expected_alpha_bps: 16.76 })],
    },
  },
  ...overrides,
})

describe('SwingScreen horizon tiers', () => {
  it('opens on the default tier rather than the fast one', () => {
    useData.mockReturnValue({ data: tieredPayload(), loading: false, error: null })
    renderScreen()
    expect(screen.getByRole('tab', { name: /13-week swing/ })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tab', { name: /3-day swing/ })).toHaveAttribute('aria-selected', 'false')
    expect(screen.getAllByText('SLOW').length).toBeGreaterThan(0)
  })

  it('switching horizon changes which legs exist, not just the row order', () => {
    useData.mockReturnValue({ data: tieredPayload(), loading: false, error: null })
    renderScreen()
    showEveryNumber()
    // The slow book has an earnings column and no pullback column.
    expect(screen.getByRole('columnheader', { name: 'Earnings' })).toBeVisible()
    expect(screen.queryByRole('columnheader', { name: 'Pullback' })).toBeNull()

    fireEvent.click(screen.getByRole('tab', { name: /3-day swing/ }))

    // The fast book has a pullback column and no earnings column: its payoff has not landed yet.
    expect(screen.getByRole('columnheader', { name: 'Pullback' })).toBeVisible()
    expect(screen.queryByRole('columnheader', { name: 'Earnings' })).toBeNull()
    expect(screen.getAllByText('FAST').length).toBeGreaterThan(0)
    expect(screen.queryByText('SLOW')).toBeNull()
  })

  it('says plainly when the median name in a book does not clear its own cost', () => {
    useData.mockReturnValue({ data: tieredPayload(), loading: false, error: null })
    renderScreen()
    fireEvent.click(screen.getByRole('tab', { name: /3-day swing/ }))
    openMethod()
    expect(screen.getByText(/costs more to round trip than the tier assumes it earns/)).toBeVisible()
    expect(screen.getByText('0/12')).toBeVisible()
  })

  it('labels the alpha figure every net-edge number depends on as an assumption', () => {
    useData.mockReturnValue({ data: tieredPayload(), loading: false, error: null })
    renderScreen()
    openMethod()
    expect(screen.getByText(/an assumption, not a measurement/)).toBeVisible()
  })

  it('publishes how much of each leg’s payoff lands inside the tier’s own window', () => {
    useData.mockReturnValue({ data: tieredPayload(), loading: false, error: null })
    renderScreen()
    fireEvent.click(screen.getByRole('tab', { name: /3-day swing/ }))
    openMethod()
    expect(screen.getByText('100% of its payoff lands in this window')).toBeVisible()
    // The volume leg pays only a fifth of its total this fast, and is flagged for it.
    expect(screen.getByText('20% of its payoff lands in this window')).toHaveClass('thin')
  })

  it('states the event trigger and how many names it holds out', () => {
    useData.mockReturnValue({ data: tieredPayload(), loading: false, error: null })
    renderScreen()
    fireEvent.click(screen.getByRole('tab', { name: /3-day swing/ }))
    openMethod()
    expect(screen.getByText(/640 names are ranked but held out today/)).toBeVisible()
  })
})

describe('SwingScreen sorting', () => {
  const tickers = (container) =>
    [...container.querySelectorAll('tbody tr td:nth-child(2) b')].map((node) => node.textContent)

  it('sorts on any column and reverses on a second click', () => {
    useData.mockReturnValue({ data: tieredPayload(), loading: false, error: null })
    const { container } = renderScreen()
    fireEvent.click(screen.getByRole('tab', { name: /3-day swing/ }))
    expect(tickers(container)).toEqual(['FAST', 'CHEAP'])

    showEveryNumber()
    fireEvent.click(screen.getByRole('button', { name: /Composite/ }))
    expect(tickers(container)).toEqual(['FAST', 'CHEAP'])
    fireEvent.click(screen.getByRole('button', { name: /Composite/ }))
    expect(tickers(container)).toEqual(['CHEAP', 'FAST'])
  })

  it('sorts on net edge, which is the column that decides whether a name is worth trading', () => {
    useData.mockReturnValue({ data: tieredPayload(), loading: false, error: null })
    const { container } = renderScreen()
    fireEvent.click(screen.getByRole('tab', { name: /3-day swing/ }))

    fireEvent.click(screen.getByRole('button', { name: /Edge after cost/ }))

    // Best net edge first, so the one name that clears its cost is on top even though it
    // ranks second on the composite.
    expect(tickers(container)).toEqual(['CHEAP', 'FAST'])
  })

  it('marks the sorted column for assistive technology without changing its name', () => {
    useData.mockReturnValue({ data: tieredPayload(), loading: false, error: null })
    renderScreen()
    showEveryNumber()
    const header = screen.getByRole('columnheader', { name: 'Composite' })
    expect(header).toHaveAttribute('aria-sort', 'none')
    fireEvent.click(screen.getByRole('button', { name: /Composite/ }))
    expect(screen.getByRole('columnheader', { name: 'Composite' })).toHaveAttribute('aria-sort', 'descending')
  })

  it('sorts rows with no cost estimate last rather than treating them as cheapest', () => {
    const data = tieredPayload()
    data.tiers.F.results = [
      tierRow('KNOWN', { rank: 1, economics_round_trip_bps: 5.0, economics_net_edge_bps: -3.7 }),
      tierRow('UNKNOWN', { rank: 2, economics_round_trip_bps: null, economics_net_edge_bps: null }),
    ]
    useData.mockReturnValue({ data, loading: false, error: null })
    const { container } = renderScreen()
    fireEvent.click(screen.getByRole('tab', { name: /3-day swing/ }))
    showEveryNumber()

    fireEvent.click(screen.getByRole('button', { name: /Cost to trade/ }))

    expect(tickers(container)).toEqual(['KNOWN', 'UNKNOWN'])
  })
})

// ---------------------------------------------------------------------------
// Readability: the plain-language layer over the same numbers
// ---------------------------------------------------------------------------

describe('SwingScreen readability', () => {
  it('answers "is this list worth looking at" before showing any number', () => {
    useData.mockReturnValue({ data: tieredPayload(), loading: false, error: null })
    renderScreen()
    expect(screen.getByText(/65 trading sessions/)).toBeVisible()
    expect(screen.getByText(/82 of 82 are expected to earn more than they cost to trade/)).toBeVisible()
  })

  it('warns in words, not arithmetic, when nothing in a book clears its cost', () => {
    useData.mockReturnValue({ data: tieredPayload(), loading: false, error: null })
    renderScreen()
    fireEvent.click(screen.getByRole('tab', { name: /3-day swing/ }))
    expect(screen.getByText(/None of them is expected to earn more than it costs to trade/)).toBeVisible()
  })

  it('states a verdict per row rather than leaving the reader to combine three columns', () => {
    useData.mockReturnValue({ data: tieredPayload(), loading: false, error: null })
    renderScreen()
    fireEvent.click(screen.getByRole('tab', { name: /3-day swing/ }))
    // FAST tops the composite and does not clear its cost. That is the reading error the
    // verdict exists to prevent, so it must be stated on the row and not inferred.
    expect(screen.getAllByText('Cost eats it').length).toBeGreaterThan(0)
    expect(screen.getByText('Cost eats it').getAttribute('title')).toMatch(/one round trip costs/)
  })

  it('marks a screened-out name as such with its reason attached', () => {
    const data = tieredPayload()
    data.tiers.S.results = [tierRow('SHORTED', {
      rank: 1, eligibility: false, current_membership: false, percentile: null,
      short_interest: { suppressed: true, reasons: ['14.6% of float short'] },
      reason_codes: ['SHORT_INTEREST_SUPPRESSED'],
    })]
    useData.mockReturnValue({ data, loading: false, error: null })
    renderScreen()
    const verdict = screen.getByText('Screened out')
    expect(verdict).toBeVisible()
    expect(verdict.getAttribute('title')).toMatch(/Heavily shorted/)
  })

  it('says how strong a signal is in words, keeping the exact number one hover away', () => {
    const data = tieredPayload()
    data.tiers.S.results = [tierRow('TOP', { rank: 1, percentile: 99.1, composite_z: 1.42 })]
    useData.mockReturnValue({ data, loading: false, error: null })
    renderScreen()
    const strength = screen.getByText('Very strong')
    expect(strength).toBeVisible()
    expect(strength.closest('td').getAttribute('title')).toMatch(/99th percentile/)
    expect(strength.closest('td').getAttribute('title')).toMatch(/composite \+1\.42/)
  })

  it('names the leg actually carrying each row', () => {
    useData.mockReturnValue({ data: tieredPayload(), loading: false, error: null })
    renderScreen()
    fireEvent.click(screen.getByRole('tab', { name: /3-day swing/ }))
    // announcement_return contributes 1.5 * 0.5, the largest of the three.
    expect(screen.getAllByText('Earnings reaction').length).toBeGreaterThan(0)
  })

  it('defers the dense columns without discarding them', () => {
    useData.mockReturnValue({ data: tieredPayload(), loading: false, error: null })
    renderScreen()
    expect(screen.queryByRole('columnheader', { name: 'Composite' })).toBeNull()
    expect(screen.queryByRole('columnheader', { name: 'Liquidity' })).toBeNull()

    showEveryNumber()

    expect(screen.getByRole('columnheader', { name: 'Composite' })).toBeVisible()
    expect(screen.getByRole('columnheader', { name: 'Liquidity' })).toBeVisible()
    expect(screen.getByRole('columnheader', { name: 'Short interest' })).toBeVisible()
  })

  it('keeps the verdict and signal columns in both views', () => {
    useData.mockReturnValue({ data: tieredPayload(), loading: false, error: null })
    renderScreen()
    showEveryNumber()
    expect(screen.getByRole('columnheader', { name: 'Verdict' })).toBeVisible()
    expect(screen.getByRole('columnheader', { name: 'Signal' })).toBeVisible()
  })

  it('keeps every header and cell aligned when the column set changes', () => {
    useData.mockReturnValue({ data: tieredPayload(), loading: false, error: null })
    const { container } = renderScreen()
    const widths = () => [
      container.querySelectorAll('thead th').length,
      ...[...container.querySelectorAll('tbody tr')].map((tr) => tr.children.length),
    ]
    expect(new Set(widths()).size).toBe(1)
    showEveryNumber()
    expect(new Set(widths()).size).toBe(1)
    fireEvent.click(screen.getByRole('tab', { name: /3-day swing/ }))
    expect(new Set(widths()).size).toBe(1)
  })

  it('leaves the method available rather than removing it', () => {
    useData.mockReturnValue({ data: tieredPayload(), loading: false, error: null })
    renderScreen()
    expect(screen.getByText('How this works')).toBeVisible()
    openMethod()
    expect(screen.getByText(/Brandt, Kishore, Santa-Clara & Venkatachalam/)).toBeVisible()
  })
})
