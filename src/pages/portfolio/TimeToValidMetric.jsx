// How much longer until the performance block's annualized ratios (Sharpe, Sortino,
// annualized return) clear the same reliability floor exportSnapshot.js's sample_size_warning
// already gates on (src/lib/portfolioStatistics.js: SAMPLE_SIZE_WARNING_FLOOR) -- so this
// countdown and that warning can never quote two different bars for "valid."

function formatDate(iso) {
  if (!iso) return null
  return new Date(`${iso}T00:00:00Z`).toLocaleDateString('en-US', {
    timeZone: 'UTC', month: 'short', day: 'numeric', year: 'numeric',
  })
}

export default function TimeToValidMetric({ timeToValidMetric: tracker }) {
  if (!tracker?.available) return null
  const { met, observations, floor, remainingSessions, estimatedDate } = tracker

  return (
    <div className="card time-to-valid-metric">
      <div className="portfolio-section-heading">
        <div><span className="eyebrow">Evidence</span><h3>Time to valid metric</h3></div>
      </div>
      {met ? (
        <p>
          <strong>{observations}</strong> of {floor} observations reached — Sharpe, Sortino, and
          annualized return above are past this report's reliability floor.
        </p>
      ) : (
        <p>
          <strong>{observations}</strong> of {floor} observations collected.
          {' '}{remainingSessions} more market session{remainingSessions === 1 ? '' : 's'} needed
          before Sharpe, Sortino, and annualized return clear this report's reliability floor
          {estimatedDate ? <> — around <strong>{formatDate(estimatedDate)}</strong></> : null}.
        </p>
      )}
      <p className="disclaimer">{tracker.methodology || 'Counts every observation already recorded toward the same 60-observation floor the export warning uses.'}</p>
    </div>
  )
}
