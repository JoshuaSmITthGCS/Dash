import { useState } from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { MobileSheet } from './MobileSheet.jsx'

// A sheet whose onClose identity changes on every render, which is what every real caller
// does (`onClose={cancelSell}`, rebuilt by the form hook on each keystroke).
function SellLikeSheet() {
  const [shares, setShares] = useState('')
  const [price, setPrice] = useState('')
  const [open, setOpen] = useState(false)
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>Sell</button>
      {open && (
        <MobileSheet open title="Sell AAA" onClose={() => setOpen(false)}>
          <input aria-label="Shares" value={shares} onChange={(event) => setShares(event.target.value)} />
          <input aria-label="Price" value={price} onChange={(event) => setPrice(event.target.value)} />
        </MobileSheet>
      )}
    </>
  )
}

describe('MobileSheet focus behaviour', () => {
  it('keeps focus in the field being typed into across re-renders', () => {
    render(<SellLikeSheet />)
    fireEvent.click(screen.getByText('Sell'))
    const price = screen.getByLabelText('Price')
    price.focus()
    fireEvent.change(price, { target: { value: '1' } })
    expect(document.activeElement).toBe(price)
    fireEvent.change(price, { target: { value: '12' } })
    fireEvent.change(price, { target: { value: '12.5' } })
    expect(document.activeElement).toBe(price)
    expect(price.value).toBe('12.5')
  })

  it('still moves focus into the sheet when it opens, and closes on Escape', () => {
    render(<SellLikeSheet />)
    fireEvent.click(screen.getByText('Sell'))
    // The header's close button is the first control in the panel.
    expect(screen.getByRole('dialog').contains(document.activeElement)).toBe(true)
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(screen.queryByRole('dialog')).toBeNull()
  })
})
