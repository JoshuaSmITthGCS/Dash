import { useMemo, useState } from 'react'
import Icon from '../components/Icons.jsx'

/**
 * Plain-language definitions for every term used elsewhere in the app. Static reference
 * content only — it never reads advisor.json, so it renders the same with no data published.
 */
const GROUPS = [
  {
    title: 'Valuation',
    note: 'What you are paying, relative to what the business actually produces.',
    terms: [
      ['PEG ratio', 'A P/E ratio divided by expected earnings growth. It answers "is this multiple justified by how fast earnings are growing," which the P/E ratio alone cannot.'],
      ['Forward P/E', 'Share price divided by next year’s expected earnings per share, rather than the year just reported. Lower generally means cheaper, holding growth and risk constant.'],
      ['EV/EBITDA', 'Enterprise value (market cap plus debt, minus cash) divided by operating profit before interest, tax, depreciation, and amortization. Unlike P/E, it is neutral to how a company is financed, so a heavily indebted company cannot look artificially cheap.'],
      ['EV/FCF', 'Enterprise value divided by free cash flow. The same capital-structure-neutral idea as EV/EBITDA, but measured against actual cash generated instead of an accounting profit figure.'],
      ['P/S (Price-to-sales)', 'Share price divided by revenue per share. Useful for early-stage or low-margin companies where earnings are small, negative, or noisy.'],
      ['P/B (Price-to-book)', 'Share price divided by reported book (accounting) value per share.'],
      ['Price-to-tangible-book', 'Price-to-book with goodwill and other intangible assets stripped out of book value. The more honest version for banks and insurers, whose goodwill can otherwise flatter the ratio.'],
      ['Dividend yield', 'Annual dividend per share divided by share price — the income return you get just for holding, before any price change.'],
      ['Enterprise value (EV)', 'The theoretical full takeover cost of a company: market capitalization plus total debt, minus cash on hand. It reflects what a buyer would actually have to pay, including the debt they’d assume.'],
    ],
  },
  {
    title: 'Profitability & cash',
    note: 'Whether the business earns well and whether the reported earnings show up as real cash.',
    terms: [
      ['ROIC (Return on invested capital)', 'Operating profit after tax divided by all the capital funding the business — debt and equity combined. Leverage cannot inflate it the way it inflates ROE, which makes it a cleaner read on how good the underlying business actually is.'],
      ['ROE (Return on equity)', 'Net income divided by shareholder equity. Taking on more debt can push this number up without the business getting any better, so it is best read alongside ROIC, not alone.'],
      ['Cash conversion', 'Free cash flow divided by net income. A ratio well under 100% is a flag that reported profit isn’t fully showing up as cash — often a sign of aggressive accounting.'],
      ['FCF yield (Free-cash-flow yield)', 'Free cash flow divided by market value. Similar in spirit to earnings yield, but built on cash the business actually generated rather than an accounting profit figure.'],
      ['Operating margin', 'Operating profit divided by revenue — what is left after running the core business, before interest and tax.'],
      ['Margin trend', 'The year-over-year change in operating margin. A mediocre margin that is improving is a meaningfully different story than the same margin that is sliding.'],
      ['Incremental margin', 'The profit earned on each new dollar of revenue growth, rather than on revenue overall. It shows whether growth is actually profitable.'],
      ['Net margin (Profit margin)', 'Bottom-line net income divided by revenue — what is left for shareholders after every expense, including interest and tax.'],
    ],
  },
  {
    title: 'Financial health',
    note: 'Whether the company can comfortably service its obligations, not just how big its debt looks on paper.',
    terms: [
      ['Interest coverage', 'Operating profit divided by interest expense — how many times over the company could pay the interest it owes from operating profit alone. Answers the "can they actually afford this debt" question that debt-to-equity cannot.'],
      ['Net debt / EBITDA', 'Total debt minus cash, divided by EBITDA. Roughly: how many years of current operating profit it would take to pay off all net debt.'],
      ['Debt-to-equity', 'Total debt divided by shareholder equity — a basic leverage ratio. Read it alongside interest coverage, since a high ratio at a very low interest rate is a different risk than the same ratio at a high one.'],
      ['Current ratio', 'Current assets divided by current liabilities — whether short-term resources cover short-term bills. Below 1 means bills due within a year exceed the cash and near-cash on hand.'],
      ['Altman Z-score', 'A composite bankruptcy-risk score built from five accounting ratios. Above roughly 3 is considered the safe zone; below roughly 1.8 signals meaningful distress risk.'],
    ],
  },
  {
    title: 'Accounting quality',
    note: 'The most commonly overlooked risk in a stock screen: whether reported profit is trustworthy.',
    terms: [
      ['Accruals ratio', '(Net income minus operating cash flow) divided by total assets. A persistently large gap between profit and cash is one of the most-studied predictors of future earnings disappointments and underperformance.'],
      ['Piotroski F-score', 'A nine-point checklist of profitability, leverage, and efficiency signals, each scored pass/fail and summed. Higher (toward 9) indicates broader fundamental strength; below about 4 is weak.'],
      ['Days sales outstanding (DSO)', 'The average number of days it takes to collect payment after a sale. A rising trend can mean revenue is being booked before the cash actually arrives.'],
      ['Inventory days', 'The average number of days stock sits before it sells. A rising trend is the manufacturing and retail equivalent of the same warning DSO gives — demand may be softening faster than the income statement shows.'],
    ],
  },
  {
    title: 'Capital allocation',
    note: 'What management does with the cash the business generates — whether your ownership stake is growing or being quietly diluted.',
    terms: [
      ['Net buyback yield', 'The year-over-year change in share count, net of new shares issued, expressed as a percentage. Positive means your ownership stake grew even though you did nothing; negative means dilution outpaced buybacks.'],
      ['Gross buyback yield', 'Cash spent on share repurchases divided by market value, before netting out new shares issued from options or compensation.'],
      ['Stock comp / revenue', 'Stock-based compensation as a share of revenue. This is a real dilution cost that does not appear as a cash expense on the income statement the way a cash salary would.'],
      ['Capex / depreciation', 'Capital expenditure divided by depreciation. A ratio under 1x means the company is spending less on new equipment and facilities than its existing assets are wearing out — a way of flattering near-term cash flow that can starve future competitiveness.'],
    ],
  },
  {
    title: 'Growth',
    terms: [
      ['Revenue growth', 'The year-over-year percentage change in total revenue.'],
      ['Earnings growth', 'The year-over-year percentage change in net income or earnings per share.'],
      ['FCF growth (3y)', 'The compound annual growth rate of free cash flow over the trailing three years — smoother than a single year-over-year figure.'],
    ],
  },
  {
    title: 'Ownership & positioning',
    note: 'Signals from who owns the stock and how it is being traded, separate from the financial statements.',
    terms: [
      ['Short interest', 'The percentage of a company’s tradable shares (its float) that are currently sold short. High short interest is not automatically bearish, but it raises the cost of being wrong if the short thesis fails.'],
      ['Days to cover', 'Total shares sold short divided by average daily trading volume — roughly how many trading days it would take for all short sellers to buy back their shares at normal volume. A high figure means any rally could be amplified by short sellers rushing to exit.'],
      ['Institutional ownership', 'The percentage of shares held by professional money managers (funds, pensions, endowments) rather than individual retail investors.'],
      ['Insider ownership', 'The percentage of shares held by a company’s own officers and directors.'],
      ['Analyst consensus', 'The average recommendation across covering analysts, typically on a 1 (strong buy) to 5 (strong sell) scale, so a lower number is more bullish.'],
      ['Target upside', 'The percentage gap between the average analyst price target and the current share price.'],
      ['Beta', 'A measure of how much a stock tends to move relative to the broader market. A beta above 1 means the stock has historically swung more than the market; below 1 means less.'],
    ],
  },
  {
    title: 'Behaviour & tradability',
    note: 'Price trend, risk, and how easily a position can actually be bought or sold without moving the price.',
    terms: [
      ['Max drawdown', 'The deepest peak-to-trough decline in price over a given window (commonly one year here). It measures the worst pain an investor would have felt holding through the period, regardless of where the price ended up.'],
      ['Volume confirmation', 'The ratio of trading volume on up days to volume on down days. A ratio below 1 means recent gains happened on lighter volume than recent declines — a rally that isn’t fully convincing yet.'],
      ['52-week high / low', 'The highest and lowest closing prices over the trailing year. Distance from these levels is a common (if rough) gauge of where a stock sits within its recent range.'],
      ['Volatility (annualized)', 'The annualized standard deviation of daily price changes — a statistical measure of how much a price bounces around, independent of direction.'],
      ['Implied volatility', 'The volatility level embedded in current option prices for the nearest listed expiry — the market’s forward-looking expectation of how much a stock will move.'],
      ['Realized volatility', 'The volatility a stock actually experienced over a recent window (commonly 20 trading days), calculated directly from historical price changes rather than inferred from option prices.'],
      ['Implied / realized vol ratio', 'Implied volatility divided by realized volatility. A ratio above 1x means options are pricing in more future movement than the stock has actually shown recently.'],
      ['Average dollar volume', 'Average daily trading volume multiplied by share price — how much money trades hands in a typical day. Low dollar volume means a position can be harder to exit without moving the price against you.'],
    ],
  },
  {
    title: 'Scoring & guidance',
    note: 'How the research score is built and how buy/hold/sell-style guidance is decided.',
    terms: [
      ['Research score', 'The overall 0–100 ranking for a company: 75% fundamentals, 15% market behaviour, 10% news sentiment, then adjusted by capped modifiers such as sector-relative valuation, short interest, liquidity, analyst expectations, and macro regime.'],
      ['Confidence', 'A measure of how complete the underlying data was for a given score, not a measure of how good the company is. Missing key inputs lowers confidence even if the metrics that are available look strong.'],
      ['Hold', 'The default guidance. It stays in place unless at least two of three independent factors — fundamentals, market behaviour, and positioning/sentiment — turn negative together.'],
      ['Watch', 'One factor has turned negative, but not enough to change the recommendation — a prompt to look closer, not to act.'],
      ['Trim', 'Two of the three independent factors have turned negative together, producing a suggested partial reduction in position size while the thesis is retested.'],
      ['Sell', 'Two factors have turned negative and the company has also fallen below the evidence threshold — the strongest guidance level, suggesting a full exit.'],
      ['Agreement count', 'How many of the three independent factors (fundamentals, market behaviour, positioning/sentiment) currently agree in the same negative direction. Guidance only moves off Hold once two or more agree.'],
      ['Sector-relative valuation', 'A modifier (±3 points) based on how cheap or expensive a company is versus its own sector peers, rather than against the whole market. Being cheap for a utility and being cheap outright are different claims.'],
      ['Macro regime', 'A modifier (±3 points) built from interest rates, inflation, labor data, and the yield curve, weighted by how sensitive a given sector is to those conditions. It never replaces company-level evidence.'],
    ],
  },
  {
    title: 'Finances',
    note: 'Terms used on the Finances tab: budgeting, savings pools, and the retirement projection.',
    terms: [
      ['Leftover', 'Monthly income minus monthly expenses in the budget subsection — the amount available to save, invest, or split into pools.'],
      ['Auto-split pool', 'A named savings bucket with a target percentage. Logging a deposit divides that dollar amount across every pool in proportion to its percentage.'],
      ['Retirement projection', 'A compounding-growth estimate of a savings balance at a future retirement age, given a starting balance, a monthly contribution, and an assumed annual return.'],
      ['Nominal balance', 'A projected future balance in future dollars, not adjusted for inflation.'],
      ['Inflation-adjusted balance', 'A projected future balance restated in today’s purchasing power by discounting for assumed inflation — a more honest read of what the balance will actually buy.'],
    ],
  },
]

export default function Glossary() {
  const [query, setQuery] = useState('')
  const normalized = query.trim().toLowerCase()

  const filtered = useMemo(() => {
    if (!normalized) return GROUPS
    return GROUPS
      .map((group) => ({
        ...group,
        terms: group.terms.filter(([term, def]) =>
          term.toLowerCase().includes(normalized) || def.toLowerCase().includes(normalized)),
      }))
      .filter((group) => group.terms.length)
  }, [normalized])

  const totalTerms = useMemo(() => GROUPS.reduce((sum, group) => sum + group.terms.length, 0), [])
  const shownTerms = filtered.reduce((sum, group) => sum + group.terms.length, 0)

  return <>
    <div className="page-head">
      <div>
        <span className="eyebrow">Reference</span>
        <h1 className="page-title">Terminology <span className="accent">glossary</span></h1>
        <p className="page-sub">Every metric and guidance term used across the app, defined in plain language. Reference only — nothing here reads live data.</p>
      </div>
      <div className="result-count"><strong>{shownTerms}</strong><span>of {totalTerms} terms</span></div>
    </div>

    <div className="research-toolbar">
      <label className="search-field">
        <Icon name="research" size={18} /><span className="sr-only">Search terms</span>
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search a term, e.g. “drawdown” or “PEG”" />
      </label>
    </div>

    {filtered.map((group) => (
      <section key={group.title} style={{ marginTop: 28 }}>
        <div className="sec-label">{group.title}</div>
        {group.note && <p className="body-copy" style={{ margin: '-4px 0 12px', color: 'var(--text-dim)' }}>{group.note}</p>}
        <div className="card card-pad">
          <dl className="glossary-list">
            {group.terms.map(([term, def]) => (
              <div className="glossary-entry" key={term}>
                <dt>{term}</dt>
                <dd>{def}</dd>
              </div>
            ))}
          </dl>
        </div>
      </section>
    ))}

    {!filtered.length && <div className="inline-empty">No terms matched “{query}”.</div>}

    <div className="disclaimer">General research only. Not individualized investment advice.</div>
  </>
}
