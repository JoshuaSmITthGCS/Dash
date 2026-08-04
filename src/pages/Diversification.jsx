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
  const { data, loading } = useData('advisor.json')
  const { positions, loading: portfolioLoading } = useFirebasePortfolio()
  const { preferences } = usePreferences()
  if (loading || portfolioLoading) return <Loading />
  if (!positions.length) return <Empty note="Add portfolio holdings before calculating diversification." />
  const prices = buildPortfolioPriceData(data?.screen_universe || [], data?.portfolio_coverage || [], data?.research || [])
  const portfolio = enrichPortfolio(positions, prices)
  const result = diversificationScore(portfolio.positions)
  const sectors = groupedWeights(result.weights || [], 'sector')
  const industries = groupedWeights(result.weights || [], 'industry')
  const stops = sectors.reduce((output, [, pct], index) => { const start = sectors.slice(0, index).reduce((sum, [, value]) => sum + value, 0); output.push(`${COLORS[index % COLORS.length]} ${start}% ${start + pct}%`); return output }, []).join(', ')
  const money = (value) => preferences.privacyMode ? '••••••' : formatPreferenceMoney(value, preferences.numberFormat)
  return <div className="diversification-page"><header className="page-head"><div><span className="eyebrow">Portfolio analytics</span><h1 className="page-title">Diversification</h1><p className="page-sub">A transparent concentration score based on priced positions, sector and industry exposure, and meaningful position count.</p></div><Link className="secondary-button compact" to="/portfolio">Back to portfolio</Link></header>
    <section className="diversification-hero"><div className="diversification-score" style={{ '--score': result.score }}><strong>{result.score}</strong><span>/100</span><small>{result.provisional ? 'Provisional score' : 'Diversification score'}</small></div><div><h2>{result.score >= 80 ? 'Broadly diversified' : result.score >= 60 ? 'Moderately diversified' : 'Concentration needs attention'}</h2><p>Coverage: {Math.round(result.coveragePct)}% of entered positions have a current price. This score is descriptive and does not say whether a holding is suitable.</p>{result.warnings.length ? <ul>{result.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul> : <p>No threshold-based concentration warnings.</p>}</div></section>
    <section className="diversification-grid"><article className="allocation-card"><h2>Sector allocation</h2><div className="allocation-donut" style={{ background: `conic-gradient(${stops || 'var(--border) 0 100%'})` }}><span>{sectors.length}<small>sectors</small></span></div><div className="allocation-legend">{sectors.map(([label, pct], index) => <div key={label}><i style={{ background: COLORS[index % COLORS.length] }} /><span>{label}</span><b>{pct.toFixed(1)}%</b></div>)}</div></article><article className="score-components"><h2>Score components</h2>{Object.entries(result.components).map(([key, value]) => <div key={key}><span>{key.replace(/([A-Z])/g, ' $1')}</span><progress max="100" value={value}>{Math.round(value)}</progress><b>{Math.round(value)}</b></div>)}<small>Weights: position balance 30%, top-five balance 20%, sector balance 25%, industry balance 15%, meaningful positions 10%.</small></article></section>
    <section className="report-section"><header className="section-heading"><div><span className="eyebrow">Position concentration</span><h2>Holdings by allocation</h2></div></header><div className="diversification-holdings">{result.weights?.map((row) => <div key={row.id || row.ticker}><CompanyLogo company={row.priceInfo || row} size={36} /><div><strong>{row.ticker}</strong><span>{row.priceInfo?.name || 'Covered holding'}</span></div><span className="allocation-bar"><i style={{ width: `${row.pct}%` }} /></span><b>{row.pct.toFixed(1)}%</b><small>{money(row.currentValue)}</small></div>)}</div></section>
    <section className="report-two-column"><article className="allocation-card"><h2>Industry concentration</h2>{industries.slice(0, 10).map(([label, pct]) => <div className="plain-allocation-row" key={label}><span>{label}</span><b>{pct.toFixed(1)}%</b></div>)}</article><article className="allocation-card"><h2>How to read this</h2><p>Large single positions, a concentrated top five, and dominant sector or industry exposures reduce the score. Very small positions below 2% do not count as meaningful diversification.</p><p>Unclassified holdings remain visible and reduce confidence. ETFs are classified using the available source metadata; look-through fund holdings are not available.</p></article></section>
  </div>
}
