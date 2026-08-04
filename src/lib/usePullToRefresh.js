import { useEffect, useRef, useState } from 'react'

const TRIGGER_DISTANCE = 70
const MAX_PULL = 120

// Native rubber-banding is suppressed globally (body has overscroll-behavior-y: contain),
// so this reimplements the gesture: only arms when the page is scrolled to the very top,
// tracks a single touch, and applies resistance so the pull always feels bounded.
export function usePullToRefresh({ onRefresh, enabled = true, refreshing = false }) {
  const [pullDistance, setPullDistance] = useState(0)
  const [armed, setArmed] = useState(false)
  const startY = useRef(null)
  const tracking = useRef(false)

  useEffect(() => {
    if (!enabled) return undefined
    const coarsePointer = window.matchMedia?.('(pointer: coarse)').matches ?? true
    if (!coarsePointer) return undefined

    const onTouchStart = (event) => {
      if (refreshing || window.scrollY > 0 || event.touches.length !== 1) { tracking.current = false; return }
      startY.current = event.touches[0].clientY
      tracking.current = true
    }

    const onTouchMove = (event) => {
      if (!tracking.current || startY.current == null) return
      const delta = event.touches[0].clientY - startY.current
      if (delta <= 0 || window.scrollY > 0) { setPullDistance(0); setArmed(false); return }
      const resisted = Math.min(MAX_PULL, delta * 0.5)
      setPullDistance(resisted)
      setArmed(resisted >= TRIGGER_DISTANCE)
    }

    const onTouchEnd = () => {
      if (tracking.current && armed) onRefresh?.()
      tracking.current = false
      startY.current = null
      setPullDistance(0)
      setArmed(false)
    }

    window.addEventListener('touchstart', onTouchStart, { passive: true })
    window.addEventListener('touchmove', onTouchMove, { passive: true })
    window.addEventListener('touchend', onTouchEnd, { passive: true })
    window.addEventListener('touchcancel', onTouchEnd, { passive: true })
    return () => {
      window.removeEventListener('touchstart', onTouchStart)
      window.removeEventListener('touchmove', onTouchMove)
      window.removeEventListener('touchend', onTouchEnd)
      window.removeEventListener('touchcancel', onTouchEnd)
    }
  }, [enabled, refreshing, armed, onRefresh])

  return { pullDistance, armed, active: pullDistance > 0 || refreshing }
}
