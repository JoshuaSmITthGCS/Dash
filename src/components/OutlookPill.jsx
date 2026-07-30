import { getOutlook } from '../lib/outlook'

export default function OutlookPill({ score }) {
  const outlook = getOutlook(score)
  if (!outlook) return <span className="mono" style={{ color: 'var(--text-faint)' }}>—</span>

  return (
    <span
      className={`outlook-pill ${outlook.key}`}
      title={`Research outlook based on a score of ${score} out of 100`}
    >
      {outlook.label}
    </span>
  )
}

