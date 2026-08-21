// Your own real investing, read over the exact same calendar window the shadow strategies
// are compared over (aligned_window) -- a separate, client-side-only overlay on the shadow
// portfolio page. It never writes into screens/shadow-portfolios.json: that file is an
// immutable, controlled experiment registry (Round 7, promotion gating, config_hash), and
// personal Firebase-sourced holdings have no place inside it. This is informational only.

const signedReturn = (value) => `${Number(value) >= 0 ? '+' : '−'}${Math.abs(Number(value)).toFixed(2)}%`

function rankAmong(strategies, myReturnPct) {
  const ranked = strategies
    .filter((row) => row.observations > 0 && Number.isFinite(Number(row.aligned?.net_return)))
    .map((row) => Number(row.aligned.net_return))
  if (!ranked.length) return null
  const beatenBy = ranked.filter((value) => value > myReturnPct).length
  return { rank: beatenBy + 1, of: ranked.length + 1 }
}

export default function MyPortfolioVsShadow({ signedIn, hasPositions, myWindow, alignedWindow, strategies }) {
  const windowLabel = alignedWindow?.window_start && alignedWindow?.window_end
    ? `${alignedWindow.window_start} → ${alignedWindow.window_end}`
    : null

  let body
  if (!signedIn) {
    body = <p>Sign in and add your holdings to compare your own investing against these strategies over this same window.</p>
  } else if (!hasPositions) {
    body = <p>Add holdings to your portfolio to compare your own investing against these strategies over this same window.</p>
  } else if (!myWindow?.available) {
    body = <p>{myWindow?.reason || 'Your portfolio does not yet have enough price history to compare over this window.'}</p>
  } else {
    const rank = rankAmong(strategies, myWindow.netReturnPct)
    body = (
      <>
        <p className="my-portfolio-vs-shadow-headline">
          Your portfolio: <strong>{signedReturn(myWindow.netReturnPct)}</strong> from {myWindow.startDate} to {myWindow.endDate}
          {rank ? <> — would rank <strong>#{rank.rank} of {rank.of}</strong> on this measure.</> : null}
        </p>
        <p className="disclaimer">
          Computed by applying your current holdings backward against published daily closes (a
          historical replay of today&rsquo;s positions, not your actual recorded account value or
          transaction costs) and reading the net change over the same window every strategy above
          is compared on. Informational only: this never writes into the shadow strategy registry
          above and plays no part in any promotion decision.
        </p>
      </>
    )
  }

  return (
    <section className="card my-portfolio-vs-shadow" aria-label="Your portfolio versus shadow strategies">
      <div className="portfolio-section-heading">
        <div><span className="eyebrow">Your investing</span><h3>Your portfolio vs. these strategies</h3></div>
      </div>
      {windowLabel && <p className="my-portfolio-vs-shadow-window">Same aligned window: {windowLabel}</p>}
      {body}
    </section>
  )
}
