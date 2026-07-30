/**
 * The extended metric stack, grouped the way an analyst would read it.
 *
 * Every entry declares how to format itself and which direction is good, so a value can be
 * tinted without a second lookup table. Metrics that the pipeline could not derive are
 * hidden rather than shown as a zero — a missing number is not a bad number.
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
      ['ev_to_ebitda', 'EV/EBITDA', num, 'Whole-company price against operating profit — debt included', { lowerBetter: true, good: 12, bad: 22 }],
      ['ev_to_fcf', 'EV/FCF', num, 'Whole-company price against actual cash generated', { lowerBetter: true, good: 22, bad: 45 }],
      ['price_to_sales', 'P/S', num, 'Price against revenue', { lowerBetter: true, good: 3, bad: 10 }],
      ['price_to_book', 'P/B', num, 'Price against reported book value', { lowerBetter: true, good: 3, bad: 10 }],
      ['price_to_tangible_book', 'P/Tangible book', num, 'Book value with goodwill stripped out — the honest one for financials', { lowerBetter: true, good: 3, bad: 8 }],
      ['dividend_yield', 'Dividend yield', (value) => `${value.toFixed(2)}%`, 'Income return at the current price'],
    ],
  },
  {
    title: 'Profitability & cash',
    note: 'ROIC cannot be inflated by leverage the way ROE can, and cash conversion tests whether earnings are real.',
    metrics: [
      ['return_on_invested_capital', 'ROIC', pct, 'Return on every dollar of capital, debt and equity alike', { good: 0.13, bad: 0.05 }],
      ['return_on_equity', 'ROE', pct, 'Return on shareholder equity only — flattered by debt', { good: 0.15, bad: 0.05 }],
      ['cash_conversion', 'Cash conversion', (value) => `${(value * 100).toFixed(0)}%`, 'Free cash flow per dollar of reported net income', { good: 0.9, bad: 0.5 }],
      ['free_cash_flow_yield', 'FCF yield', pct, 'Free cash flow against market value', { good: 0.05, bad: 0 }],
      ['operating_margin', 'Operating margin', pct, 'Profit left after running the business'],
      ['operating_margin_trend', 'Margin trend', (value) => `${value >= 0 ? '+' : ''}${(value * 100).toFixed(1)}pp`, 'Year-over-year change — direction beats level', { good: 0.005, bad: -0.01 }],
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
      ['altman_z', 'Altman Z-score', num, 'Composite bankruptcy risk — above 3 is the safe zone', { good: 3, bad: 1.8 }],
    ],
  },
  {
    title: 'Accounting quality',
    note: 'The biggest blind spot in most screens. Big gaps between profit and cash predict underperformance.',
    metrics: [
      ['accruals_ratio', 'Accruals ratio', (value) => `${(value * 100).toFixed(1)}%`, 'Net income minus operating cash flow, over assets — negative is healthy', { lowerBetter: true, good: 0.03, bad: 0.1 }],
      ['piotroski_f', 'Piotroski F-score', (value) => `${value.toFixed(1)}/9`, 'Nine-point fundamental-strength composite', { good: 6.5, bad: 4 }],
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
      ['net_buyback_yield', 'Net buyback yield', (value) => `${value >= 0 ? '+' : ''}${(value * 100).toFixed(1)}%`, 'Share count change over the year, net of dilution — positive means your stake grew', { good: 0.01, bad: -0.01 }],
      ['stock_comp_to_revenue', 'Stock comp / revenue', pct, 'The dilution cost GAAP earnings hide', { lowerBetter: true, good: 0.03, bad: 0.08 }],
      ['capex_to_depreciation', 'Capex / depreciation', times, 'Under 1× flatters near-term cash flow and starves the business'],
      ['gross_buyback_yield', 'Gross buybacks', pct, 'Cash spent repurchasing stock, against market value'],
    ],
  },
  {
    title: 'Growth',
    metrics: [
      ['revenue_growth', 'Revenue growth', pct, 'Year-over-year revenue change', { good: 0.1, bad: 0 }],
      ['earnings_growth', 'Earnings growth', pct, 'Year-over-year earnings change', { good: 0.1, bad: 0 }],
      ['fcf_growth_3y', 'FCF growth (3y)', pct, 'Compound annual free-cash-flow growth', { good: 0.08, bad: 0 }],
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
      ['@technical.max_drawdown_252d', 'Max drawdown (1y)', (value) => `${value.toFixed(1)}%`, 'Deepest peak-to-trough fall over the past year', { good: -10, bad: -30 }],
      ['@technical.volume_ratio_60d', 'Volume confirmation', (value) => `${value.toFixed(2)}×`, 'Volume on up days against down days — under 1 means rallies are unconvinced', { good: 1.15, bad: 0.85 }],
      ['@technical.pct_from_52w_high', 'From 52-week high', (value) => `${value.toFixed(1)}%`, 'Distance below the yearly high', { good: -5, bad: -25 }],
      ['@technical.pct_above_52w_low', 'Above 52-week low', (value) => `+${value.toFixed(1)}%`, 'Distance above the yearly low'],
      ['@technical.annualized_volatility', 'Volatility', (value) => `${value.toFixed(0)}%`, 'Annualized standard deviation of daily moves', { lowerBetter: true, good: 25, bad: 50 }],
      ['beta', 'Beta', num, 'Sensitivity to the broad market — the link between the Fed backdrop and this name'],
      ['average_dollar_volume', 'Avg daily volume', dollars, 'Dollar liquidity — how easily a position can be entered or exited', { good: 50e6, bad: 5e6 }],
    ],
  },
]

function readValue(stock, key) {
  if (key.startsWith('@technical.')) return stock.technical_detail?.[key.slice(11)]
  return stock[key]
}

function tone(value, thresholds) {
  if (!thresholds) return 'var(--text)'
  const { good, bad, lowerBetter } = thresholds
  if (good == null || bad == null) return 'var(--text)'
  const isGood = lowerBetter ? value <= good : value >= good
  const isBad = lowerBetter ? value >= bad : value <= bad
  if (isGood) return 'var(--pos)'
  if (isBad) return 'var(--neg)'
  return 'var(--text)'
}

function Metric({ label, value, format, why, thresholds }) {
  return (
    <div className="metric-detail" title={why}>
      <span className="metric-detail-label">{label}</span>
      <b className="mono" style={{ color: tone(value, thresholds) }}>{format(value)}</b>
      {why && <small>{why}</small>}
    </div>
  )
}

export default function MetricSections({ stock, sections = SECTIONS }) {
  const rendered = sections
    .map((section) => ({
      ...section,
      resolved: section.metrics
        .map(([key, label, format, why, thresholds]) => ({
          key, label, format, why, thresholds, value: readValue(stock, key),
        }))
        .filter((metric) => typeof metric.value === 'number' && Number.isFinite(metric.value)),
    }))
    .filter((section) => section.resolved.length)

  if (!rendered.length) {
    return (
      <p style={{ color: 'var(--text-faint)', fontSize: 13 }}>
        Extended metrics appear here once the pipeline has derived this company’s financial statements.
      </p>
    )
  }

  return (
    <div style={{ display: 'grid', gap: 22 }}>
      {rendered.map((section) => (
        <section key={section.title}>
          <div className="sec-label">{section.title}</div>
          {section.note && (
            <p style={{ color: 'var(--text-dim)', fontSize: 12.5, margin: '-6px 0 12px' }}>{section.note}</p>
          )}
          <div className="metric-detail-grid">
            {section.resolved.map((metric) => <Metric key={metric.key} {...metric} />)}
          </div>
        </section>
      ))}
    </div>
  )
}
