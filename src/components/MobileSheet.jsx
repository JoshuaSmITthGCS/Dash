import { useId, useState } from 'react'
import { useDialog } from '../lib/useDialog.js'
import Icon from './Icons.jsx'

export function MobileSheet({ open, title, onClose, children, className = '' }) {
  const titleId = useId()
  // Shares its dialog behaviour with StockDetailModal. This sheet already had
  // Escape and focus restore; the hook adds the focus trap it was missing.
  const panelRef = useDialog(open, onClose)
  if (!open) return null
  return <div className={`mobile-sheet-layer ${className}`} role="presentation" onPointerDown={(event) => { if (event.target === event.currentTarget) onClose() }}>
    <section ref={panelRef} className="mobile-sheet" role="dialog" aria-modal="true" aria-labelledby={titleId} tabIndex="-1">
      <div className="mobile-sheet-handle" aria-hidden="true" />
      <header><h2 id={titleId}>{title}</h2><button type="button" className="icon-button" aria-label={`Close ${title}`} onClick={onClose}><Icon name="close" /></button></header>
      <div className="mobile-sheet-body">{children}</div>
    </section>
  </div>
}

export function ResponsiveControlPanel({ label, title, children }) {
  const [open, setOpen] = useState(false)
  return <>
    <div className="desktop-control-panel">{children}</div>
    <button type="button" className="secondary-button mobile-sheet-trigger" onClick={() => setOpen(true)}><span>{label}</span><Icon name="chevron" size={17} /></button>
    <MobileSheet open={open} title={title} onClose={() => setOpen(false)}>{children}<button type="button" className="primary-button mobile-sheet-done" onClick={() => setOpen(false)}>Done</button></MobileSheet>
  </>
}
