import { render, screen, fireEvent } from '@testing-library/react'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { useDialog } from './useDialog.js'

function Dialog({ open, onClose, withControls = true }) {
  const ref = useDialog(open, onClose)
  if (!open) return null
  return (
    <div ref={ref} role="dialog" aria-modal="true" aria-label="Test dialog" tabIndex="-1">
      {withControls && <>
        <button type="button">first</button>
        <button type="button">middle</button>
        <button type="button">last</button>
      </>}
    </div>
  )
}

function Harness({ withControls = true }) {
  const [open, setOpen] = useState(false)
  return <>
    <button type="button" onClick={() => setOpen(true)}>open</button>
    <Dialog open={open} onClose={() => setOpen(false)} withControls={withControls} />
  </>
}

describe('useDialog', () => {
  it('moves focus into the dialog when it opens', () => {
    render(<Harness />)
    fireEvent.click(screen.getByRole('button', { name: 'open' }))
    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'first' }))
  })

  it('focuses the panel itself when the dialog has no controls', () => {
    render(<Harness withControls={false} />)
    fireEvent.click(screen.getByRole('button', { name: 'open' }))
    expect(document.activeElement).toBe(screen.getByRole('dialog'))
  })

  it('closes on Escape', () => {
    const onClose = vi.fn()
    render(<Dialog open onClose={onClose} />)
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('wraps Tab from the last control back to the first', () => {
    render(<Dialog open onClose={() => {}} />)
    const last = screen.getByRole('button', { name: 'last' })
    last.focus()
    fireEvent.keyDown(document, { key: 'Tab' })
    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'first' }))
  })

  it('wraps Shift+Tab from the first control back to the last', () => {
    render(<Dialog open onClose={() => {}} />)
    screen.getByRole('button', { name: 'first' }).focus()
    fireEvent.keyDown(document, { key: 'Tab', shiftKey: true })
    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'last' }))
  })

  it('returns focus to whatever opened it', () => {
    render(<Harness />)
    const opener = screen.getByRole('button', { name: 'open' })
    opener.focus()
    fireEvent.click(opener)
    expect(document.activeElement).not.toBe(opener)
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(document.activeElement).toBe(opener)
  })
})
