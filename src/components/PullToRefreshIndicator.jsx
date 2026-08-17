import Icon from './Icons.jsx'

export default function PullToRefreshIndicator({ pullDistance, armed, refreshing, settling }) {
  if (!refreshing && pullDistance <= 0) return null
  const progress = refreshing ? 1 : Math.min(1, pullDistance / 70)
  return (
    <div
      className={`pull-to-refresh${settling ? ' pull-to-refresh--settling' : ''}`}
      style={{ '--ptr-progress': progress, '--ptr-distance': `${Math.min(pullDistance, 70)}px` }}
      aria-hidden="true"
    >
      <span className={`pull-to-refresh-badge${armed || refreshing ? ' armed' : ''}`}>
        <Icon name="sync" size={16} className={refreshing ? 'refresh-spin' : ''} />
      </span>
    </div>
  )
}
