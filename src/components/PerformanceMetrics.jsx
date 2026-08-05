function ratio(value) {
  return value == null || !Number.isFinite(value) ? 'Unavailable' : value.toFixed(2)
}

function percent(value) {
  return value == null || !Number.isFinite(value) ? 'Unavailable' : `${value.toFixed(1)}%`
}

export default function PerformanceMetrics({ metrics, benchmarkLabel = 'benchmark', riskFree }) {
  return (
    <section className="performance-metrics" aria-labelledby="standard-performance-title">
      <header><div><span className="eyebrow">Standard measures</span><h2 id="standard-performance-title">Risk and performance</h2></div><small>{metrics?.available ? `${metrics.observations} daily returns` : metrics?.reason}</small></header>
      <div>
        <article><span>Information ratio</span><strong>{ratio(metrics?.informationRatio)}</strong><small>Versus {benchmarkLabel}</small></article>
        <article><span>Sharpe ratio</span><strong>{ratio(metrics?.sharpe)}</strong><small>{riskFree?.fallback ? 'Configured fallback' : riskFree?.series} {riskFree?.annualPct?.toFixed(2) ?? '0.00'}%</small></article>
        <article><span>Sortino ratio</span><strong>{ratio(metrics?.sortino)}</strong><small>Downside risk only</small></article>
        <article><span>Calmar ratio</span><strong>{ratio(metrics?.calmar)}</strong><small>Return per drawdown</small></article>
        <article><span>Maximum drawdown</span><strong>{percent(metrics?.maxDrawdown)}</strong><small>Worst peak decline</small></article>
        <article><span>Current drawdown</span><strong>{percent(metrics?.currentDrawdown)}</strong><small>From high-water mark</small></article>
      </div>
    </section>
  )
}
