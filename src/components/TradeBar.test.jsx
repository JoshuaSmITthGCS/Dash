import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import TradeBar from './TradeBar.jsx'

const held = { shares: 3, price: 140 }

describe('TradeBar', () => {
  it('opens on Sell for a held position and submits the typed trade', async () => {
    const onSubmit = vi.fn().mockResolvedValue({ success: true, message: 'Sold.' })
    render(<TradeBar ticker="LULU" currentPrice={140} position={held} onSubmit={onSubmit} />)

    fireEvent.click(screen.getByRole('button', { name: /Sell LULU/ }))
    fireEvent.change(screen.getByLabelText(/Shares/), { target: { value: '3' } })
    fireEvent.change(screen.getByLabelText(/Sale date/), { target: { value: '2026-09-02' } })
    fireEvent.click(screen.getByRole('button', { name: /Confirm sale/ }))

    await waitFor(() => expect(onSubmit).toHaveBeenCalledWith({
      side: 'sell', ticker: 'LULU', shares: '3', price: '140', date: '2026-09-02',
    }))
  })

  it('keeps focus in the field while a number is typed', () => {
    render(<TradeBar ticker="LULU" currentPrice={140} position={held} onSubmit={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: /Sell LULU/ }))
    const shares = screen.getByLabelText(/Shares/)
    shares.focus()
    fireEvent.change(shares, { target: { value: '1' } })
    fireEvent.change(shares, { target: { value: '1.2' } })
    expect(document.activeElement).toBe(shares)
    expect(shares.value).toBe('1.2')
  })

  it('blocks a sale larger than the position instead of sending it', () => {
    const onSubmit = vi.fn()
    render(<TradeBar ticker="LULU" currentPrice={140} position={held} onSubmit={onSubmit} />)
    fireEvent.click(screen.getByRole('button', { name: /Sell LULU/ }))
    fireEvent.change(screen.getByLabelText(/Shares/), { target: { value: '9' } })
    expect(screen.getByRole('button', { name: /Confirm sale/ })).toBeDisabled()
    expect(screen.getByText('You hold 3 LULU shares.')).toBeTruthy()
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('offers only Buy when nothing is held, and says so when the ticker was sold', () => {
    render(<TradeBar ticker="LULU" currentPrice={140} position={null} onSubmit={vi.fn()} closed onReopen={vi.fn()} />)
    expect(screen.queryByRole('button', { name: /Sell LULU/ })).toBeNull()
    expect(screen.getByRole('button', { name: /Buy LULU/ })).toBeTruthy()
    expect(screen.getByText(/You sold out of LULU/)).toBeTruthy()
  })

  it('fills the price from the live quote but never over a price the user typed', () => {
    const { rerender } = render(<TradeBar ticker="LULU" currentPrice={140} position={held} onSubmit={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: /Sell LULU/ }))
    expect(screen.getByLabelText(/Price/).value).toBe('140')
    fireEvent.change(screen.getByLabelText(/Price/), { target: { value: '131.40' } })
    rerender(<TradeBar ticker="LULU" currentPrice={142.5} position={held} onSubmit={vi.fn()} />)
    expect(screen.getByLabelText(/Price/).value).toBe('131.40')
  })

  it('surfaces a failed write instead of reporting success', async () => {
    const onSubmit = vi.fn().mockResolvedValue({ success: false, error: 'offline' })
    render(<TradeBar ticker="LULU" currentPrice={140} position={held} onSubmit={onSubmit} />)
    fireEvent.click(screen.getByRole('button', { name: /Sell LULU/ }))
    fireEvent.change(screen.getByLabelText(/Shares/), { target: { value: '1' } })
    fireEvent.click(screen.getByRole('button', { name: /Confirm sale/ }))
    expect(await screen.findByText('offline')).toBeTruthy()
  })
})
