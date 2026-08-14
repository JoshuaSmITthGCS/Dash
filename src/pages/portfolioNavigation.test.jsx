import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { PORTFOLIO_NAV, PortfolioNavigation } from './Portfolio.jsx'

const at = (path) => render(
  <MemoryRouter initialEntries={[path]}>
    <PortfolioNavigation />
  </MemoryRouter>,
)

describe('portfolio navigation contract', () => {
  it('provides separate summary, performance, and data overview routes', () => {
    expect(PORTFOLIO_NAV).toEqual([
      { to: '/portfolio', label: 'Summary', end: true },
      { to: '/portfolio/performance', label: 'Performance' },
      { to: '/portfolio/data-overview', label: 'Data overview' },
    ])
  })

  it('marks only the exact portfolio page active', () => {
    at('/portfolio/performance')

    const active = screen.getAllByRole('link').filter((link) => link.classList.contains('active'))
    expect(active.map((link) => link.textContent)).toEqual(['Performance'])
    expect(screen.getByRole('link', { name: 'Summary' })).not.toHaveClass('active')
  })
})
