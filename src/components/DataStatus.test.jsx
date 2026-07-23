import { render, screen } from '@testing-library/react'

import { DataStatus, freshness } from './DataStatus.jsx'
import { useData } from '../lib/useData'

vi.mock('../lib/useData', async () => {
  const actual = await vi.importActual('../lib/useData')
  return { ...actual, useData: vi.fn() }
})

describe('DataStatus', () => {
  it('makes demo fixtures unmistakable', () => {
    useData.mockImplementation((file) => file === 'advisor.json'
      ? { data: { data_mode: 'demo', generated_at: new Date().toISOString() } }
      : { data: { status: 'degraded', stages: {} } })
    render(<DataStatus />)
    expect(screen.getByText('Demo data')).toBeVisible()
    expect(screen.getByText(/Do not use them/)).toBeVisible()
  })

  it('shows source-level failures', () => {
    useData.mockImplementation((file) => file === 'advisor.json'
      ? { data: { data_mode: 'live', generated_at: new Date().toISOString() } }
      : { data: { status: 'error', stages: { advisor: { status: 'error', message: 'provider failure' } } } })
    render(<DataStatus />)
    expect(screen.getByText('Data needs attention')).toBeVisible()
    expect(screen.getByText('Advisor engine')).toHaveAttribute('title', 'provider failure')
  })
})

describe('freshness', () => {
  it('marks data stale at 36 hours', () => {
    const now = Date.parse('2026-07-22T12:00:00Z')
    expect(freshness('2026-07-21T01:00:00Z', now).stale).toBe(false)
    expect(freshness('2026-07-21T00:00:00Z', now).stale).toBe(true)
  })
})
