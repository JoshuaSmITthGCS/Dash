import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import ResearchEvidence, {
  BenchmarkPanel, CalibrationPanel, CostPanel, DiagnosticsPanel, ExperimentPanel,
  FactorPanel, ScoreInterpretation,
} from './ResearchEvidence'

const headline = {
  validation_status: 'no calibration history yet',
  ic_periods_accumulated: 0,
  ic_periods_required: 24,
  forecast_target: { primary_horizon_sessions: 63 },
  score_is_not_a_probability:
    'The Research Score ranks attractiveness. Confidence measures how reliable that '
    + "rank's evidence is. Neither is a probability that the stock rises, and no score "
    + 'bucket has enough closed forward windows to state one.',
}

const benchmarks = {
  status: 'measured',
  strategy: { cagr: 0.1033, volatility: 0.192, sharpe: 0.611, max_drawdown: -0.2076 },
  rows: [
    { name: 'VTV', description: 'CRSP US large value', cagr: 0.1217, volatility: 0.139,
      sharpe: 0.899, max_drawdown: -0.1534, beta: 0.98, annualized_alpha_pct: -0.48,
      newey_west_t_statistic: -0.09, significant: false },
    { name: 'IWM', description: 'Russell 2000', cagr: 0.0704, volatility: 0.2063,
      sharpe: 0.433, max_drawdown: -0.2675, beta: 0.65, annualized_alpha_pct: 6.34,
      newey_west_t_statistic: 1.04, significant: false },
  ],
  summary: { beaten_on_cagr_count: '9 of 14',
    verdict: 'no tradeable benchmark in this set is beaten with statistically significant alpha' },
}

describe('ScoreInterpretation', () => {
  it('states plainly that the score is not a probability', () => {
    render(<ScoreInterpretation headline={headline} />)
    expect(screen.getByText(/Neither is a probability that the stock rises/i))
      .toBeInTheDocument()
  })

  it('shows insufficient calibration rather than implying a calibrated score', () => {
    render(<ScoreInterpretation headline={headline} />)
    expect(screen.getByText(/Historical calibration: insufficient data/i)).toBeInTheDocument()
    expect(screen.getByText('0 of 24')).toBeInTheDocument()
  })

  it('reports the preregistered forecast target in sessions', () => {
    render(<ScoreInterpretation headline={headline} />)
    expect(screen.getByText('63-session sector-residual return')).toBeInTheDocument()
  })
})

describe('BenchmarkPanel', () => {
  it('shows the strategy beside every benchmark it is compared against', () => {
    render(<BenchmarkPanel panel={benchmarks} />)
    expect(screen.getByText('ValueSignal')).toBeInTheDocument()
    expect(screen.getByText('VTV')).toBeInTheDocument()
    expect(screen.getByText('IWM')).toBeInTheDocument()
  })

  it('publishes the verdict rather than leaving the table to speak for itself', () => {
    render(<BenchmarkPanel panel={benchmarks} />)
    expect(screen.getByText(/beaten with statistically significant alpha/i)).toBeInTheDocument()
  })

  it('reports a missing artifact instead of rendering an empty table', () => {
    render(<BenchmarkPanel panel={{ status: 'not_generated', reason: 'not built' }} />)
    expect(screen.getByText(/Benchmark comparison not generated/i)).toBeInTheDocument()
  })
})

describe('FactorPanel', () => {
  const panel = {
    status: 'measured', months: 58, r_squared: 0.589, annualized_alpha_pct: -2.57,
    loadings: [
      { factor: 'alpha', estimate: -0.0022, newey_west_t_statistic: -0.437, significant: false },
      { factor: 'market_excess', estimate: 0.859, newey_west_t_statistic: 6.5, significant: true },
    ],
  }

  it('marks which loadings clear the significance bar', () => {
    const { container } = render(<FactorPanel panel={panel} />)
    expect(within(container).getByText(/t 6\.50 · significant/)).toBeInTheDocument()
    expect(within(container).getByText('t -0.44')).toBeInTheDocument()
  })
})

describe('DiagnosticsPanel', () => {
  const panel = {
    status: 'measured',
    unit_of_account: { trade: 'one monthly rebalance period holding a 20-name book' },
    sample: { first: '2021-09', last: '2026-07' },
    expectancy: { win_rate: 0.61, average_win: 0.0429, average_loss: 0.0421,
      payoff_ratio: 1.019, expectancy_per_period: 0.00977 },
    profit_factor: { profit_factor: 1.594 },
    streaks: { longest_losing_streak: 3 },
    turnover: { mean_monthly_turnover: 0.649 },
    turnover_adjusted_return: { share_of_gross_return_consumed_by_costs: 0.07 },
    regime_definitions: { preregistration: 'defined from benchmark series only' },
    regime_attribution: {
      rates: {
        rising_rates: { months: 26, strategy_annualized: 0.006, benchmark_annualized: 0.175 },
        falling_rates: { months: 32, strategy_annualized: 0.189, benchmark_annualized: 0.086 },
      },
    },
  }

  it('names the unit of account so a month is not read as a position', () => {
    render(<DiagnosticsPanel panel={panel} />)
    expect(screen.getByText(/one monthly rebalance period holding a 20-name book/i))
      .toBeInTheDocument()
  })

  it('shows expectancy and profit factor', () => {
    render(<DiagnosticsPanel panel={panel} />)
    expect(screen.getByText('61.0%')).toBeInTheDocument()
    expect(screen.getByText('1.594')).toBeInTheDocument()
  })

  it('surfaces regime performance against the benchmark', () => {
    render(<DiagnosticsPanel panel={panel} />)
    expect(screen.getByText('Rising Rates')).toBeInTheDocument()
    expect(screen.getByText(/vs \+17\.5% · n=26/)).toBeInTheDocument()
  })
})

describe('CostPanel', () => {
  const panel = {
    status: 'measured',
    turnover: { rebalances: 60, mean_turnover: 0.6492 },
    realized_flat_10bps: { cost_bps: 10, cagr: 0.111423 },
    scenarios: [
      { scenario: 'gross', cost_bps: 0, total_cost: 0, drag_vs_realized_flat: -4522.44 },
      { scenario: 'stress', cost_bps: 25, total_cost: 11306.05, drag_vs_realized_flat: 6783.61 },
    ],
    never_present_gross_as_net: 'Gross is shown only as an upper bound, never as an outcome.',
  }

  it('shows realized turnover and the published rate', () => {
    render(<CostPanel panel={panel} />)
    expect(screen.getByText('64.9%')).toBeInTheDocument()
    expect(screen.getByText('60')).toBeInTheDocument()
    expect(screen.getByText('11.14%')).toBeInTheDocument()
  })

  it('prices every scenario against the published flat rate', () => {
    render(<CostPanel panel={panel} />)
    expect(screen.getByText('Gross')).toBeInTheDocument()
    expect(screen.getByText('Stress')).toBeInTheDocument()
    expect(screen.getByText('25.00 bps')).toBeInTheDocument()
    expect(screen.getByText('+$6,784')).toBeInTheDocument()
  })

  it('carries the warning against reading gross as an outcome', () => {
    render(<CostPanel panel={panel} />)
    expect(screen.getByText(/never as an outcome/)).toBeInTheDocument()
  })
})

describe('CalibrationPanel', () => {
  it('refuses to show a table when no bucket has closed forward windows', () => {
    render(<CalibrationPanel panel={{
      status: 'insufficient_data', observations: 0, fixed_score_bands: [],
      what_would_populate_this: '24 monthly point-in-time periods',
    }} />)
    expect(screen.getByText(/Insufficient data/i)).toBeInTheDocument()
    expect(screen.getByText(/would turn an admitted unknown into a false claim/i))
      .toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it('shows only the bands that were actually measured once data exists', () => {
    render(<CalibrationPanel panel={{
      status: 'measured', observations: 90,
      fixed_score_bands: [
        { bucket: '80+', status: 'measured', observations: 60,
          median_residual_return: 0.018, beat_sector_rate: 0.589 },
        { bucket: '70-74', status: 'insufficient_data', observations: 4 },
      ],
    }} />)
    expect(screen.getByText('80+')).toBeInTheDocument()
    expect(screen.queryByText('70-74')).not.toBeInTheDocument()
    expect(screen.getByText('58.9%')).toBeInTheDocument()
  })
})

describe('ExperimentPanel', () => {
  it('shows rejected experiments alongside supported ones', () => {
    render(<ExperimentPanel panel={{
      status: 'measured',
      summary: { experiments: 2, total_variants_tested: 16, promoted_to_champion: [] },
      experiments: [
        { id: 'q1-benchmark', hypothesis: 'residual alpha survives', category: 'diagnostic',
          result: 'rejected', decision: 'abandon', reason: 'no residual alpha at |t| = 0.437',
          number_of_variants_tested: 2 },
        { id: 'news-weight', hypothesis: 'the news component is inert', category: 'corrective',
          result: 'supported', decision: 'shipped_as_fix', reason: 'confirmed',
          number_of_variants_tested: 1 },
      ],
    }} />)
    expect(screen.getByText('q1-benchmark')).toBeInTheDocument()
    expect(screen.getByText('Rejected')).toBeInTheDocument()
    expect(screen.getByText('news-weight')).toBeInTheDocument()
    expect(screen.getByText(/0 promoted/)).toBeInTheDocument()
  })
})

describe('ResearchEvidence', () => {
  it('renders nothing rather than an empty shell when there is no artifact', () => {
    const { container } = render(<ResearchEvidence data={null} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('explains how to generate the artifact when it failed to load', () => {
    render(<ResearchEvidence error={new Error('404')} />)
    expect(screen.getByRole('alert')).toHaveTextContent(/build_research_evidence/)
  })

  it('renders every panel from a full payload', () => {
    render(<ResearchEvidence data={{
      headline, benchmarks, model_version: '3.2.0', code_commit_hash: 'abcdef1234',
      factor_exposures: { status: 'not_generated', reason: 'x' },
      strategy_diagnostics: { status: 'not_generated', reason: 'x' },
      costs: { status: 'not_generated', reason: 'x' },
      calibration: { status: 'insufficient_data', fixed_score_bands: [],
        what_would_populate_this: 'more periods' },
      experiments: { status: 'not_generated', reason: 'x' },
    }} />)
    expect(screen.getByText(/Research Score is a rank, not a probability/i)).toBeInTheDocument()
    expect(screen.getByText(/Model 3\.2\.0 · commit abcdef12/)).toBeInTheDocument()
    // Panels whose artifact is absent say so rather than showing a plausible blank.
    expect(screen.getAllByText(/not generated/i).length).toBeGreaterThan(2)
  })
})
