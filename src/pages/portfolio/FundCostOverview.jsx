// Weighted ETF expense ratio across the user's actual fund holdings (Metric Gap Matrix:
// "Can derive locally" -- per-fund expense_ratio is already published in etfs.json; this
// just aggregates it against the user's real position sizes, nothing new to fetch).

export default function FundCostOverview({ fundCost }) {
  if (!fundCost) return null
  const { expenseRatioPct, fundValue, fundCount } = fundCost

  return (
    <div className="card fund-cost-overview">
      <div className="portfolio-section-heading">
        <div><span className="eyebrow">Evidence</span><h3>Fund cost</h3></div>
      </div>
      <div className="fund-cost-stat">
        <span className="fund-cost-value">{expenseRatioPct.toFixed(2)}%</span>
        <span className="fund-cost-label">
          weighted expense ratio across {fundCount} fund{fundCount === 1 ? '' : 's'}
          {' '}(${fundValue.toLocaleString('en-US', { maximumFractionDigits: 0 })})
        </span>
      </div>
    </div>
  )
}
