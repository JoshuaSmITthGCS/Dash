export default function SetupQualityBreakdown({ guidance, compact = false }) {
  if (!guidance) return null
  const tone = guidance.hardBlocked || guidance.setupLabel === 'Avoid'
    ? 'avoid'
    : guidance.setupLabel === 'Weak Setup' ? 'weak' : 'positive'
  return (
    <section className={`setup-quality ${tone}${compact ? ' compact' : ''}`} aria-label={`Setup quality ${guidance.setupScore} out of 100`}>
      <header>
        <div><span>Setup quality</span><strong>{guidance.setupLabel}</strong></div>
        <b>{guidance.setupScore}<small>/100</small></b>
      </header>
      <div className="setup-subscore-grid">
        {guidance.subscores.map((item) => (
          <div key={item.key}>
            <span>{item.label}</span><b>{Math.round(item.value * 100)}</b>
            <i aria-hidden="true"><em style={{ width: `${item.value * 100}%` }} /></i>
          </div>
        ))}
      </div>
      {guidance.hardBlocked && <p>{guidance.hardBlockReasons.join('. ')}.</p>}
    </section>
  )
}
