/**
 * The extended metric stack, grouped the way an analyst would read it.
 *
 * Every entry declares how to format itself and which direction is good, so a value can be
 * tinted without a second lookup table. Metrics that the pipeline could not derive are
 * hidden rather than shown as a zero – a missing number is not a bad number.
 */

const pct = (value, digits = 1) => `${(value * 100).toFixed(digits)}%`
const num = (value, digits = 2) => value.toFixed(digits)
const times = (value) => `${value.toFixed(1)}×`
const days = (value) => `${Math.round(value)}d`
const dollars = (value) => {
  const abs = Math.abs(value)
  if (abs >= 1e12) return `$${(value / 1e12).toFixed(1)}T`
  if (abs >= 1e9) return `$${(value / 1e9).toFixed(1)}B`
  if (abs >= 1e6) return `$${(value / 1e6).toFixed(0)}M`
  return `$${Math.round(value).toLocaleString('en-US')}`
}

// [key, label, format, why it matters, {good, bad} thresholds where higher/lower is better]
export const SECTIONS = [
  {
    title: 'Valuation',
    note: 'Capital-structure-neutral multiples catch levered names that only look cheap on P/E.',
    metrics: [
      ['peg', 'PEG', num, 'Growth-adjusted earnings multiple', { lowerBetter: true, good: 1.5, bad: 3 }],
      ['forward_pe', 'Forward P/E', num, 'Price against next year’s earnings', { lowerBetter: true, good: 20, bad: 40 }],
      ['ev_to_ebitda', 'EV/EBITDA', num, 'Whole-company price against operating profit – debt included. The best-validated single value multiple in the published research', { lowerBetter: true, good: 12, bad: 22 }],
      ['ev_to_ebit', 'EV/EBIT', num, 'The same multiple without the depreciation add-back, so capital intensity cannot hide in it', { lowerBetter: true, good: 14, bad: 26 }],
      ['ev_to_fcf', 'EV/FCF', num, 'Whole-company price against actual cash generated', { lowerBetter: true, good: 22, bad: 45 }],
      ['ev_to_sales', 'EV/Sales', num, 'Revenue multiple including debt – a levered company cannot look cheap simply by borrowing', { lowerBetter: true, good: 3, bad: 10 }],
      ['price_to_sales', 'P/S', num, 'Price against revenue, used where the balance sheet is unavailable', { lowerBetter: true, good: 3, bad: 10 }],
      ['price_to_book', 'P/B', num, 'Price against reported book value', { lowerBetter: true, good: 3, bad: 10 }],
      ['price_to_tangible_book', 'P/Tangible book', num, 'Book value with goodwill stripped out – the honest one for financials', { lowerBetter: true, good: 3, bad: 8 }],
      ['dividend_yield', 'Dividend yield', (value) => `${value.toFixed(2)}%`, 'Income return at the current price'],
    ],
  },
  {
    title: 'Profitability & cash',
    note: 'ROIC cannot be inflated by leverage the way ROE can, and cash conversion tests whether earnings are real.',
    metrics: [
      ['return_on_invested_capital', 'ROIC', pct, 'Return on every dollar of capital, debt and equity alike', { good: 0.13, bad: 0.05 }],
      ['gross_profits_to_assets', 'Gross profits / assets', pct, 'Profitability measured above the line where accounting discretion operates – about as predictive as book-to-market, and complementary to it', { good: 0.22, bad: 0.08 }],
      ['return_on_equity', 'ROE', pct, 'Return on shareholder equity only – flattered by debt', { good: 0.15, bad: 0.05 }],
      ['cash_conversion', 'Cash conversion', (value) => `${(value * 100).toFixed(0)}%`, 'Free cash flow per dollar of reported net income', { good: 0.9, bad: 0.5 }],
      ['free_cash_flow_yield', 'FCF yield', pct, 'Free cash flow against market value', { good: 0.05, bad: 0 }],
      ['operating_margin', 'Operating margin', pct, 'Profit left after running the business'],
      ['operating_margin_trend', 'Margin trend', (value) => `${value >= 0 ? '+' : ''}${(value * 100).toFixed(1)}pp`, 'Year-over-year change – direction beats level', { good: 0.005, bad: -0.01 }],
      ['incremental_margin', 'Incremental margin', pct, 'Profit carried by each dollar of new revenue', { good: 0.25, bad: 0 }],
      ['profit_margin', 'Net margin', pct, 'Bottom-line profit per dollar of revenue', { good: 0.12, bad: 0 }],
    ],
  },
  {
    title: 'Financial health',
    note: 'Interest coverage answers the question debt-to-equity cannot: can this company actually service its debt at current rates?',
    metrics: [
      ['interest_coverage', 'Interest coverage', times, 'Operating profit per dollar of interest owed', { good: 6, bad: 2 }],
      ['net_debt_to_ebitda', 'Net debt/EBITDA', times, 'Years of operating profit needed to clear net debt', { lowerBetter: true, good: 1.5, bad: 4 }],
      ['debt_to_equity', 'Debt/equity', num, 'Leverage against book equity', { lowerBetter: true, good: 1, bad: 2.5 }],
      ['current_ratio', 'Current ratio', num, 'Short-term assets against short-term bills', { good: 1.5, bad: 1 }],
      ['altman_z', 'Altman Z-score', num, 'Composite bankruptcy risk, computed with the variant fitted for this sector – the original manufacturing model or Altman’s non-manufacturer revision. Suppressed for financials, where it has no meaning', { good: 2.6, bad: 1.1 }],
    ],
  },
  {
    title: 'Accounting quality',
    note: 'The F-score leads here. Accruals remain, at a small weight – the gap between profit and cash was a strong signal for decades and has faded.',
    metrics: [
      ['piotroski_f', 'Piotroski F-score', (value) => `${value.toFixed(1)}/9`, 'Nine-point fundamental-strength composite, and the one earnings-quality signal that still validates well', { good: 6.5, bad: 4 }],
      ['accruals_ratio', 'Accruals ratio', (value) => `${(value * 100).toFixed(1)}%`, 'Net income minus operating cash flow, over assets – negative is healthy. Weighted lightly: its predictive power has largely decayed since the early 2000s', { lowerBetter: true, good: 0.03, bad: 0.1 }],
      ['days_sales_outstanding', 'Days sales outstanding', days, 'How long revenue sits as an unpaid invoice'],
      ['days_sales_outstanding_trend', 'DSO trend', (value) => `${value >= 0 ? '+' : ''}${(value * 100).toFixed(0)}%`, 'Rising receivable days can mean revenue booked ahead of cash', { lowerBetter: true, good: 0.03, bad: 0.15 }],
      ['inventory_days', 'Inventory days', days, 'How long stock sits before it sells'],
      ['inventory_days_trend', 'Inventory trend', (value) => `${value >= 0 ? '+' : ''}${(value * 100).toFixed(0)}%`, 'Rising inventory days is the retail and industrial version of the same warning', { lowerBetter: true, good: 0.03, bad: 0.15 }],
    ],
  },
  {
    title: 'Capital allocation',
    note: 'Whether management is quietly diluting you or steadily increasing your share of the business.',
    metrics: [
      ['net_buyback_yield', 'Net buyback yield', (value) => `${value >= 0 ? '+' : ''}${(value * 100).toFixed(1)}%`, 'Share count change over the year, net of dilution – positive means your stake grew', { good: 0.01, bad: -0.01 }],
      ['stock_comp_to_revenue', 'Stock comp / revenue', pct, 'The dilution cost GAAP earnings hide', { lowerBetter: true, good: 0.03, bad: 0.08 }],
      ['capex_to_depreciation', 'Capex / depreciation', times, 'Under 1× flatters near-term cash flow and starves the business'],
      ['asset_growth', 'Asset growth', (value) => `${value >= 0 ? '+' : ''}${(value * 100).toFixed(1)}%`, 'Total balance-sheet expansion year over year. Aggressive growth has historically preceded weak returns, and shrinking is not a virtue either – both tails count against'],
      ['gross_buyback_yield', 'Gross buybacks', pct, 'Cash spent repurchasing stock, against market value'],
    ],
  },
  {
    title: 'Growth',
    metrics: [
      ['revenue_growth', 'Revenue growth', pct, 'Year-over-year revenue change', { good: 0.1, bad: 0 }],
      ['earnings_growth', 'Earnings growth', pct, 'Year-over-year earnings change', { good: 0.1, bad: 0 }],
      ['fcf_growth_3y', 'FCF growth (3y)', pct, 'Compound annual free-cash-flow growth', { good: 0.08, bad: 0 }],
      ['earnings_surprise', 'Earnings surprise', (value) => `${value >= 0 ? '+' : ''}${value.toFixed(1)}%`, 'Recent quarters against expectations, newest weighted heaviest. Beating expectations carries drift in a way trailing growth alone does not', { good: 3, bad: -5 }],
    ],
  },
  {
    title: 'Ownership & positioning',
    note: 'Crowding and conviction from outside the financial statements.',
    metrics: [
      ['short_percent_of_float', 'Short interest', pct, 'Share of the float sold short', { lowerBetter: true, good: 0.05, bad: 0.15 }],
      ['days_to_cover', 'Days to cover', (value) => `${value.toFixed(1)}d`, 'Trading days for shorts to unwind at normal volume', { lowerBetter: true, good: 3, bad: 7 }],
      ['institutional_ownership', 'Institutional ownership', pct, 'Share held by professional managers'],
      ['insider_ownership', 'Insider ownership', pct, 'Share held by officers and directors'],
      ['analyst_rating', 'Analyst consensus', (value) => `${value.toFixed(1)}/5`, 'Lower is more bullish on the standard scale', { lowerBetter: true, good: 2, bad: 3.5 }],
      ['analyst_target_upside', 'Target upside', (value) => `${value >= 0 ? '+' : ''}${value.toFixed(0)}%`, 'Consensus price target against today’s price', { good: 10, bad: -5 }],
    ],
  },
  {
    title: 'Behaviour & tradability',
    note: 'Trend quality, drawdown depth, and whether you could exit without moving the price.',
    metrics: [
      ['@technical.momentum_12_1_pct', '12-1 momentum', (value) => `${value >= 0 ? '+' : ''}${value.toFixed(1)}%`, 'Twelve-month return excluding the most recent month, the standard construction – the skipped month is dominated by short-term reversal. Measured on a fixed trading-day offset (252/21 sessions); the standalone Momentum screen instead uses exact calendar month-end prices, so the two can disagree slightly around holidays or short months', { good: 15, bad: -10 }],
      ['@technical.relative_acceleration', 'Acceleration vs market', (value) => `${value >= 0 ? '+' : ''}${value.toFixed(2)}σ`, 'Whether the gap against the S&P 500 is widening or narrowing – this quarter’s market-adjusted excess return against last quarter’s, in standard errors. Measured and shown, but it carries no weight in the score', { good: 1, bad: -1 }],
      ['@technical.sortino_ratio', 'Sortino ratio', num, 'Return per unit of downside deviation – upside volatility is not a risk worth penalising', { good: 1.5, bad: 0 }],
      ['@technical.sharpe_ratio', 'Sharpe ratio', num, 'Return per unit of total volatility, computed the same way as on the ETF screen', { good: 1.2, bad: 0 }],
      ['@technical.max_drawdown_252d', 'Max drawdown (1y)', (value) => `${value.toFixed(1)}%`, 'Deepest peak-to-trough fall over the past year', { good: -10, bad: -30 }],
      ['@technical.volume_ratio_60d', 'Volume confirmation', (value) => `${value.toFixed(2)}×`, 'Volume on up days against down days – under 1 means rallies are unconvinced', { good: 1.15, bad: 0.85 }],
      ['@technical.pct_from_52w_high', 'From 52-week high', (value) => `${value.toFixed(1)}%`, 'Distance below the yearly high', { good: -5, bad: -25 }],
      ['@technical.pct_above_52w_low', 'Above 52-week low', (value) => `+${value.toFixed(1)}%`, 'Distance above the yearly low'],
      ['@technical.annualized_volatility', 'Volatility', (value) => `${value.toFixed(0)}%`, 'Annualized standard deviation of daily moves', { lowerBetter: true, good: 25, bad: 50 }],
      ['beta', 'Beta', num, 'Sensitivity to the broad market – the link between the Fed backdrop and this name'],
      ['average_dollar_volume', 'Avg daily volume', dollars, 'Dollar liquidity – how easily a position can be entered or exited', { good: 50e6, bad: 5e6 }],
      ['implied_volatility', 'Implied volatility', pct, 'Near-the-money option pricing for the nearest listed expiry'],
      ['realized_volatility_20d', 'Realized volatility (20d)', pct, 'Annualized volatility actually experienced over 20 sessions', { lowerBetter: true, good: 0.25, bad: 0.50 }],
      ['implied_realized_vol_ratio', 'Implied / realized vol', times, 'Above 1× means options price more movement than the stock recently realized'],
    ],
  },
]

export function readValue(stock, key) {
  if (key.startsWith('@technical.')) return stock.technical_detail?.[key.slice(11)]
  return stock[key]
}

export const canonicalKey = (key) => ({ revenue_growth: 'trailing_revenue_growth', earnings_growth: 'trailing_eps_growth' }[key] || key)

// The exact set of metrics this stock would actually render, section by section, applicability
// exceptions and unresolved values already filtered out - the single source of truth both the
// live "All metrics" panel and any other reader (the copy-to-clipboard export, for one) build
// from, so the two can never quietly disagree about what "shown" means for this row.
export function resolvedMetricSections(stock, sections = SECTIONS) {
  const status = stock.analysis_v2?.metric_status || {}
  return sections
    .map((section) => ({
      ...section,
      resolved: section.metrics
        .map(([key, label, format, why, thresholds]) => ({
          key, label, format, why, thresholds, value: readValue(stock, key),
        }))
        .filter((metric) => {
          const state = status[canonicalKey(metric.key)]?.status
          return !['suppressed', 'replaced', 'unavailable'].includes(state)
            && typeof metric.value === 'number' && Number.isFinite(metric.value)
        }),
    }))
    .filter((section) => section.resolved.length)
}
