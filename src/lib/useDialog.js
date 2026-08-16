import { useCallback, useEffect, useRef } from 'react'

const FOCUSABLE = [
  'a[href]', 'button:not([disabled])', 'input:not([disabled])', 'select:not([disabled])',
  'textarea:not([disabled])', 'summary', '[tabindex]:not([tabindex="-1"])',
].join(',')

/**
 * Modal dialog behaviour, in one place.
 *
 * A modal owes the reader four things, and all four have to be present or the
 * dialog is broken for anyone not using a mouse:
 *
 *   1. focus moves into the dialog when it opens,
 *   2. Tab and Shift+Tab stay inside it while it is open,
 *   3. Escape closes it,
 *   4. focus returns to whatever opened it.
 *
 * Returns a ref to put on the dialog panel. The caller still supplies the
 * `role="dialog"`, `aria-modal="true"` and `aria-labelledby` attributes, because
 * those belong on the element the caller renders.
 */
export function useDialog(open, onClose) {
  const panelRef = useRef(null)

  const visibleFocusable = useCallback(() => {
    const panel = panelRef.current
    if (!panel) return []
    return [...panel.querySelectorAll(FOCUSABLE)].filter((node) => {
      if (node.hasAttribute('hidden') || node.getAttribute('aria-hidden') === 'true') return false
      // A control inside a collapsed <details> is not rendered, so it must not be
      // a stop in the trap. Checked structurally rather than through offsetParent
      // or getClientRects, which report nothing under a headless test renderer.
      const details = node.closest('details')
      if (details && !details.open && node.tagName !== 'SUMMARY') return false
      return !node.closest('[hidden],[aria-hidden="true"]')
    })
  }, [])

  useEffect(() => {
    if (!open) return undefined
    const panel = panelRef.current
    const previous = document.activeElement

    // Prefer the first real control; fall back to the panel itself so the reader
    // lands inside the dialog rather than at the top of the page behind it.
    const first = visibleFocusable()[0]
    if (first) first.focus()
    else panel?.focus()

    const onKeyDown = (event) => {
      if (event.key === 'Escape') { event.stopPropagation(); onClose(); return }
      if (event.key !== 'Tab') return
      const nodes = visibleFocusable()
      if (!nodes.length) { event.preventDefault(); panel?.focus(); return }
      const firstNode = nodes[0]
      const lastNode = nodes[nodes.length - 1]
      const active = document.activeElement
      if (event.shiftKey && (active === firstNode || !panel?.contains(active))) {
        event.preventDefault(); lastNode.focus()
      } else if (!event.shiftKey && active === lastNode) {
        event.preventDefault(); firstNode.focus()
      }
    }

    document.addEventListener('keydown', onKeyDown, true)
    return () => {
      document.removeEventListener('keydown', onKeyDown, true)
      // The opener can be gone by now (a row that re-rendered), so this is optional.
      if (previous && document.contains(previous)) previous.focus?.()
    }
  }, [open, onClose, visibleFocusable])

  return panelRef
}

export default useDialog
