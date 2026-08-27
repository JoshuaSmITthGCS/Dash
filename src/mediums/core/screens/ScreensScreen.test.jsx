import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import ScreensScreen from './ScreensScreen.jsx'
import { MediumProvider } from '../MediumContext.jsx'
import { useData } from '../../../lib/useData.js'

vi.mock('../../../lib/useData.js', async (importOriginal) => ({ ...(await importOriginal()), useData: vi.fn() }))

// StockDetailSheet (mounted unconditionally by ScreensScreen since the FastGrowth open-detail
// wiring) calls useRenderer(), which needs `manifest.loadRenderer` to resolve to something — a
// bare `{ components: {} }` manifest crashed every test here with "manifest.loadRenderer is not
// a function" even when no ?ticker= was ever set, because useRenderer's own effect always fires.
const fakeChart = vi.fn(({ metricId }) => <svg data-testid="fake-chart" data-metric-id={metricId} />)
const fakeRenderer = { dial: fakeChart, bar: fakeChart, profile: fakeChart, waterfall: fakeChart, line: fakeChart, scatter: fakeChart }
const fakeManifest = { components: {}, loadRenderer: () => Promise.resolve(fakeRenderer) }

function renderScreens(path) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <MediumProvider value={fakeManifest}><ScreensScreen /></MediumProvider>
    </MemoryRouter>
  )
}

describe('ScreensScreen', () => {
  it('resolves ?recipe=swing to the swing file and renders its rows', () => {
    useData.mockReturnValue({ data: { status: 'success', results: [{ ticker: 'AAPL' }, { ticker: 'MSFT' }] }, loading: false })
    renderScreens('/v2/screens?recipe=swing')
    expect(screen.getByTestId('row-count')).toHaveTextContent('2 names')
  })

  it('defaults to swing with no recipe param', () => {
    useData.mockReturnValue({ data: { status: 'success', results: [] }, loading: false })
    renderScreens('/v2/screens')
    expect(screen.getByText('swing')).toBeInTheDocument()
  })

  it('shows the gated state as a feature, not a failure, for early-session', () => {
    useData.mockReturnValue({ data: { status: 'gated', disclaimer: 'Killed screens are a successful outcome.' }, loading: false })
    renderScreens('/v2/screens?recipe=early-session')
    expect(screen.getByTestId('gated-note')).toHaveTextContent('successful outcome')
  })

  it('shows the partial-collection alert for politics', () => {
    useData.mockReturnValue({ data: { status: 'partial', reason_code: 'SOME_SOURCES_UNAVAILABLE', results: [] }, loading: false })
    renderScreens('/v2/screens?recipe=politics')
    expect(screen.getByTestId('partial-note')).toBeInTheDocument()
  })

  it('shows unavailable when the recipe has no data yet', () => {
    useData.mockReturnValue({ data: null, loading: false })
    renderScreens('/v2/screens?recipe=matrix')
    expect(screen.getByRole('alert')).toHaveTextContent('Screen snapshot unavailable')
  })
})

const SWING_DATA = {
  status: 'success', schema_version: '1.0', model_version: '1.0', config_version: '1.0',
  default_tier: 'fast',
  tier_order: ['fast', 'slow'],
  tiers: {
    fast: {
      label: 'Fast', horizon_label: '2-5 days', target_hold_sessions: 3,
      book_count: 1, book_clearing_cost: 1,
      round_trips_per_year: 60, median_round_trip_bps: 20, expected_alpha_bps_per_period: 30,
      median_net_edge_bps: 10, break_even_alpha_bps_per_month: 5,
      weights: { pead_drift: 0.3, analyst_revision: 0.2 },
      leg_coverage: { pead_drift: 0.5, analyst_revision: 0.4 },
      results: [{
        ticker: 'AAPL', name: 'Apple', sector: 'Technology', market_cap: 3e12, median_dollar_volume_60d: 5e9,
        coverage: 0.8, current_membership: true, percentile: 91, composite_z: 1.2,
        eligibility: true, economics_net_edge_bps: 12, economics_predicted_upside_pct: 1.5,
        economics_round_trip_bps: 8, economics_expected_alpha_bps: 20, rank: 1,
        legs: { pead_drift: { applied: true, z: 1.1 }, analyst_revision: { applied: false } },
        short_interest: { suppressed: false, short_percent_of_float: 0.01 },
        reason_codes: [],
      }],
    },
    slow: { label: 'Slow', horizon_label: '3-8 weeks', target_hold_sessions: 30, book_count: 0, book_clearing_cost: 0, results: [] },
  },
  evidence: { pead_drift: { label: 'Earnings surprise drift', horizon: '20d', direction: 'long', effect: 'x', citation: 'y', caveat: 'z' } },
  cost_model: { status: null, by_portfolio_size: { a: { portfolio_value: 1e6, median_round_trip_bps: 12 } }, cost_ceiling_bps: 40, note: 'note' },
  coverage_note: 'coverage note',
}

const OPTIONS_DATA = {
  status: 'success', schema_version: '1', model_version: '1', config_version: '1',
  results: [{
    ticker: 'MSFT', rank: 1, eligibility: true, sector: 'Technology', option_type: 'call',
    strike: 400, expiration: '2026-09-18', days_to_expiration: 20,
    implied_volatility: 0.3, implied_realized_vol_ratio: 1.1, spread_pct: 0.02,
    open_interest: 500, capital_required: 4000, score: 8.5, confidence: 0.7,
  }],
}

const MOMENTUM_DATA = {
  status: 'success', schema_version: '1', model_version: '1', config_version: '1',
  coverage_note: 'coverage note',
  results: [{
    ticker: 'NVDA', rank: 1, sector: 'Technology', classification: 'High momentum', peer_group: 'Semis',
    percentile: 95, structural_score: 80, tactical_score: 90, confidence: 0.9, eligibility: true,
    market_cap: 2e12, median_dollar_volume_60d: 1e9, current_membership: true, reason_codes: [],
  }],
}

const EARLY_SESSION_DATA = {
  status: 'success', schema_version: '1', model_version: '1', disclaimer: 'Killed screens are a successful outcome.',
  screens: {
    premarket_reversal: { reason_code: 'NO_EXTENDED_HOURS_OHLCV', fallback: 'daily_context_only', candidate_count: 0 },
    first_hour: { reason_code: null, fallback: 'none', candidate_count: 3 },
  },
  capabilities: [
    { capability: 'Extended hours OHLCV', provider: 'yfinance', granularity: '1m', freshness: 'daily', verdict: 'UNAVAILABLE', available: false },
  ],
}

const POLITICS_DATA = {
  status: 'success', schema_version: '1', model_version: '1', history_days: 30,
  summary: { trades: 10, filings_estimated: 12, volume_upper: 5000000, politicians: 4, issuers: 6 },
  signals: [{ ticker: 'TSLA', direction: 'BUY', representative: 'Jane Doe', chamber: 'senate', flags: ['CLUSTER_TRADE'] }],
  top_tickers: [{
    ticker: 'TSLA', rank: 1, asset_description: 'Tesla Inc', disclosed_volume_midpoint: 100000,
    trade_count: 3, buy_count: 2, sell_count: 1, unique_politicians: 2, politicians: ['Jane Doe', 'John Roe'], flags: [],
  }],
  results: [{
    representative: 'Jane Doe', symbol: 'TSLA', chamber: 'senate', transaction_type: 'Purchase',
    amount: '$1,001 - $15,000', amount_lower: 1001, amount_upper: 15000, transaction_date: '2026-07-01',
    disclosure_date: '2026-07-15', filing_delay_days: 14, flags: ['CLUSTER_TRADE'], return_since_purchase_pct: 5.2,
    asset_description: 'Tesla Inc',
  }],
}

const INSTITUTIONAL_DATA = {
  status: 'success', schema_version: '1', model_version: '1',
  managers_reviewed: 20, managers_configured: 25, cusips_mapped: 100, cusips_seen: 110, cusips_pending: 10, amendments_seen: 3,
  results: [{ ticker: 'AMZN', cusip: '023135106', managers_added: 3, managers_dropped: 1, share_change_pct: 0.12, flag: 'ACCUMULATION', as_of: '2026-06-30' }],
}

const INSIDEINFO_DATA = {
  status: 'success', schema_version: '1', model_version: '1', ranked_count: 5, notable_count: 2,
  results: [{ ticker: 'GOOG', score: 4.2, institutional_flag: 'CLUSTER_ACCUMULATION', congress_flags: ['CLUSTER_TRADE'], members_buying: 3, managers_added: 2 }],
}

describe('ScreensScreen — swing recipe', () => {
  it('wires the tier tablist, filter panel and table with a computed verdict', () => {
    useData.mockReturnValue({ data: SWING_DATA, loading: false })
    const { container } = renderScreens('/v2/screens?recipe=swing')
    expect(container.querySelector('[data-capability-id="nav.screens.swing-tier-tablist"]')).toBeInTheDocument()
    expect(container.querySelector('[data-capability-id="control.screens.swing-filters"]')).toBeInTheDocument()
    expect(container.querySelector('[data-capability-id="column.screens.swing-table"]')).toHaveTextContent('Worth buying')
    expect(container.querySelector('[data-capability-id="figure.screens.swing-tier-headline"]')).toHaveTextContent('Hold about 3')
    expect(container.querySelector('[data-capability-id="disclosure.screens.swing-frozen-priors"]')).toBeInTheDocument()
    expect(container.querySelector('[data-capability-id="disclosure.screens.swing-footer-versions"]')).toBeInTheDocument()
  })
})

describe('ScreensScreen — options recipe', () => {
  it('wires the strategy sub-nav, direction/sector filters, disclosure and table', () => {
    useData.mockImplementation((file) => (
      file === 'screens/options.json' ? { data: OPTIONS_DATA, loading: false } : { data: null, loading: false }
    ))
    const { container } = renderScreens('/v2/screens?recipe=options')
    expect(container.querySelector('[data-capability-id="nav.screens.options-sub-nav"]')).toBeInTheDocument()
    expect(container.querySelector('[data-capability-id="control.screens.options-direction-select"]')).toBeInTheDocument()
    expect(container.querySelector('[data-capability-id="control.screens.options-sector-filter"]')).toBeInTheDocument()
    expect(container.querySelector('[data-capability-id="disclosure.screens.options-not-instruction"]')).toBeInTheDocument()
    expect(container.querySelector('[data-capability-id="column.screens.options-table"]')).toHaveTextContent('MSFT')
  })
})

describe('ScreensScreen — generic family recipe (momentum)', () => {
  it('wires the shared filter panel, table and coverage-note disclosure', () => {
    useData.mockReturnValue({ data: MOMENTUM_DATA, loading: false })
    const { container } = renderScreens('/v2/screens?recipe=momentum')
    expect(container.querySelector('[data-capability-id="control.screens.generic-filters"]')).toBeInTheDocument()
    expect(container.querySelector('[data-capability-id="column.screens.generic-table"]')).toHaveTextContent('NVDA')
    expect(container.querySelector('[data-capability-id="disclosure.screens.generic-coverage-note"]')).toHaveTextContent('coverage note')
  })
})

describe('ScreensScreen — early-session recipe', () => {
  it('wires the gate summary, gate cards and capability matrix', () => {
    useData.mockReturnValue({ data: EARLY_SESSION_DATA, loading: false })
    const { container } = renderScreens('/v2/screens?recipe=early-session')
    expect(container.querySelector('[data-capability-id="figure.screens.earlysession-gate-summary"]')).toHaveTextContent('3 live candidate')
    expect(container.querySelector('[data-capability-id="figure.screens.earlysession-gate-cards"]')).toHaveTextContent('Killed by data gate')
    expect(container.querySelector('[data-capability-id="figure.screens.earlysession-capability-matrix"]')).toHaveTextContent('Extended hours OHLCV')
    expect(container.querySelector('[data-capability-id="disclosure.screens.earlysession-guardrail"]')).toBeInTheDocument()
  })
})

describe('ScreensScreen — politics recipe', () => {
  it('wires the kpi cards, signals/top-tickers panels, bar timeline and table', () => {
    useData.mockReturnValue({ data: POLITICS_DATA, loading: false })
    const { container } = renderScreens('/v2/screens?recipe=politics')
    expect(container.querySelector('[data-capability-id="figure.screens.politics-kpi-cards"]')).toHaveTextContent('Trades: 10')
    expect(container.querySelector('[data-capability-id="figure.screens.politics-signals-panel"]')).toHaveTextContent('TSLA')
    expect(container.querySelector('[data-capability-id="figure.screens.politics-top-tickers"]')).toHaveTextContent('TSLA')
    expect(container.querySelector('[data-capability-id="chart.screens.politics-bar-timeline"]')).toBeInTheDocument()
    expect(container.querySelector('[data-capability-id="column.screens.politics-table"]')).toHaveTextContent('TSLA')
    expect(container.querySelector('[data-capability-id="disclosure.screens.politics-stock-act-ranges"]')).toBeInTheDocument()
  })
})

describe('ScreensScreen — institutional recipe', () => {
  it('wires the kpis, filters, table and disclosures', () => {
    useData.mockReturnValue({ data: INSTITUTIONAL_DATA, loading: false })
    const { container } = renderScreens('/v2/screens?recipe=institutional')
    expect(container.querySelector('[data-capability-id="figure.screens.institutional-kpis"]')).toHaveTextContent('Managers reviewed: 20')
    expect(container.querySelector('[data-capability-id="control.screens.institutional-filters"]')).toBeInTheDocument()
    expect(container.querySelector('[data-capability-id="column.screens.institutional-table"]')).toHaveTextContent('AMZN')
    expect(container.querySelector('[data-capability-id="disclosure.screens.institutional-curated-list"]')).toBeInTheDocument()
  })
})

describe('ScreensScreen — inside-information recipe', () => {
  it('wires the kpis, sort control, table and disclosure', () => {
    useData.mockReturnValue({ data: INSIDEINFO_DATA, loading: false })
    const { container } = renderScreens('/v2/screens?recipe=inside-information')
    expect(container.querySelector('[data-capability-id="figure.screens.insideinfo-kpis"]')).toHaveTextContent('Tickers with disclosed activity: 5')
    expect(container.querySelector('[data-capability-id="control.screens.insideinfo-sort"]')).toBeInTheDocument()
    expect(container.querySelector('[data-capability-id="column.screens.insideinfo-table"]')).toHaveTextContent('GOOG')
    expect(container.querySelector('[data-capability-id="disclosure.screens.insideinfo-flagged-only"]')).toBeInTheDocument()
  })
})

const REPORT_DATA = {
  research: [
    {
      ticker: 'ACME', name: 'Acme Corp', sector: 'Technology', score: 88,
      technical_detail: { return_5d: 8, return_20d: 10 },
      history: { closes: [10, 10.2, 10.5, 10.8, 11, 11.3, 11.6, 10.9] },
    },
    {
      ticker: 'BIOX', name: 'BioX Inc', sector: 'Healthcare', score: 55,
      technical_detail: { return_5d: 1, return_20d: 3, relative_strength_20d: 2 },
      fundamental_detail: { revenue_growth: 0.12, operating_margin_trend: 0.01 },
      history: { closes: [] },
    },
  ],
  screen_universe: [],
}

describe('ScreensScreen — fast-growth recipe', () => {
  it('wires the breakout view: screen-select, sector filter and breakout columns table', () => {
    useData.mockImplementation((file) => (
      file === 'report.json' ? { data: REPORT_DATA, loading: false } : { data: null, loading: false }
    ))
    const { container } = renderScreens('/v2/screens?recipe=fast-growth')
    expect(container.querySelector('[data-capability-id="control.screens.fastgrowth-screen-select"]')).toBeInTheDocument()
    expect(container.querySelector('[data-capability-id="control.screens.fastgrowth-sector-filter"]')).toBeInTheDocument()
    expect(container.querySelector('[data-capability-id="column.screens.fastgrowth-breakout-columns"]')).toHaveTextContent('ACME')
    expect(container.querySelector('[data-capability-id="figure.screens.fastgrowth-mobile-cards"]')).toHaveTextContent('ACME')
    expect(container.querySelector('[data-capability-id="disclosure.screens.fastgrowth-footer"]')).toBeInTheDocument()
    expect(container.querySelector('[data-capability-id="disclosure.screens.fastgrowth-unvalidated"]')).not.toBeInTheDocument()
  })

  it('wires the emerging-growth view: unvalidated disclosure and emerging columns table', () => {
    useData.mockImplementation((file) => (
      file === 'report.json' ? { data: REPORT_DATA, loading: false } : { data: null, loading: false }
    ))
    const { container } = renderScreens('/v2/screens?recipe=fast-growth&sub=emerging')
    expect(container.querySelector('[data-capability-id="disclosure.screens.fastgrowth-unvalidated"]')).toBeInTheDocument()
    expect(container.querySelector('[data-capability-id="column.screens.fastgrowth-emerging-columns"]')).toHaveTextContent('BIOX')
  })
})

const ADVISOR_THEME_DATA = {
  generated_at: '2026-08-20T00:00:00Z',
  theme_screen: {
    unavailable_reason: null,
    by_ticker: {
      NVST: [
        { theme_id: 'aging_demographics', display_name: 'Aging Demographics', theme_exposure_score: 61, opportunity_score: 70, eligible: true, confidence: 0.8, role: 'supplier' },
        { theme_id: 'digital_payments', display_name: 'Digital Payments', theme_exposure_score: 55, opportunity_score: 60, eligible: true, confidence: 0.5, role: 'root' },
      ],
    },
    themes: [{
      id: 'aging_demographics', display_name: 'Aging Demographics', thesis: 'The most predictable demand curve available.',
      sectors: ['Healthcare'], industries: ['Medical Devices'],
      count: 46, eligible_count: 19,
      group_counts: { leaders: 1, connected: 46 },
      rows: [
        {
          ticker: 'BSX', name: 'Boston Scientific', sector: 'Healthcare', industry: 'Medical Devices', role: 'root',
          candidate_source: 'portfolio', theme_exposure_score: 85, opportunity_score: 74, eligible: true,
          leading_signals_fired: ['filing_keyword_density_trend'], why: ['In this theme because it is one of your holdings'],
        },
        {
          ticker: 'NVST', name: 'Envista Holdings', sector: 'Healthcare', industry: 'Medical Instruments', role: 'supplier',
          candidate_source: 'sector_peer', theme_exposure_score: 61, opportunity_score: 70, eligible: true,
          leading_signals_fired: ['backlog_growth'], why: ["In this theme because it is a peer-group neighbour"],
        },
      ],
      trend: {
        verdict: { label: 'broadening', summary: 'The group is outperforming.' },
        direction: { relative_strength_median: 68.8 },
        breadth: { outperforming_share: 0.978 },
        crowding: { expensiveness_percentile_median: 50, already_priced: false },
        roles: [{ role: 'root', members: 15, relative_strength_median: 69.1 }, { role: 'supplier', members: 16, relative_strength_median: 57.1 }],
      },
      biggest_players: [{ ticker: 'ABT', name: 'Abbott Laboratories', role: 'root', theme_exposure_score: 43.4, eligible: false }],
    }],
  },
}

describe('ScreensScreen — themes recipe', () => {
  it('wires the theme index, per-theme block, leaders/connected tables and momentum-excluded disclosure', () => {
    useData.mockImplementation((file) => (
      file === 'advisor.json' ? { data: ADVISOR_THEME_DATA, loading: false, reload: vi.fn() } : { data: null, loading: false }
    ))
    const { container } = renderScreens('/v2/screens?recipe=themes')
    expect(container.querySelector('[data-capability-id="nav.screens.themes-index"]')).toHaveTextContent('Aging Demographics')
    expect(container.querySelector('[data-capability-id="figure.screens.themes-per-theme-blocks"]')).toHaveTextContent('Boston Scientific')
    expect(container.querySelector('[data-capability-id="figure.screens.themes-per-theme-blocks"]')).toHaveTextContent('Envista Holdings')
    expect(container.querySelector('[data-capability-id="disclosure.screens.themes-momentum-excluded"]')).toBeInTheDocument()
    expect(container.querySelector('[data-capability-id="control.screens.themes-hide-holdings"]')).toBeInTheDocument()
    expect(container.querySelector('[data-capability-id="figure.screens.themes-cross-theme-section"]')).toBeInTheDocument()
  })

  it('shows the unavailable-reason empty state when no theme scored any exposure', () => {
    useData.mockImplementation((file) => (
      file === 'advisor.json'
        ? { data: { generated_at: 't', theme_screen: { unavailable_reason: 'No signals resolved this run.', themes: [], by_ticker: {} } }, loading: false, reload: vi.fn() }
        : { data: null, loading: false }
    ))
    const { container } = renderScreens('/v2/screens?recipe=themes')
    expect(container.querySelector('[data-capability-id="state.screens.themes-unavailable-reason"]')).toHaveTextContent('No signals resolved this run.')
  })
})
