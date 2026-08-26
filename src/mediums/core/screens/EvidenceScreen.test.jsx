import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import EvidenceScreen from './EvidenceScreen.jsx'
import { MediumProvider } from '../MediumContext.jsx'
import { useData } from '../../../lib/useData.js'
import { useAuth } from '../../../lib/FirebaseAuthContext.jsx'
import { useFirebasePortfolio } from '../../../lib/useFirebasePortfolio.js'

vi.mock('../../../lib/useData.js', async (importOriginal) => ({ ...(await importOriginal()), useData: vi.fn() }))
// The shadow section's "your portfolio vs. these strategies" overlay mounts its own
// <FirebaseAuthProvider> (same pattern as PortfolioScreen.jsx). Real Firebase auth/session
// wiring has no place in a unit test, so both the provider and the hook it and
// useFirebasePortfolio depend on are mocked outright — no network call is ever made.
vi.mock('../../../lib/FirebaseAuthContext.jsx', () => ({
  AuthProvider: ({ children }) => children,
  useAuth: vi.fn(),
}))
vi.mock('../../../lib/useFirebasePortfolio.js', () => ({ useFirebasePortfolio: vi.fn() }))

const fakeManifest = { components: {} }

const comparisonFixture = {
  methods_total: 2,
  generated_at: '2026-08-25T19:59:33.979245+00:00',
  interpretation: 'Success rates may be ranked only inside a comparable group.',
  comparable_groups: { held_portfolio: 'Portfolios held unchanged apart from scheduled rebalances.' },
  feature_rollup: [],
  methods: [
    {
      id: 'research_score_monthly', label: 'Research score, top 20 monthly', comparable_group: 'held_portfolio',
      status: 'measured', status_detail: null, source: 'pipeline/backtest_monthly_results.json',
      window_start: '2021-09-01', window_end: '2026-08-13',
      total_return_pct: 104.9975, cagr_pct: 15.6149, sharpe: 0.9205, max_drawdown_pct: -18.9802,
      excess_return_pct: 20.9661, excess_return_withheld_reason: null,
      success_rate: 0.5833, success_rate_basis: 'rebalance_periods_positive',
      beat_benchmark_rate: 0.5333, periods_measured: 60, periods_in_cash: 0, caveats: [],
    },
  ],
}

const optionsBacktestFixture = {
  status: 'success',
  backtest: { num_trades: 12280, sharpe_ratio: 0.233, deflated_sharpe_ratio: 0.9975, win_rate: 0.3288, average_pnl_per_trade: 5.58 },
}

const shadowFixture = {
  promotion_gate: 'No strategy is promotion-eligible until the configured 36 monthly observations are complete.',
  aligned_window: { observations: 1, window_start: '2026-08-21', window_end: '2026-08-24' },
  strategies: [
    {
      strategy: 'Existing production model', net_return: 1.4755, cagr: null, sharpe: null, sortino: null,
      max_drawdown: -1.1037, turnover: 290.0, observations: 12, snapshots: 16, composition_change: 5.0,
      annualized_metrics_minimum_observations: 20, evidence_status: 'Accumulating · 12 immutable net-of-cost returns',
      aligned: { net_return: -0.1351 }, cost_bps: 20,
    },
  ],
}

const advisorFixture = {
  methodology: {
    weights: { fundamentals: 0.6, market_behavior: 0.3, news_sentiment: 0.1 },
    fundamental_weights: { valuation: 0.2 },
    modifiers: {},
  },
  model_metadata: {
    semantic_version: '1.2.3', git_commit_sha: 'abcdef123456789', config_hash: 'deadbeefcafefeed', generated_at: '2026-08-25T00:00:00Z',
  },
  disclaimer: 'General research only. Not individualized investment advice.',
}

function renderEvidence(path = '/v2/evidence') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <MediumProvider value={fakeManifest}><EvidenceScreen /></MediumProvider>
    </MemoryRouter>
  )
}

describe('EvidenceScreen', () => {
  it('closes the docs-only gap: renders the no-signal-promoted disclosure with live counts', () => {
    useData.mockImplementation((file) => {
      if (file === 'validation/signal_metrics.json') return { data: { summary: { ready: 44, breached: 9, total: 64 } }, loading: false }
      if (file === 'validation/research_evidence.json') return { data: { headline: { ic_periods_accumulated: 0, ic_periods_required: 24 } }, loading: false }
      return { data: null, loading: false }
    })
    renderEvidence()
    expect(screen.getByTestId('promotion-disclosure')).toHaveTextContent('No signal has been promoted')
    expect(screen.getByTestId('promotion-disclosure')).toHaveTextContent('0 of the 24')
    expect(screen.getByTestId('metrics-summary')).toHaveTextContent('44 ready · 9 breached of 64')
  })

  it('shows the unavailable alert when signal metrics have not been published', () => {
    useData.mockReturnValue({ data: null, loading: false })
    renderEvidence()
    expect(screen.getByRole('alert')).toHaveTextContent('Signal metrics unavailable')
  })

  it('renders every published metric through WallLabel, grouped by sample requirement', () => {
    const metric = {
      id: 'rank_ic_1d', group: 'signal', label: 'Rank IC (1d)', value: -0.038, display: '-0.038',
      reads: 'Spearman correlation of score against forward return.', breached: true, status: 'ready',
      requires_live_sample: false, observations: 60, required_observations: null,
    }
    useData.mockImplementation((file) => {
      if (file === 'validation/signal_metrics.json') {
        return {
          data: {
            summary: { ready: 1, breached: 1, total: 1 },
            groups: [{ id: 'signal', letter: 'A', title: 'Signal quality', requires_live_sample: false }],
            metrics: [metric],
          },
          loading: false,
        }
      }
      if (file === 'validation/research_evidence.json') return { data: { headline: { ic_periods_accumulated: 0, ic_periods_required: 24 } }, loading: false }
      return { data: null, loading: false }
    })
    const { container } = renderEvidence()
    expect(container.querySelector('[data-capability-id="metric.report.rank-ic-1d"]')).toHaveTextContent('Rank IC (1d)')
  })

  it('does not fetch the validation files for the methodology section', () => {
    useData.mockReturnValue({ data: null, loading: false })
    const { container } = renderEvidence('/v2/evidence?section=methodology')
    expect(container.querySelector('[data-section="methodology"]')).toBeInTheDocument()
    expect(screen.queryByTestId('metrics-summary')).not.toBeInTheDocument()
  })
})

describe('EvidenceScreen backtests section', () => {
  it('renders the champion-method backtest metrics through WallLabel and the coverage cards', () => {
    useData.mockImplementation((file) => {
      if (file === 'screens/backtest-comparison.json') return { data: comparisonFixture, loading: false }
      if (file === 'screens/options-backtest.json') return { data: optionsBacktestFixture, loading: false }
      return { data: null, loading: false }
    })
    const { container } = renderEvidence('/v2/evidence?section=backtests')
    expect(container.querySelector('[data-testid="backtests-measured-count"]')).toHaveTextContent('1')
    expect(container.querySelector('[data-capability-id="metric.report.backtest-total-return"]')).toHaveTextContent('Total return')
    expect(container.querySelector('[data-capability-id="metric.report.backtest-cagr"]')).toHaveTextContent('CAGR')
    expect(container.querySelector('[data-capability-id="metric.report.backtest-dsr"]')).toHaveTextContent('Deflated Sharpe')
    expect(container.querySelector('[data-capability-id="metric.report.backtest-win-rate"]')).toHaveTextContent('Win rate')
    expect(container.querySelector('[data-capability-id="metric.report.average-pnl-trade"]')).toHaveTextContent('Avg P/L per trade')
    expect(container.querySelector('[data-capability-id="metric.report.trade-count"]')).toHaveTextContent('Trades')
    expect(container.querySelector('[data-capability-id="column.evidence.backtests-method-tables"]')).toBeInTheDocument()
  })

  it('shows the backtests-unavailable alert when the comparison artifact has not published', () => {
    useData.mockReturnValue({ data: null, loading: false })
    renderEvidence('/v2/evidence?section=backtests')
    expect(screen.getByRole('alert')).toHaveTextContent('Backtest comparison unavailable')
  })
})

describe('EvidenceScreen shadow section', () => {
  it('renders the shadow metrics through WallLabel, the strategies table, and the not-signed-in mine branch', () => {
    useData.mockImplementation((file) => {
      if (file === 'screens/shadow-portfolios.json') return { data: shadowFixture, loading: false }
      return { data: null, loading: false }
    })
    useAuth.mockReturnValue({ currentUser: null })
    useFirebasePortfolio.mockReturnValue({ positions: [] })
    const { container } = renderEvidence('/v2/evidence?section=shadow')
    expect(container.querySelector('[data-capability-id="metric.report.shadow-net-return"]')).toHaveTextContent('Net return (own window)')
    expect(container.querySelector('[data-capability-id="metric.report.shadow-aligned-net-return"]')).toHaveTextContent('Aligned net return')
    expect(container.querySelector('[data-capability-id="column.evidence.shadow-strategies-table"]')).toBeInTheDocument()
    expect(container.querySelector('[data-testid="shadow-mine-branch"]')).toHaveTextContent('not-signed-in')
  })

  it('shows the result branch of the mine overlay once a signed-in user has a comparable window', () => {
    useData.mockImplementation((file) => {
      if (file === 'screens/shadow-portfolios.json') return { data: shadowFixture, loading: false }
      return { data: null, loading: false }
    })
    useAuth.mockReturnValue({ currentUser: { uid: 'josh' } })
    useFirebasePortfolio.mockReturnValue({ positions: [] })
    const { container } = renderEvidence('/v2/evidence?section=shadow')
    // No positions -> the no-positions branch, not "result" (no price data is faked to fast-forward this).
    expect(container.querySelector('[data-testid="shadow-mine-branch"]')).toHaveTextContent('no-positions')
  })

  it('shows the shadow-unavailable alert when the shadow artifact has not published', () => {
    useData.mockReturnValue({ data: null, loading: false })
    useAuth.mockReturnValue({ currentUser: null })
    useFirebasePortfolio.mockReturnValue({ positions: [] })
    renderEvidence('/v2/evidence?section=shadow')
    expect(screen.getByRole('alert')).toHaveTextContent('Shadow results unavailable')
  })
})

describe('EvidenceScreen methodology section', () => {
  it('renders the weight stack and version card read live from advisor.json', () => {
    useData.mockImplementation((file) => {
      if (file === 'advisor.json') return { data: advisorFixture, loading: false }
      return { data: null, loading: false }
    })
    const { container } = renderEvidence('/v2/evidence?section=methodology')
    expect(container.querySelector('[data-testid="weight-stack"]')).toHaveTextContent('60% fundamentals')
    expect(container.querySelector('[data-testid="weight-stack"]')).toHaveTextContent('30% behaviour')
    expect(container.querySelector('[data-capability-id="figure.evidence.methodology-version-card"]')).toHaveTextContent('1.2.3')
    expect(container.querySelector('[data-capability-id="export.evidence.methodology-download-docs"]')).toBeInTheDocument()
  })
})

describe('EvidenceScreen glossary section', () => {
  it('counts terms, reads the research-score definition live, and filters on search', () => {
    useData.mockImplementation((file) => {
      if (file === 'advisor.json') return { data: advisorFixture, loading: false }
      return { data: null, loading: false }
    })
    const { container } = renderEvidence('/v2/evidence?section=glossary')
    expect(container.querySelector('[data-capability-id="figure.evidence.glossary-research-score-def"]')).toHaveTextContent('60% fundamentals')
    const countBefore = container.querySelector('[data-testid="glossary-count"]').textContent
    expect(countBefore).toMatch(/^\d+ of \d+ terms$/)

    const input = container.querySelector('input[type="search"]')
    fireEvent.change(input, { target: { value: 'PEG ratio' } })

    expect(container.querySelector('[data-testid="glossary-count"]').textContent).toMatch(/^1 of \d+ terms$/)
  })

  it('shows the no-match state for a query that matches nothing', () => {
    useData.mockImplementation((file) => {
      if (file === 'advisor.json') return { data: advisorFixture, loading: false }
      return { data: null, loading: false }
    })
    const { container } = renderEvidence('/v2/evidence?section=glossary')
    const input = container.querySelector('input[type="search"]')
    fireEvent.change(input, { target: { value: 'zzz-not-a-real-term' } })
    expect(container.querySelector('[data-capability-id="state.evidence.glossary-no-match"]')).toHaveTextContent('No terms matched')
  })
})
