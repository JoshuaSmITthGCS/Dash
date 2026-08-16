// View 02 — Performance. Time-weighted return against the selected benchmark, plus the
// opportunity-cost comparison from the recorded purchase dates.
//
// This view always reads full holdings history; the Data overview's scope switch narrows
// the statistics, not this chart.

import GrowthChart from '../../components/GrowthChart'
import Icon from '../../components/Icons'
import { compareBenchmarkSeries, selectPeriod } from '../../lib/portfolioAnalytics.js'
import { moveColor, PERFORMANCE_PERIODS, PERIOD_NAMES, signedPct } from './format.js'

export default function Performance({
  holdings,
  holdingsSeriesFull,
  benchmarks,
  performancePeriod,
  onPerformancePeriodChange,
}) {
  const { growth, versusIndex } = holdings
  const { analyticsBenchmarkSeries, selectedBenchmarkSymbol, selectedBenchmarkLabel } = benchmarks

  const comparison = compareBenchmarkSeries(
    selectPeriod(holdingsSeriesFull, performancePeriod),
    analyticsBenchmarkSeries ? [{
      symbol: selectedBenchmarkSymbol,
      label: selectedBenchmarkLabel,
      dates: analyticsBenchmarkSeries.dates,
      values: analyticsBenchmarkSeries.values,
    }] : [],
  )
  const performanceIndex = comparison ? {
    dates: comparison.dates,
    portfolio: comparison.portfolio.values.map((value) => 100 * value / comparison.portfolio.values[0]),
    benchmark: comparison.benchmarks[0].values.map((value) => 100 * value / comparison.benchmarks[0].values[0]),
  } : null

  return (
    <section className="portfolio-dashboard-section portfolio-performance-section" aria-labelledby="portfolio-performance-title">
      <header className="portfolio-section-heading">
        <div><span className="portfolio-section-number">02</span><div><span className="eyebrow">Benchmark</span><h2 id="portfolio-performance-title">Performance</h2></div></div>
        <label><span>Compare over</span><select value={performancePeriod} onChange={(event) => onPerformancePeriodChange(event.target.value)}>{PERFORMANCE_PERIODS.map((period) => <option key={period} value={period}>{PERIOD_NAMES[period]}</option>)}</select></label>
      </header>
      {performanceIndex ? <div className="portfolio-benchmark-chart">
        <div className="portfolio-benchmark-kpis">
          <span><small>Time-weighted return</small><strong className={comparison.portfolio.returnPct >= 0 ? 'positive' : 'negative'}>{signedPct(comparison.portfolio.returnPct, 2)}</strong></span>
          <span><small>{selectedBenchmarkLabel}</small><strong className={comparison.benchmarks[0].returnPct >= 0 ? 'positive' : 'negative'}>{signedPct(comparison.benchmarks[0].returnPct, 2)}</strong></span>
          <span><small>Difference</small><strong className={comparison.portfolio.returnPct - comparison.benchmarks[0].returnPct >= 0 ? 'positive' : 'negative'}>{signedPct(comparison.portfolio.returnPct - comparison.benchmarks[0].returnPct, 2)}</strong></span>
        </div>
        <GrowthChart
          height={330}
          width={1080}
          dates={performanceIndex.dates}
          series={[
            { label: 'Portfolio TWR', values: performanceIndex.portfolio, color: 'var(--series-stock)', emphasis: true },
            { label: selectedBenchmarkLabel, values: performanceIndex.benchmark, color: 'var(--series-benchmark)', dashPattern: '7 5' },
          ]}
          valueFormatter={(value) => signedPct(value - 100, 1)}
          caption={`Both lines start at 0% on the same market date. Your line reprices today's exact shares at matched historical closes, so cash transfers cannot affect it; ${selectedBenchmarkLabel} uses the same dates.`}
          lineStyle="line"
        />
      </div> : <div className="unavailable-panel"><strong>Comparison history is still building</strong><p>Two shared market dates are needed to compare your current holdings with {selectedBenchmarkLabel}.</p></div>}

      {growth && (
        <details className="card portfolio-comparison">
          <summary>
            <div>
              <span className="eyebrow">Opportunity cost</span>
              <strong>What if I chose the S&amp;P 500–or did not invest?</strong>
              <small>Same cost-basis dollars on your recorded purchase dates</small>
            </div>
            <div className="comparison-summary-side">
              {versusIndex && <span className="comparison-edge" style={{ color: moveColor(versusIndex.excessReturnPct) }}>{signedPct(versusIndex.excessReturnPct)} vs S&amp;P</span>}
              <span className="comparison-toggle" aria-hidden="true"><Icon name="chevron" size={18} /></span>
            </div>
          </summary>
          <div className="portfolio-comparison-chart">
            <GrowthChart
              dates={growth.dates}
              series={[
                { label: 'My holdings', values: growth.holdings, color: 'var(--series-stock)', emphasis: true },
                { label: 'S&P 500, same cost basis', values: growth.benchmark, color: 'var(--series-benchmark)', dashPattern: '7 5' },
                { label: 'Cost basis held flat', values: growth.cash, color: 'var(--series-cash)', dashPattern: '2 5' },
              ]}
              title="One-to-one performance from your investment dates"
              caption={`Each holding starts with its exact cost-basis dollars on its recorded purchase date, then follows that stock’s price return. The S&P receives the identical starting dollars on the identical date; the flat line leaves that cost basis unchanged. Covers ${growth.trackedTickers.length} dated position${growth.trackedTickers.length === 1 ? '' : 's'} from ${growth.firstInvestmentDate}${growth.untrackedCount ? `. ${growth.untrackedCount} missing a usable date or published history` : ''}.`}
              zoomable
            />
          </div>
        </details>
      )}
    </section>
  )
}
