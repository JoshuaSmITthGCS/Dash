import { Link } from 'react-router-dom'
import { useData } from '../lib/useData.js'
import { useFirebasePortfolio } from '../lib/useFirebasePortfolio.js'
import { buildPortfolioPriceData } from '../lib/portfolioPosition.js'
import { diversificationScore, enrichPortfolio } from '../lib/portfolioAnalytics.js'
import { formatPreferenceMoney, usePreferences } from '../lib/PreferencesContext.jsx'
import { Loading, Empty } from '../components/Bits.jsx'
import CompanyLogo from '../components/CompanyLogo.jsx'

const COLORS = ['#315f49', '#64866d', '#8ba692', '#b5c6b8', '#c89b64', '#92735d', '#7c8992', '#b0aaa1']

function groupedWeights(weights, field) {
  return Object.entries(weights.reduce((result, row) => { const key = row.priceInfo?.[field] || 'Unclassified'; result[key] = (result[key] || 0) + row.pct; return result }, {})).sort((a, b) => b[1] - a[1])
}

export default function Diversification() {
  const { data, loading } = useData('report.json')
  const { data: etfData, loading: etfLoading } = useData('etfs.json')
  const { positions, loading: portfolioLoading } = useFirebasePortfolio()
  const { preferences } = usePreferences()
  if (loading || portfolioLoading || etfLoading) return <Loading />
  if (!positions.length) return <Empty note="Add portfolio holdings before calculating diversification." />
  const prices = buildPortfolioPriceData(data?.screen_universe || [], data?.portfolio_coverage || [], data?.research || [])
  const portfolio = enrichPortfolio(positions, prices)
  const result = diversificationScore(portfolio.positions, { etfs: etfData?.etfs || [] })
  const sectors = (result.sectorExposures || []).map((row) => [row.label, row.pct])
  const industries = groupedWeights(result.weights || [], 'industry')
  const stops = sectors.reduce((output, [, pct], index) => { const start = sectors.slice(0, index).reduce((sum, [, value]) => sum + value, 0); output.push(`${COLORS[index % COLORS.length]} ${start}% ${start + pct}%`); return output }, []).join(', ')
  const money = (value) => preferences.privacyMode ? '••••••' : formatPreferenceMoney(value, preferences.numberFormat)
  return <div className="diversification-page"><header className="page-head"><div><span className="eyebrow">Portfolio analytics</span><h1 className="page-title">Diversification</h1><p className="page-sub">Concentration, ETF look-through, and common movement across your holdings.</p></div><Link className="secondary-button compact" to="/portfolio">Back to portfolio</Link></header>
    <section className="diversification-hero"><div className="diversification-score" style={{ '--score': result.score }}><strong>{result.score}</strong><span>/100</span><small>{result.provisional ? 'Provisional score' : 'Diversification score'}</small></div><div><h2>{result.score >= 80 ? 'Broadly diversified' : result.score >= 60 ? 'Moderately diversified' : 'Concentration needs attention'}</h2><div className="effective-bet-summary"><span>You hold<strong>{result.rawHoldingCount}</strong><small>priced holdings</small></span><span>Effective bets<strong>{result.effectiveBets == null ? 'Unavailable' : result.effectiveBets.toFixed(1)}</strong><small>{result.correlation.available ? `${result.correlation.tickers.length} holdings and ${result.correlation.observations} common returns` : result.correlation.reason}</small></span><span>Effective holdings<strong>{result.effectiveHoldings.toFixed(1)}</strong><small>1 divided by HHI</small></span></div><p>Coverage: {Math.round(result.coveragePct)}% of entered positions have a current price. This score is descriptive and does not say whether a holding is suitable.</p>{result.warnings.length ? <ul>{result.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul> : <p>No concentration warnings in covered holdings.</p>}</div></section>
    <section className="diversification-grid"><article className="allocation-card"><h2>Look-through sector allocation</h2><div className="allocation-donut" style={{ background: `conic-gradient(${stops || 'var(--border) 0 100%'})` }}><span>{sectors.length}<small>sectors</small></span></div><div className="allocation-legend">{sectors.map(([label, pct], index) => <div key={label}><i style={{ background: COLORS[index % COLORS.length] }} /><span>{label}</span><b>{pct.toFixed(1)}%</b></div>)}</div></article><article className="score-components"><h2>Score components</h2>{Object.entries(result.components).map(([key, value]) => <div key={key}><span>{key.replace(/([A-Z])/g, ' $1')}</span><progress max="100" value={value ?? 0}>{value == null ? 'Unavailable' : Math.round(value)}</progress><b>{value == null ? 'N/A' : Math.round(value)}</b></div>)}<small>Effective bets and diversification ratio carry half the score when correlation history is available. HHI-based holding, sector, and industry breadth carry the other half.</small></article></section>
    {result.correlation.available && <section className="report-section"><header className="section-heading"><div><span className="eyebrow">Trailing daily returns</span><h2>Pairwise correlation matrix</h2></div><span className="settings-value">Diversification ratio {result.diversificationRatio == null ? 'Unavailable' : result.diversificationRatio.toFixed(2)}</span></header><div className="correlation-table-wrap"><table className="correlation-table"><thead><tr><th scope="col">Holding</th>{result.correlation.tickers.map((ticker) => <th scope="col" key={ticker}>{ticker}</th>)}</tr></thead><tbody>{result.correlation.tickers.map((ticker, rowIndex) => <tr key={ticker}><th scope="row">{ticker}</th>{result.correlation.matrix[rowIndex].map((value, columnIndex) => <td key={result.correlation.tickers[columnIndex]}>{value.toFixed(2)}</td>)}</tr>)}</tbody></table></div></section>}
    <section className="report-section"><header className="section-heading"><div><span className="eyebrow">Position concentration</span><h2>Holdings by allocation</h2></div></header><div className="diversification-holdings">{result.weights?.map((row) => <div key={row.id || row.ticker}><CompanyLogo company={row.priceInfo || row} size={36} /><div><strong>{row.ticker}</strong><span>{row.priceInfo?.name || 'Covered holding'}</span></div><span className="allocation-bar"><i style={{ width: `${row.pct}%` }} /></span><b>{row.pct.toFixed(1)}%</b><small>{money(row.currentValue)}</small></div>)}</div></section>
    <section className="report-two-column"><article className="allocation-card"><h2>Industry concentration</h2>{industries.slice(0, 10).map(([label, pct]) => <div className="plain-allocation-row" key={label}><span>{label}</span><b>{pct.toFixed(1)}%</b></div>)}</article><article className="allocation-card"><h2>How to read this</h2><p>HHI shows concentration across every weight. Effective holdings is its reciprocal. Effective bets goes further by measuring how many independent return patterns those holdings produced.</p><p>ETF weights are decomposed into published sectors when Yahoo supplies them. Missing look-through stays visible as unavailable and makes the result provisional.</p></article></section>
  </div>
}
