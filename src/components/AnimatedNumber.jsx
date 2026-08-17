import { useEffect, useRef, useState } from 'react'

// Animates a numeric value counting up or down to its new target whenever `value` changes,
// instead of the figure jumping straight to the refreshed number. Interpolates the raw
// number through requestAnimationFrame and hands each intermediate value to `format`, so a
// money/percent formatter can be reused as-is.
export default function AnimatedNumber({ value, format = String, duration = 700 }) {
  const [display, setDisplay] = useState(value)
  const fromRef = useRef(value)
  const frameRef = useRef(null)

  useEffect(() => {
    if (!Number.isFinite(value)) {
      setDisplay(value)
      fromRef.current = value
      return undefined
    }
    const from = Number.isFinite(fromRef.current) ? fromRef.current : value
    const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    if (from === value || reduceMotion) {
      setDisplay(value)
      fromRef.current = value
      return undefined
    }
    const start = window.performance.now()
    const tick = (now) => {
      const progress = Math.min(1, (now - start) / duration)
      const eased = 1 - (1 - progress) ** 3
      const next = from + (value - from) * eased
      setDisplay(next)
      if (progress < 1) {
        frameRef.current = window.requestAnimationFrame(tick)
      } else {
        fromRef.current = value
      }
    }
    frameRef.current = window.requestAnimationFrame(tick)
    return () => window.cancelAnimationFrame(frameRef.current)
  }, [value, duration])

  return format(display)
}
