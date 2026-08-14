import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { OPTIONS_NAV, OptionsNavigation, SCREEN_NAV, ScreenNavigation } from './ResearchScreen.jsx'
import { STRATEGY_SCREENS } from '../lib/strategyScreenConfigs.js'
import { MOBILE_NAV } from '../App.jsx'

const at = (path, ui) => render(<MemoryRouter initialEntries={[path]}>{ui}</MemoryRouter>)

describe('screen navigation contract', () => {
  it('leads the screens rail with swing signals and gives Markets its own destination', () => {
    expect(SCREEN_NAV[0]).toEqual(['/screens/swing', 'Swing signals'])
    expect(MOBILE_NAV.find((item) => item.label === 'Markets').to).toBe('/markets')
  })

  it('marks the swing screen active when it is open', () => {
    at('/screens/swing', <ScreenNavigation />)

    expect(screen.getByRole('link', { name: 'Swing signals' })).toHaveClass('active')
  })

  it('exposes options as a single top-level tab, not one tab per strategy', () => {
    const optionsTabs = SCREEN_NAV.filter(([to]) => to.startsWith('/screens/options'))
    expect(optionsTabs).toEqual([['/screens/options', 'Options']])
    for (const id of Object.keys(STRATEGY_SCREENS)) {
      expect(SCREEN_NAV.some(([to]) => to === `/screens/${id}`)).toBe(false)
    }
  })

  it('keeps every strategy screen reachable from the options sub-nav', () => {
    const covered = OPTIONS_NAV.map((item) => item.strategyId).filter(Boolean)
    expect(covered.sort()).toEqual(Object.keys(STRATEGY_SCREENS).sort())
    expect(OPTIONS_NAV[0]).toMatchObject({ to: '/screens/options', end: true })
    for (const item of OPTIONS_NAV.slice(1)) {
      expect(item.to).toBe(`/screens/options/${item.strategyId}`)
    }
  })

  it('holds the options tab active while a strategy sub-tab is open', () => {
    at('/screens/options/collar', <ScreenNavigation />)

    expect(screen.getByRole('link', { name: 'Options' })).toHaveClass('active')
  })

  it('marks the open strategy — and only it — active in the sub-nav', () => {
    at('/screens/options/collar', <OptionsNavigation />)

    const active = screen.getAllByRole('link').filter((link) => link.classList.contains('active'))
    expect(active.map((link) => link.textContent)).toEqual(['Collar'])
  })

  it('does not leave the multi-day sub-tab active on a strategy route', () => {
    at('/screens/options/covered-call', <OptionsNavigation />)

    expect(screen.getByRole('link', { name: 'Multi-day' })).not.toHaveClass('active')
  })
})
