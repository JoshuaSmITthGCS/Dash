import { render, screen, fireEvent } from '@testing-library/react'

import ErrorBoundary from './ErrorBoundary.jsx'

function Bomb({ shouldThrow }) {
  if (shouldThrow) throw new Error('boom')
  return <div>fine</div>
}

describe('ErrorBoundary', () => {
  const originalError = console.error
  beforeEach(() => { console.error = vi.fn() })
  afterEach(() => { console.error = originalError })

  it('renders children when nothing throws', () => {
    render(<ErrorBoundary><Bomb shouldThrow={false} /></ErrorBoundary>)
    expect(screen.getByText('fine')).toBeVisible()
  })

  it('catches a render error instead of unmounting the whole tree', () => {
    render(<ErrorBoundary pageName="Research"><Bomb shouldThrow /></ErrorBoundary>)
    expect(screen.getByRole('alert')).toHaveTextContent('Research didn’t finish loading')
    expect(screen.getByRole('alert')).toHaveTextContent('Your saved data is safe')
    expect(screen.queryByText('fine')).not.toBeInTheDocument()
  })

  it('lets the user retry once the underlying problem is gone', () => {
    const retry = vi.fn()
    const { rerender } = render(<ErrorBoundary onRetry={retry}><Bomb shouldThrow /></ErrorBoundary>)
    expect(screen.getByRole('alert')).toBeVisible()

    rerender(<ErrorBoundary onRetry={retry}><Bomb shouldThrow={false} /></ErrorBoundary>)
    fireEvent.click(screen.getByRole('button', { name: 'Reload page' }))

    expect(retry).toHaveBeenCalledOnce()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.getByText('fine')).toBeVisible()
  })

  it('explains how to recover when an app update invalidates a route chunk', () => {
    function ChunkBomb() { throw new Error('Failed to fetch dynamically imported module') }
    render(<ErrorBoundary pageName="Portfolio"><ChunkBomb /></ErrorBoundary>)
    expect(screen.getByRole('alert')).toHaveTextContent('Portfolio didn’t finish loading')
    expect(screen.getByRole('alert')).toHaveTextContent('app may have updated')
  })
})
