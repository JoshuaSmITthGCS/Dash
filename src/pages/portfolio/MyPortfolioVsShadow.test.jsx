import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import MyPortfolioVsShadow from './MyPortfolioVsShadow.jsx'

const alignedWindow = { window_start: '2026-08-13', window_end: '2026-08-21' }
const strategies = [
  { strategy: 'A', observations: 4, aligned: { net_return: 1.5 } },
  { strategy: 'B', observations: 4, aligned: { net_return: -0.5 } },
  { strategy: 'C', observations: 0 },
]

describe('MyPortfolioVsShadow', () => {
  it('prompts sign-in when signed out', () => {
    render(<MyPortfolioVsShadow signedIn={false} hasPositions={false} myWindow={null} alignedWindow={alignedWindow} strategies={strategies} />)
    expect(screen.getByText(/Sign in and add your holdings/)).toBeInTheDocument()
  })

  it('prompts adding holdings when signed in with an empty portfolio', () => {
    render(<MyPortfolioVsShadow signedIn hasPositions={false} myWindow={null} alignedWindow={alignedWindow} strategies={strategies} />)
    expect(screen.getByText(/Add holdings to your portfolio/)).toBeInTheDocument()
  })

  it('shows the unavailable reason when the window cannot be computed yet', () => {
    render(<MyPortfolioVsShadow signedIn hasPositions myWindow={{ available: false, reason: 'test reason' }} alignedWindow={alignedWindow} strategies={strategies} />)
    expect(screen.getByText('test reason')).toBeInTheDocument()
  })

  it('reports the net return and rank among strategies with a matched aligned return', () => {
    render(<MyPortfolioVsShadow
      signedIn hasPositions
      myWindow={{ available: true, netReturnPct: 1.0, startDate: '2026-08-13', endDate: '2026-08-21', observations: 4 }}
      alignedWindow={alignedWindow}
      strategies={strategies}
    />)
    expect(screen.getByText(/\+1\.00%/)).toBeInTheDocument()
    // Beaten only by strategy A (1.5%), so #2 of 3 (2 strategies with a matched return + me).
    expect(screen.getByText(/#2 of 3/)).toBeInTheDocument()
    expect(screen.getAllByText(/2026-08-13/).length).toBeGreaterThan(0)
    expect(screen.getByText(/Same aligned window: 2026-08-13 → 2026-08-21/)).toBeInTheDocument()
  })

  it('formats a negative net return with a minus sign', () => {
    render(<MyPortfolioVsShadow
      signedIn hasPositions
      myWindow={{ available: true, netReturnPct: -2.25, startDate: '2026-08-13', endDate: '2026-08-21', observations: 4 }}
      alignedWindow={alignedWindow}
      strategies={[]}
    />)
    expect(screen.getByText(/−2\.25%/)).toBeInTheDocument()
  })
})
