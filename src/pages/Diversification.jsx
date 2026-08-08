import { Link } from 'react-router-dom'
import { useData } from '../lib/useData.js'
import { useFirebasePortfolio } from '../lib/useFirebasePortfolio.js'
import { buildPortfolioPriceData } from '../lib/portfolioPosition.js'
import { currentHoldingsSeries, diversificationScore, enrichPortfolio, portfolioRiskDecomposition } from '../lib/portfolioAnalytics.js'
import { aggregateThemeExposure, factorRegression } from '../lib/factorAnalytics.js'
import { formatPreferenceMoney, usePreferences } from '../lib/PreferencesContext.jsx'
import { Loading, Empty } from '../components/Bits.jsx'
import CompanyLogo from '../components/CompanyLogo.jsx'
import InfoTag from '../components/InfoTag.jsx'

const COLORS = ['#315f49', '#64866d', '#8ba692', '#b5c6b8', '#c89b64', '#92735d', '#7c8992', '#b0aaa1']

function groupedWeights(weights, field) {
  return Object.entries(weights.reduce((result, row) => { const key = row.priceInfo?.[field] || 'Unclassified'; result[key] = (result[key] || 0) + row.pct; return result }, {})).sort((a, b) => b[1] - a[1])
}

export default function Diversification() {
  const { data, loading } = useData('report.json')
  const { data: etfData, loading: etfLoading } = useData('etfs.json')
  const { data: factorData, loading: factorLoading } = useData('factors/french.json')
  const { data: advisorData, loading: advisorLoading } = useData('advisor.json')
  const { data: benchmarkReport, loading: benchmarkLoading } = useData('benchmark-report.json')
  const { positions, loading: portfolioLoading } = useFirebasePortfolio()
  const { preferences } = usePreferences()
  if (loading || portfolioLoading || etfLoading || factorLoading || advisorLoading || benchmarkLoading) return <Loading />
  if (!positions.length) return <Empty note="Add portfolio holdings before calculating diversification." />
  const prices = buildPortfolioPriceData(data?.screen_universe || [], data?.portfolio_coverage || [], data?.research || [])
  const portfolio = enrichPortfolio(positions, prices)
  const result = diversificationScore(portfolio.positions, { etfs: etfData?.etfs || [] })
  const benchmarkSymbol = preferences.defaultBenchmark
  const benchmarkHistory = benchmarkReport?.histories?.[benchmarkSymbol]
    || (data?.benchmark_history?.dates ? { dates: data.benchmark_history.dates, closes: data.benchmark_history.closes } : null)
  const benchmarkWeights = (etfData?.etfs || []).find((row) => row.ticker === benchmarkSymbol)?.top_holdings
  const risk = portfolioRiskDecomposition(portfolio.positions, {
    benchmarkHistory,
    benchmarkWeights,
    etfs: etfData?.etfs || [],
  })
  const portfolioSeries = currentHoldingsSeries(positions, prices)
  const factors = factorRegression(portfolioSeries, factorData)
  const themes = aggregateThemeExposure(portfolio.positions, advisorData?.theme_screen?.by_ticker || {})
  const sectors = (result.sectorExposures || []).map((row) => [row.label, row.pct])
  const industries = groupedWeights(result.weights || [], 'industry')
  const stops = sectors.reduce((output, [, pct], index) => { const start = sectors.slice(0, index).reduce((sum, [, value]) => sum + value, 0); output.push(`${COLORS[index % COLORS.length]} ${start}% ${start + pct}%`); return output }, []).join(', ')
  const money = (value) => preferences.privacyMode ? '••••••' : formatPreferenceMoney(value, preferences.numberFormat)
  return <div className="diversification-page"><header className="page-head"><div><span className="eyebrow">Portfolio analytics</span><h1 className="page-title">Diversification</h1><p className="page-sub">Concentration, ETF look-through, and common movement across your holdings.</p></div><Link className="secondary-button compact" to="/portfolio">Back to portfolio</Link></header>
    <section className="diversification-hero"><div className="diversification-score" style={{ '--score': result.score }}><strong>{result.score}</strong><span>/100</span><small>{result.provisional ? 'Provisional score' : 'Diversification score'}</small></div><div><h2>You hold {result.rawHoldingCount} positions. You hold {result.effectiveBets == null ? 'an unavailable number of' : result.effectiveBets.toFixed(1)} effective bets.
      <InfoTag label="Effective bets">
        <strong>Diversification score &amp; effective bets</strong>
        <p>"Effective bets" measures how many genuinely independent return patterns your holdings
          actually produced, not just how many tickers you own - ten highly correlated stocks might
          only behave like two or three independent bets. The score blends effective bets/diversification
          ratio (when correlation history is available) with HHI-based holding, sector, and industry
          breadth. See "How to read this" below for HHI and effective holdings.</p>
      </InfoTag>
    </h2><p>{result.score >= 80 ? 'Broadly diversified' : result.score >= 60 ? 'Moderately diversified' : 'Concentration needs attention'}</p><div className="effective-bet-summary"><span>Raw holdings<strong>{result.rawHoldingCount}</strong><small>priced positions</small></span><span>Effective bets<strong>{result.effectiveBets == null ? 'Unavailable' : result.effectiveBets.toFixed(1)}</strong><small>{result.correlation.available ? `${result.correlation.tickers.length} holdings and ${result.correlation.observations} common returns` : result.correlation.reason}</small></span><span>Effective holdings<strong>{result.effectiveHoldings.toFixed(1)}</strong><small>1 divided by HHI</small></span></div><p>Coverage: {Math.round(result.coveragePct)}% of entered positions have a current price. This score is descriptive and does not say whether a holding is suitable.</p>{result.lookThrough.unresolvedDollars > 0 && <p><strong>{money(result.lookThrough.unresolvedDollars)}</strong> is unresolved ETF exposure because published look-through data is unavailable.</p>}{result.warnings.length ? <ul>{result.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul> : <p>No concentration warnings in covered holdings.</p>}</div></section>
    <section className="diversification-grid"><article className="allocation-card"><h2>Look-through sector allocation
      <InfoTag label="Look-through sector allocation">
        <strong>Look-through sector allocation</strong>
        <p>Your portfolio's sector exposure "looking through" ETF holdings to their published
          underlying sector weights, not just treating each fund as one undifferentiated block -
          two portfolios that look diversified by ticker count can be concentrated in the same sector
          once fund holdings are decomposed.</p>
      </InfoTag>
    </h2><div className="allocation-donut" style={{ background: `conic-gradient(${stops || 'var(--border) 0 100%'})` }}><span>{sectors.length}<small>sectors</small></span></div><div className="allocation-legend">{sectors.map(([label, pct], index) => <div key={label}><i style={{ background: COLORS[index % COLORS.length] }} /><span>{label}</span><b>{pct.toFixed(1)}%</b></div>)}</div></article><article className="score-components"><h2>Score components
      <InfoTag label="Score components" align="right">
        <strong>Score components</strong>
        <p>The individual 0–100 inputs that blend into the diversification score above - each bar is
          one factor (holding breadth, sector breadth, industry breadth, and, when correlation history
          is available, effective bets and diversification ratio).</p>
      </InfoTag>
    </h2>{Object.entries(result.components).map(([key, value]) => <div key={key}><span>{key.replace(/([A-Z])/g, ' $1')}</span><progress max="100" value={value ?? 0}>{value == null ? 'Unavailable' : Math.round(value)}</progress><b>{value == null ? 'N/A' : Math.round(value)}</b></div>)}<small>Effective bets and diversification ratio carry half the score when correlation history is available. HHI-based holding, sector, and industry breadth carry the other half.</small></article></section>
    {result.correlation.available && <section className="report-section"><header className="section-heading"><div><span className="eyebrow">Trailing daily returns</span><h2>Pairwise correlation matrix
      <InfoTag label="Pairwise correlation matrix">
        <strong>Pairwise correlation matrix</strong>
        <p>How closely each pair of holdings' daily returns moved together, from -1 (perfectly
          opposite) to +1 (moved in lockstep). High correlation across most pairs means the portfolio
          has less real diversification than its holding count suggests, even if sectors differ.</p>
      </InfoTag>
    </h2></div><span className="settings-value">Diversification ratio {result.diversificationRatio == null ? 'Unavailable' : result.diversificationRatio.toFixed(2)}</span></header><div className="correlation-table-wrap"><table className="correlation-table"><thead><tr><th scope="col">Holding</th>{result.correlation.tickers.map((ticker) => <th scope="col" key={ticker}>{ticker}</th>)}</tr></thead><tbody>{result.correlation.tickers.map((ticker, rowIndex) => <tr key={ticker}><th scope="row">{ticker}</th>{result.correlation.matrix[rowIndex].map((value, columnIndex) => <td key={result.correlation.tickers[columnIndex]}>{value.toFixed(2)}</td>)}</tr>)}</tbody></table></div></section>}
    <section className="report-section"><header className="section-heading"><div><span className="eyebrow">Covariance decomposition</span><h2>What carries the risk
      <InfoTag label="What carries the risk">
        <strong>What carries the risk</strong>
        <p>Decomposes total portfolio risk into each holding's percent contribution - a position can be
          a small dollar weight but still carry an outsized share of total risk if it is volatile and
          poorly correlated with the rest of the portfolio. Expected shortfall is the average return on
          the worst 5% of observed days.</p>
      </InfoTag>
    </h2></div></header>{risk.available ? <><div className="report-chart-summary"><div className="report-metric"><span>Expected shortfall 95%</span><strong>{risk.expectedShortfall95Pct.toFixed(2)}%</strong><small>Average return in the worst 5% of observed days</small></div><div className="report-metric"><span>Tracking error</span><strong>{risk.trackingErrorPct == null ? 'Unavailable' : `${risk.trackingErrorPct.toFixed(1)}%`}</strong><small>Annualized versus {benchmarkSymbol}</small></div><div className="report-metric"><span>Active share</span><strong>{risk.activeSharePct == null ? 'Unavailable' : `${risk.activeSharePct.toFixed(1)}%`}</strong><small>Shown only with sufficient benchmark constituent coverage</small></div></div><div className="correlation-table-wrap"><table className="correlation-table"><thead><tr><th scope="col">Holding</th><th scope="col">Portfolio weight</th><th scope="col">Share of total risk</th></tr></thead><tbody>{risk.contributions.map((row) => <tr key={row.ticker}><th scope="row">{row.ticker}</th><td>{row.weightPct.toFixed(1)}%</td><td>{row.percentContributionToRisk.toFixed(1)}%</td></tr>)}</tbody></table></div></> : <p>{risk.reason}</p>}</section>
    <section className="report-section"><header className="section-heading"><div><span className="eyebrow">Five factors plus momentum</span><h2>Portfolio factor exposure
      <InfoTag label="Portfolio factor exposure">
        <strong>Portfolio factor exposure</strong>
        <p>A regression of your portfolio's monthly returns against the Fama-French five factors plus
          momentum (market, size, value, profitability, investment, momentum) - shows which systematic
          risk factors actually drove your returns, not just which stocks you hold. A t-statistic under
          2 on alpha is not meaningful evidence of skill beyond the factors.</p>
      </InfoTag>
    </h2></div>{factors.available && <span className="settings-value">R² {(factors.rSquared * 100).toFixed(1)}%</span>}</header>{factors.available ? <><p>{factors.summary}</p><div className="factor-loading-grid">{Object.entries(factors.loadings).map(([key, value]) => <div key={key}><span>{key.replace('_', ' ')}</span><strong>{value.toFixed(2)}</strong><small>Standard error {factors.standardErrors[key].toFixed(2)}</small></div>)}</div><p>Annualized alpha {factors.alphaAnnualPct.toFixed(2)}% with a t-statistic of {factors.alphaTStatistic?.toFixed(2) ?? 'unavailable'}. A t-statistic under 2 is not meaningful evidence of alpha.</p><small>{factors.observations} monthly observations from {factors.startMonth} through {factors.endMonth}</small></> : <div className="unavailable-panel"><strong>Factor history is accumulating</strong><p>{factors.reason}</p></div>}</section>
    <section className="report-section"><header className="section-heading"><div><span className="eyebrow">Independent lens</span><h2>Theme exposure
      <InfoTag label="Theme exposure">
        <strong>Theme exposure</strong>
        <p>How much of your portfolio, by dollar coverage, is exposed to each structural trend theme
          (e.g. AI infrastructure) - see /screens/themes for the full per-company leaderboard behind
          these numbers. Independent from the research score by design; price momentum contributes
          nothing to it.</p>
      </InfoTag>
    </h2></div></header>{themes.length ? <div className="factor-loading-grid">{themes.slice(0, 6).map((theme) => <div key={theme.theme}><span>{theme.theme}</span><strong>{theme.exposureScore.toFixed(0)}</strong><small>{theme.portfolioCoveragePct.toFixed(0)}% portfolio coverage</small></div>)}</div> : <p>Theme exposure is unavailable in the current research snapshot. It remains independent from the research score.</p>}</section>
    <section className="report-section"><header className="section-heading"><div><span className="eyebrow">Position concentration</span><h2>Holdings by allocation
      <InfoTag label="Holdings by allocation">
        <strong>Holdings by allocation</strong>
        <p>Every covered position ranked by its share of total portfolio value - the fastest way to
          see which single holding you'd feel most if it moved sharply.</p>
      </InfoTag>
    </h2></div></header><div className="diversification-holdings">{result.weights?.map((row) => <div key={row.id || row.ticker}><CompanyLogo company={row.priceInfo || row} size={36} /><div><strong>{row.ticker}</strong><span>{row.priceInfo?.name || 'Covered holding'}</span></div><span className="allocation-bar"><i style={{ width: `${row.pct}%` }} /></span><b>{row.pct.toFixed(1)}%</b><small>{money(row.currentValue)}</small></div>)}</div></section>
    <section className="report-two-column"><article className="allocation-card"><h2>Industry concentration
      <InfoTag label="Industry concentration">
        <strong>Industry concentration</strong>
        <p>A finer cut than sector - two holdings can sit in different sectors but the same industry
          (or vice versa share a sector while operating nothing alike). Same look-through methodology
          as sector allocation above.</p>
      </InfoTag>
    </h2>{industries.slice(0, 10).map(([label, pct]) => <div className="plain-allocation-row" key={label}><span>{label}</span><b>{pct.toFixed(1)}%</b></div>)}</article><article className="allocation-card"><h2>How to read this</h2><p>HHI shows concentration across every weight. Effective holdings is its reciprocal. Effective bets goes further by measuring how many independent return patterns those holdings produced.</p><p>ETF weights are decomposed into published sectors when Yahoo supplies them. Missing look-through stays visible as unavailable and makes the result provisional.</p></article></section>
  </div>
}
