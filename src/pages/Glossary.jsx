import { useMemo, useState } from 'react'
import Icon from '../components/Icons.jsx'
import { useData } from '../lib/useData'

/**
 * Plain-language definitions for every term used elsewhere in the app. Scoring definitions
 * are hydrated from advisor.json so the glossary always describes the published model.
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
      ['Dividend yield', 'Annual dividend per share divided by share price – the income return you get just for holding, before any price change.'],
      ['Enterprise value (EV)', 'The theoretical full takeover cost of a company: market capitalization plus total debt, minus cash on hand. It reflects what a buyer would actually have to pay, including the debt they’d assume.'],
    ],
  },
  {
    title: 'Profitability & cash',
    note: 'Whether the business earns well and whether the reported earnings show up as real cash.',
    terms: [
      ['ROIC (Return on invested capital)', 'Operating profit after tax divided by all the capital funding the business – debt and equity combined. Leverage cannot inflate it the way it inflates ROE, which makes it a cleaner read on how good the underlying business actually is.'],
      ['ROE (Return on equity)', 'Net income divided by shareholder equity. Taking on more debt can push this number up without the business getting any better, so it is best read alongside ROIC, not alone.'],
      ['Cash conversion', 'Free cash flow divided by net income. A ratio well under 100% is a flag that reported profit isn’t fully showing up as cash – often a sign of aggressive accounting.'],
      ['FCF yield (Free-cash-flow yield)', 'Free cash flow divided by market value. Similar in spirit to earnings yield, but built on cash the business actually generated rather than an accounting profit figure.'],
      ['Operating margin', 'Operating profit divided by revenue – what is left after running the core business, before interest and tax.'],
      ['Margin trend', 'The year-over-year change in operating margin. A mediocre margin that is improving is a meaningfully different story than the same margin that is sliding.'],
      ['Incremental margin', 'The profit earned on each new dollar of revenue growth, rather than on revenue overall. It shows whether growth is actually profitable.'],
      ['Net margin (Profit margin)', 'Bottom-line net income divided by revenue – what is left for shareholders after every expense, including interest and tax.'],
    ],
  },
  {
    title: 'Financial health',
    note: 'Whether the company can comfortably service its obligations, not just how big its debt looks on paper.',
    terms: [
      ['Interest coverage', 'Operating profit divided by interest expense – how many times over the company could pay the interest it owes from operating profit alone. Answers the "can they actually afford this debt" question that debt-to-equity cannot.'],
      ['Net debt / EBITDA', 'Total debt minus cash, divided by EBITDA. Roughly: how many years of current operating profit it would take to pay off all net debt.'],
      ['Debt-to-equity', 'Total debt divided by shareholder equity – a basic leverage ratio. Read it alongside interest coverage, since a high ratio at a very low interest rate is a different risk than the same ratio at a high one.'],
      ['Current ratio', 'Current assets divided by current liabilities – whether short-term resources cover short-term bills. Below 1 means bills due within a year exceed the cash and near-cash on hand.'],
      ['Altman Z-score', 'A composite bankruptcy-risk score built from five accounting ratios. Above roughly 3 is considered the safe zone. Below roughly 1.8 signals meaningful distress risk.'],
    ],
  },
  {
    title: 'Accounting quality',
    note: 'The most commonly overlooked risk in a stock screen: whether reported profit is trustworthy.',
    terms: [
      ['Accruals ratio', '(Net income minus operating cash flow) divided by total assets. A persistently large gap between profit and cash is one of the most-studied predictors of future earnings disappointments and underperformance.'],
      ['Piotroski F-score', 'A nine-point checklist of profitability, leverage, and efficiency signals, each scored pass/fail and summed. Higher (toward 9) indicates broader fundamental strength. Below about 4 is weak.'],
      ['Days sales outstanding (DSO)', 'The average number of days it takes to collect payment after a sale. A rising trend can mean revenue is being booked before the cash actually arrives.'],
      ['Inventory days', 'The average number of days stock sits before it sells. A rising trend is the manufacturing and retail equivalent of the same warning DSO gives – demand may be softening faster than the income statement shows.'],
    ],
  },
  {
    title: 'Capital allocation',
    note: 'What management does with the cash the business generates – whether your ownership stake is growing or being quietly diluted.',
    terms: [
      ['Net buyback yield', 'The year-over-year change in share count, net of new shares issued, expressed as a percentage. Positive means your ownership stake grew even though you did nothing. Negative means dilution outpaced buybacks.'],
      ['Gross buyback yield', 'Cash spent on share repurchases divided by market value, before netting out new shares issued from options or compensation.'],
      ['Stock comp / revenue', 'Stock-based compensation as a share of revenue. This is a real dilution cost that does not appear as a cash expense on the income statement the way a cash salary would.'],
      ['Capex / depreciation', 'Capital expenditure divided by depreciation. A ratio under 1x means the company is spending less on new equipment and facilities than its existing assets are wearing out – a way of flattering near-term cash flow that can starve future competitiveness.'],
    ],
  },
  {
    title: 'Growth',
    terms: [
      ['Revenue growth', 'The year-over-year percentage change in total revenue.'],
      ['Earnings growth', 'The year-over-year percentage change in net income or earnings per share.'],
      ['FCF growth (3y)', 'The compound annual growth rate of free cash flow over the trailing three years – smoother than a single year-over-year figure.'],
    ],
  },
  {
    title: 'Ownership & positioning',
    note: 'Signals from who owns the stock and how it is being traded, separate from the financial statements.',
    terms: [
      ['Short interest', 'The percentage of a company’s tradable shares (its float) that are currently sold short. High short interest is not automatically bearish, but it raises the cost of being wrong if the short thesis fails.'],
      ['Days to cover', 'Total shares sold short divided by average daily trading volume – roughly how many trading days it would take for all short sellers to buy back their shares at normal volume. A high figure means any rally could be amplified by short sellers rushing to exit.'],
      ['Institutional ownership', 'The percentage of shares held by professional money managers (funds, pensions, endowments) rather than individual retail investors.'],
      ['Insider ownership', 'The percentage of shares held by a company’s own officers and directors.'],
      ['Analyst consensus', 'The average recommendation across covering analysts, typically on a 1 (strong buy) to 5 (strong sell) scale, so a lower number is more bullish.'],
      ['Target upside', 'The percentage gap between the average analyst price target and the current share price.'],
      ['Beta', 'A measure of how much a stock tends to move relative to the broader market. A beta above 1 means the stock has historically swung more than the market. Below 1 means less.'],
    ],
  },
  {
    title: 'Behaviour & tradability',
    note: 'Price trend, risk, and how easily a position can actually be bought or sold without moving the price.',
    terms: [
      ['Max drawdown', 'The deepest peak-to-trough decline in price over a given window (commonly one year here). It measures the worst pain an investor would have felt holding through the period, regardless of where the price ended up.'],
      ['Noise floor', 'How large a move against the index would have to be, over a given window, before it means anything for your particular portfolio. It is one standard error of your own tracking noise – the ordinary week-to-week wobble between you and the index – scaled to the length of the window. A +0.4% month against a ±2.4% floor is not a good month, it is a normal one, and the short-term tiles say so rather than reporting the number on its own and inviting a conclusion it cannot support. The floor grows with the square root of the window, which is why the same 2% means different things over a week and over a quarter.'],
      ['Current streak', 'How many consecutive recent observations your portfolio has finished ahead of (or behind) the index, and the calendar days those observations span. The day count matters because the underlying price history is not evenly spaced – five observations in a row can mean a week or a month depending on where in the history you are.'],
      ['Recent tracking risk', 'How much your portfolio has been moving independently of the index lately, annualized, shown against the same figure over a longer baseline. Rising above the baseline means your holdings have started behaving less like the market than usual – which is neither good nor bad in itself, but it is the quantity that sets the noise floor, so it tells you how much of any recent gap is likely to be luck.'],
      ['Active share', 'The share of your portfolio that differs from the index’s own holdings, position by position. 0% means you have effectively bought the index; 100% means you own nothing it owns. Unlike almost everything else on the page it needs no history at all – it is a fact about today’s weights – so it is readable from the first day you hold anything. It is only shown when enough of your holdings can be matched against published index constituents.'],
      ['Up capture / down capture', 'What share of the index’s gains your portfolio kept, and what share of its losses it took, measured separately over the periods the index rose and the periods it fell. Up 90 / down 60 means you keep most of the rallies while taking well under two thirds of the selloffs. Neither number means much on its own – a low up capture is the price you pay for a low down capture, and that trade can be a good one. Sharpe and information ratio blend both directions into a single figure, which is why they cannot tell a portfolio that wins by keeping up in rallies from one that wins by losing less in downturns.'],
      ['Capture spread', 'Up capture minus down capture. This is the number that settles whether the trade-off is working: positive means you keep more of the upside than you take of the downside, which is the entire justification for not just buying the index. Negative means the reverse – giving up the rallies and taking the falls anyway – and is the specific failure mode a cautious, low-beta portfolio is at risk of.'],
      ['Batting average', 'The share of calendar months in which your portfolio beat the index. It measures how *often* you win, where capture ratios measure how *much*, and the two can disagree sharply: a portfolio that wins four months in twelve with three enormous wins is a real strategy and a fragile one. The tile also shows how big a typical winning month is against a typical losing one, which is how a record below 50% can still be ahead overall. Counted monthly on purpose – a hit rate measured daily is a different and much less meaningful number.'],
      ['Longest underwater', 'The longest stretch your portfolio spent below its previous high-water mark, in calendar time rather than trading days. Maximum drawdown says how deep the hole was; this says how long you were in it, and those are very different experiences of the same percentage. A 20% fall recovered in three weeks and a 20% fall you sat in for fourteen months are not the same portfolio to live with, and duration is the part most people underestimate in advance.'],
      ['Acceleration vs S&P 500 (portfolio)', 'The same question asked of your whole portfolio rather than one holding: is the gap between your account and the index still widening? It compares the excess return your portfolio earned over the last quarter against the quarter before it, after subtracting the move your portfolio’s own beta says the market handed you – so a portfolio that only rose because the index rose does not read as accelerating. Deposits and withdrawals are netted out first, since money arriving in an account is not performance. Every other measure on that panel reports a level: how far ahead you are, how much risk you took. This one reports the change in it. A portfolio that beat the index by 8% last quarter and 1% this one is still ahead, and is losing the argument.'],
      ['Acceleration vs market', 'Whether a stock’s lead over the market is widening or narrowing, rather than how big that lead currently is. It compares the excess return earned over the most recent quarter against the quarter before it, after subtracting the move the stock’s own beta says the market handed it – so a high-beta name that only rose because the index rose does not read as accelerating. The result is quoted in standard errors (σ) of the stock’s own tracking noise, which is what lets a quiet utility and a volatile biotech be compared on the same scale: +1σ is a pickup one standard error larger than this stock’s ordinary week-to-week wobble. The most recent week is deliberately excluded, because very short-term moves tend to reverse. It is measured and displayed but carries no weight in the research score, pending evidence that it predicts anything.'],
      ['Volume confirmation', 'The ratio of trading volume on up days to volume on down days. A ratio below 1 means recent gains happened on lighter volume than recent declines – a rally that isn’t fully convincing yet.'],
      ['52-week high / low', 'The highest and lowest closing prices over the trailing year. Distance from these levels is a common (if rough) gauge of where a stock sits within its recent range.'],
      ['Volatility (annualized)', 'The annualized standard deviation of daily price changes – a statistical measure of how much a price bounces around, independent of direction.'],
      ['Implied volatility', 'The volatility level embedded in current option prices for the nearest listed expiry – the market’s forward-looking expectation of how much a stock will move.'],
      ['Realized volatility', 'The volatility a stock actually experienced over a recent window (commonly 20 trading days), calculated directly from historical price changes rather than inferred from option prices.'],
      ['Implied / realized vol ratio', 'Implied volatility divided by realized volatility. A ratio above 1x means options are pricing in more future movement than the stock has actually shown recently.'],
      ['IV skew', 'The implied volatility of an out-of-the-money put minus the implied volatility of a similarly out-of-the-money call, at the same expiration. Positive skew (the normal case for equities since the 1987 crash) means puts are priced richer than calls – read as hedging demand, not a directional signal. It is shown for context only; a single day’s reading says nothing about whether skew is steepening or flattening, which is the part that has historically mattered.'],
      ['Put/call open interest ratio', 'Total open interest across all puts at the selected expiration, divided by the same for calls. Only meaningful at its own historical extremes as a contrarian sentiment gauge – there is no evidence it has predictive value as a day-to-day ranking input, so it is shown for context only, never used to rank candidates.'],
      ['IV percentile (1y)', 'Where a stock’s most recently observed implied volatility sits (0-100) versus its own trailing one-year history of daily readings – the real thing an "IV rank" means. This app began archiving one implied-volatility reading per ticker per day (from the ~1-week options chain the Best multi-day options screen already fetches) once this feature shipped; there is no way to backfill it further back, since no data provider serves historical implied volatility, only the live chain. That means this field reads blank for roughly the first three months for any given ticker, then fills in as each one crosses 60 archived trading days – never a fabricated number in the meantime.'],
      ['Realized volatility percentile', 'Where a stock’s current 20-day realized volatility sits (0-100) versus its own trailing one-year range of that same rolling figure – the "volatility cone" technique, applied to realized (not implied) volatility. This is available immediately (no archive to wait on), and was this app’s original stand-in before "IV percentile" existed. Prefer IV percentile once it’s populated for a given ticker; this one remains useful in the meantime and as a cross-check. Blank when there isn’t enough trading history to compute it.'],
      ['Managed exit (50% / 21 DTE)', 'A position-management convention for premium-selling strategies (covered calls, cash-secured puts, iron condors): close the position once it has captured about half its maximum possible profit, and exit by around 21 days to expiration regardless of profit, since gamma risk accelerates sharply in an option’s final weeks. tastytrade’s own 314-trade strangle study found this lifted the win rate from 82% to 90% at the cost of roughly 40% less total profit versus holding to expiration – a real trade-off, not a free improvement, and self-published practitioner data rather than a peer-reviewed result.'],
      ['Single-expiry GEX (gamma exposure)', 'An estimate of dealer gamma exposure – roughly, how many dollars of the underlying a market maker would need to trade for every 1% move, given the open interest sitting at every strike of one option expiration. Positive readings are associated with dealers dampening moves (buying dips, selling rallies); negative readings with dealers amplifying them. Two honest limits: it assumes the standard but unverified convention that dealers end up net long the calls and net short the puts retail traders buy (an assumption a 2026 academic paper formalized as exactly that, not a fact), and it only covers ONE expiration – the one a given screen happens to be looking at – not the full sum across a stock’s entire options market real GEX products publish. Treat it as a rough, same-day directional cue, not a precise measurement.'],
      ['Average dollar volume', 'Average daily trading volume multiplied by share price – how much money trades hands in a typical day. Low dollar volume means a position can be harder to exit without moving the price against you.'],
    ],
  },
  {
    title: 'Scoring & guidance',
    note: 'How the research score is built and how buy/hold/sell-style guidance is decided.',
    terms: [
      ['Research score', null],
      ['Confidence', 'A measure of how complete the underlying data was for a given score, not a measure of how good the company is. Missing key inputs lowers confidence even if the metrics that are available look strong.'],
      ['Buy', 'A shadow-policy entry classification: structural quality, timing, confidence, data quality, valuation, liquidity, and portfolio capacity all pass. It is distinct from Hold.'],
      ['Accumulate', 'The shadow policy permits gradual additions because business quality is strong and timing is improving, while concentration remains acceptable.'],
      ['Hold existing position', 'Evidence supports maintaining a position already owned. It does not mean the security meets today’s entry requirements.'],
      ['Watch', 'No action. Evidence is incomplete, mixed, weakly timed, or below the confidence needed for a prescriptive company decision.'],
      ['Trim', 'Reduce an existing position. The shadow policy names whether the cause is company deterioration, concentration, valuation, tactics, or risk budget and sizes the trade from context.'],
      ['Exit position', 'Close a held position under a namespaced stop, thesis, portfolio, or explicit user rule. A position exit does not automatically mean the company thesis failed.'],
      ['Avoid', 'Do not initiate a new position under current company evidence. This is not the same as selling a position already owned.'],
      ['Sell thesis', 'Verified structural or combined company evidence has invalidated the thesis, independently of the user’s cost basis.'],
      ['Agreement count', 'How many of the three independent factors (fundamentals, market behaviour, positioning/sentiment) currently agree in the same negative direction. Guidance only moves off Hold once two or more agree.'],
      ['Sector-relative valuation', 'A modifier (±3 points) based on how cheap or expensive a company is versus its own sector peers, rather than against the whole market. Being cheap for a utility and being cheap outright are different claims.'],
      ['Macro regime', 'A modifier (±3 points) built from interest rates, inflation, labor data, and the yield curve, weighted by how sensitive a given sector is to those conditions. It never replaces company-level evidence.'],
    ],
  },
  {
    title: 'Finances',
    note: 'Terms used on the Finances tab: budgeting, savings pools, and the retirement projection.',
    terms: [
      ['Leftover', 'Monthly income minus monthly expenses in the budget subsection – the amount available to save, invest, or split into pools.'],
      ['Auto-split pool', 'A named savings bucket with a target percentage. Logging a deposit divides that dollar amount across every pool in proportion to its percentage.'],
      ['Retirement simulation', 'A range built from 5,000 paths that resample consecutive 12-month blocks of historical returns. It uses portfolio history after three years, otherwise the selected benchmark, and reports percentiles plus the probability savings last through the planned withdrawal period. Simulated outcomes are not predictions.'],
      ['Nominal balance', 'A projected future balance in future dollars, not adjusted for inflation.'],
      ['Inflation-adjusted balance', 'A projected future balance restated in today’s purchasing power by discounting for assumed inflation – a more honest read of what the balance will actually buy.'],
      ['401(k) / 403(b)', 'An employer-sponsored retirement account with pre-tax (traditional) or after-tax (Roth) contributions, deducted straight from payroll. The 2026 IRS employee deferral limit is $24,500, plus a $8,000 catch-up at 50+ or $11,250 at ages 60–63.'],
      ['Roth IRA', 'An individual retirement account funded with after-tax dollars. Qualified withdrawals in retirement are tax-free. The 2026 IRS limit is $7,500, plus a $1,100 catch-up at 50+. Eligibility to contribute phases out at higher incomes.'],
      ['Traditional IRA', 'An individual retirement account funded with pre-tax dollars (subject to income and workplace-plan rules). Withdrawals in retirement are taxed as income. Shares the same 2026 IRS limit as a Roth IRA: $7,500, plus a $1,100 catch-up at 50+.'],
      ['HSA (Health Savings Account)', 'A triple-tax-advantaged account for medical expenses, available with a qualifying high-deductible health plan. 2026 IRS limits are $4,400 self-only or $8,750 family coverage, plus a $1,000 catch-up at 55+.'],
      ['Contribution limit', 'The maximum an account holder may contribute to a tax-advantaged account in a calendar year under IRS rules. Exceeding it can trigger excise taxes, so it is tracked separately from an account’s balance.'],
      ['Catch-up contribution', 'An additional amount the IRS allows account holders past a certain age to contribute on top of the standard limit, meant to help late savers close the gap before retirement.'],
    ],
  },
]

export default function Glossary() {
  const { data } = useData('advisor.json')
  const [query, setQuery] = useState('')
  const normalized = query.trim().toLowerCase()
  const groups = useMemo(() => {
    const weights = data?.methodology?.weights || {}
    const blend = Object.entries(weights)
      .filter(([, value]) => typeof value === 'number')
      .map(([key, value]) => `${Math.round(value * 100)}% ${key.replace(/_/g, ' ')}`)
      .join(', ')
    const scoringDefinition = blend
      ? `The overall 0 to 100 company ranking uses ${blend}, then applies the capped modifiers published with the snapshot.`
      : 'The overall 0 to 100 company ranking uses the component weights in the latest published snapshot, then applies its capped modifiers.'
    return GROUPS.map((group) => ({
      ...group,
      terms: group.terms.map(([term, definition]) => [
        term,
        term === 'Research score' ? scoringDefinition : definition,
      ]),
    }))
  }, [data])

  const filtered = useMemo(() => {
    if (!normalized) return groups
    return groups
      .map((group) => ({
        ...group,
        terms: group.terms.filter(([term, def]) =>
          term.toLowerCase().includes(normalized) || def.toLowerCase().includes(normalized)),
      }))
      .filter((group) => group.terms.length)
  }, [groups, normalized])

  const totalTerms = useMemo(() => groups.reduce((sum, group) => sum + group.terms.length, 0), [groups])
  const shownTerms = filtered.reduce((sum, group) => sum + group.terms.length, 0)

  return <>
    <div className="page-head">
      <div>
        <span className="eyebrow">Reference</span>
        <h1 className="page-title">Terminology <span className="accent">glossary</span></h1>
        <p className="page-sub">Every metric and guidance term used across the app, defined in plain language. Scoring weights reflect the latest published model.</p>
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
      <section key={group.title} className="sec-label--section">
        <div className="sec-label">{group.title}</div>
        {group.note && <p className="body-copy glossary-group-note">{group.note}</p>}
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
