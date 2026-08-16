import { useEffect, useState } from 'react'

/**
 * The rendered CSS width of an element, tracked through resizes.
 *
 * Exists for the hand-rolled SVG charts. An `<svg viewBox="0 0 920 360" width="100%">`
 * dropped into a 743px container scales everything inside it by 743/920 = 0.81 — so a
 * label written as `fontSize="11"` paints at 8.9px, and `getComputedStyle` still reports
 * 11 because that is the specified size in user units. `DESIGN.md` sets an 11px floor
 * that includes SVG labels, and no amount of editing the attribute can satisfy it while
 * the viewBox is a different width from the box it is drawn into.
 *
 * Feeding this width back in as the viewBox width makes the scale exactly 1, so every
 * px inside the chart — label sizes, paddings, tooltip boxes — means what it says.
 *
 * Returns `fallback` until the first measurement, and forever in environments without
 * ResizeObserver (jsdom), so charts still render server-side and under test.
 */
export function useElementWidth(ref, fallback = null) {
  const [width, setWidth] = useState(null)

  useEffect(() => {
    const element = ref.current
    if (!element) return undefined
    const apply = (measured) => {
      // A collapsed or display:none container measures 0; keep the last good width
      // rather than collapsing the chart's coordinate space to nothing.
      if (measured > 0) setWidth(Math.round(measured))
    }
    // Measure once directly. Inside a closed <details> the browser still lays out a box
    // but skips ResizeObserver callbacks for skipped content, so a chart in a collapsed
    // section would otherwise keep its seed width and be drawn at the wrong scale for the
    // first frame after the user opens it. Subtract padding and border so this agrees with
    // the content-box width ResizeObserver reports, rather than overshooting by one frame.
    const style = window.getComputedStyle?.(element)
    const inset = style
      ? ['paddingLeft', 'paddingRight', 'borderLeftWidth', 'borderRightWidth']
        .reduce((total, key) => total + (parseFloat(style[key]) || 0), 0)
      : 0
    apply(element.getBoundingClientRect().width - inset)
    if (typeof ResizeObserver === 'undefined') return undefined
    const observer = new ResizeObserver((entries) => apply(entries[0]?.contentRect?.width ?? 0))
    observer.observe(element)
    return () => observer.disconnect()
  }, [ref])

  return width ?? fallback
}

export default useElementWidth
