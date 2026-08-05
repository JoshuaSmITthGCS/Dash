function signed(value, digits = 1) {
  return value == null ? 'Unavailable' : `${value >= 0 ? '+' : ''}${value.toFixed(digits)}%`
}

export default function PortfolioReturnSummary({ summary }) {
  if (!summary) return null
  return (
    <section className="portfolio-return-summary" aria-label="Portfolio return methods">
      <article>
        <span>Strategy return (time-weighted)</span>
        <strong>{summary.strategy.available ? signed(summary.strategy.returnPct) : 'Unavailable'}</strong>
        <small>{summary.strategy.available ? 'Modified Dietz' : summary.strategy.reason}</small>
      </article>
      <article>
        <span>Your return (money-weighted, includes timing of deposits)</span>
        <strong>{summary.moneyWeighted.available ? signed(summary.moneyWeighted.rate) : 'Unavailable'}</strong>
        <small>{summary.moneyWeighted.available ? 'Annualized XIRR' : summary.moneyWeighted.reason}</small>
      </article>
      <p>{summary.explanation}</p>
    </section>
  )
}
