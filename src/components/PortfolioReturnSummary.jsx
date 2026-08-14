function signed(value, digits = 1) {
  return value == null ? 'Unavailable' : `${value >= 0 ? '+' : ''}${value.toFixed(digits)}%`
}

function ReturnBar({ value }) {
  if (value == null || !Number.isFinite(value)) return null
  const capped = Math.min(Math.abs(value), 100)
  const width = Math.max(2, capped)
  return (
    <i className={`return-bar ${value >= 0 ? 'positive' : 'negative'}`}
      style={{ width: `${width}%` }} aria-hidden="true" />
  )
}

export default function PortfolioReturnSummary({ summary }) {
  if (!summary) return null
  return (
    <section className="portfolio-return-summary" aria-label="Portfolio return methods">
      <article>
        <span>Strategy return (time-weighted)</span>
        <strong>{summary.strategy.available ? signed(summary.strategy.returnPct) : 'Unavailable'}</strong>
        {summary.strategy.available && <ReturnBar value={summary.strategy.returnPct} />}
        <small>{summary.strategy.available ? 'Modified Dietz' : summary.strategy.reason}</small>
      </article>
      <article>
        <span>Your return (money-weighted, includes timing of deposits)</span>
        <strong>{summary.moneyWeighted.available ? signed(summary.moneyWeighted.rate) : 'Unavailable'}</strong>
        {summary.moneyWeighted.available && <ReturnBar value={summary.moneyWeighted.rate} />}
        <small>{summary.moneyWeighted.available ? 'Annualized XIRR' : summary.moneyWeighted.reason}</small>
      </article>
      <p>{summary.explanation}</p>
    </section>
  )
}
