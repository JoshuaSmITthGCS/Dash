/**
 * Data Freshness Indicator
 *
 * Shows when data was last updated and alerts users to stale data.
 * Transparency: users should know if they're looking at old information.
 */

export default function DataFreshnessIndicator({ timestamp, type = 'price', threshold = 24 }) {
  if (!timestamp) {
    return (
      <div style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 4,
        fontSize: 11,
        opacity: 0.7
      }}>
        <span>⚠️</span>
        <span>No timestamp</span>
      </div>
    )
  }

  const now = new Date()
  const updatedAt = new Date(timestamp)
  const hoursAgo = (now - updatedAt) / (1000 * 60 * 60)
  const daysAgo = hoursAgo / 24

  // Determine freshness level
  let status = 'fresh'
  let color = 'var(--pos)'
  let icon = '✓'
  let label = 'Current'

  if (hoursAgo > threshold * 24) {
    // Very stale (beyond threshold days)
    status = 'stale'
    color = 'var(--neg)'
    icon = '⚠️'
    label = 'Stale'
  } else if (hoursAgo > threshold * 12) {
    // Getting old (half threshold)
    status = 'aging'
    color = 'orange'
    icon = '⏱'
    label = 'Aging'
  } else if (hoursAgo > 24) {
    // Recent but not current
    status = 'recent'
    color = '#3b82f6'
    icon = '✓'
    label = 'Recent'
  }

  // Format time ago
  let timeAgo
  if (hoursAgo < 1) {
    const minutesAgo = Math.floor(hoursAgo * 60)
    timeAgo = `${minutesAgo}m ago`
  } else if (hoursAgo < 24) {
    timeAgo = `${Math.floor(hoursAgo)}h ago`
  } else if (daysAgo < 30) {
    timeAgo = `${Math.floor(daysAgo)}d ago`
  } else {
    const monthsAgo = Math.floor(daysAgo / 30)
    timeAgo = `${monthsAgo}mo ago`
  }

  const formattedDate = updatedAt.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: updatedAt.getFullYear() !== now.getFullYear() ? 'numeric' : undefined,
    hour: '2-digit',
    minute: '2-digit'
  })

  return (
    <div
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 4,
        fontSize: 11,
        color,
        fontFamily: 'var(--font-mono)'
      }}
      title={`Last updated: ${formattedDate}\nStatus: ${label}\nType: ${type}`}
    >
      <span>{icon}</span>
      <span>{timeAgo}</span>
    </div>
  )
}

/**
 * Batch freshness summary
 * Shows overall data quality for a list of timestamps
 */
export function DataFreshnessSummary({ timestamps, type = 'mixed' }) {
  if (!timestamps || timestamps.length === 0) {
    return (
      <div style={{
        padding: 12,
        background: 'var(--bg-elev)',
        borderRadius: 8,
        border: '1px solid var(--border)',
        fontSize: 12,
        textAlign: 'center',
        opacity: 0.7
      }}>
        No timestamp data available
      </div>
    )
  }

  const now = new Date()
  const ages = timestamps
    .filter(t => t)
    .map(t => (now - new Date(t)) / (1000 * 60 * 60)) // hours

  if (ages.length === 0) {
    return (
      <div style={{
        padding: 12,
        background: 'var(--bg-elev)',
        borderRadius: 8,
        border: '1px solid var(--border)',
        fontSize: 12,
        textAlign: 'center',
        opacity: 0.7
      }}>
        No valid timestamps
      </div>
    )
  }

  const avgAge = ages.reduce((sum, age) => sum + age, 0) / ages.length
  const oldestAge = Math.max(...ages)
  const newestAge = Math.min(...ages)

  const staleCount = ages.filter(age => age > 168).length // >7 days
  const agingCount = ages.filter(age => age > 72 && age <= 168).length // 3-7 days
  const freshCount = ages.filter(age => age <= 72).length // <=3 days

  const freshnessScore = (freshCount / ages.length) * 100

  let overallStatus = 'fresh'
  let overallColor = 'var(--pos)'
  let overallIcon = '✓'

  if (freshnessScore < 50) {
    overallStatus = 'stale'
    overallColor = 'var(--neg)'
    overallIcon = '⚠️'
  } else if (freshnessScore < 75) {
    overallStatus = 'mixed'
    overallColor = 'orange'
    overallIcon = '⏱'
  }

  const formatHours = (hours) => {
    if (hours < 24) return `${Math.floor(hours)}h`
    const days = hours / 24
    if (days < 30) return `${Math.floor(days)}d`
    return `${Math.floor(days / 30)}mo`
  }

  return (
    <div style={{
      padding: 16,
      background: 'var(--bg-card)',
      border: `1px solid ${overallColor}`,
      borderRadius: 12
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <h3 style={{ margin: 0, fontSize: 14, fontWeight: 600 }}>
          {overallIcon} Data Freshness: {overallStatus.charAt(0).toUpperCase() + overallStatus.slice(1)}
        </h3>
        <div style={{
          fontSize: 20,
          fontWeight: 700,
          color: overallColor,
          fontFamily: 'var(--font-mono)'
        }}>
          {freshnessScore.toFixed(0)}%
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, fontSize: 12 }}>
        <div>
          <div style={{ opacity: 0.7, marginBottom: 4 }}>Fresh (≤3d)</div>
          <div style={{ fontSize: 16, fontWeight: 600, color: 'var(--pos)' }}>
            {freshCount}
          </div>
        </div>
        <div>
          <div style={{ opacity: 0.7, marginBottom: 4 }}>Aging (3-7d)</div>
          <div style={{ fontSize: 16, fontWeight: 600, color: 'orange' }}>
            {agingCount}
          </div>
        </div>
        <div>
          <div style={{ opacity: 0.7, marginBottom: 4 }}>Stale (>7d)</div>
          <div style={{ fontSize: 16, fontWeight: 600, color: 'var(--neg)' }}>
            {staleCount}
          </div>
        </div>
      </div>

      <div style={{
        marginTop: 12,
        paddingTop: 12,
        borderTop: '1px solid var(--border)',
        fontSize: 11,
        opacity: 0.7,
        fontFamily: 'var(--font-mono)'
      }}>
        Avg: {formatHours(avgAge)} • Oldest: {formatHours(oldestAge)} • Newest: {formatHours(newestAge)}
      </div>
    </div>
  )
}
