import { useEffect, useState } from 'react'

/**
 * Subscribe to a CSS media query from JavaScript.
 *
 * Charts are hand-rolled SVG with fixed viewBoxes, so a few of them need to know
 * the breakpoint in JS to pick a geometry rather than relying on CSS alone. This
 * is that hook, and it is the only copy — it previously existed twice, verbatim,
 * in GrowthChart and MarketHeatmap.
 *
 * Guards `window`/`matchMedia` so the hook is inert under SSR and in the jsdom
 * environments that do not stub matchMedia.
 */
export function useMediaQuery(query) {
  const getMatches = () => typeof window !== 'undefined'
    && typeof window.matchMedia === 'function'
    && window.matchMedia(query).matches
  const [matches, setMatches] = useState(getMatches)

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return undefined
    const media = window.matchMedia(query)
    const update = () => setMatches(media.matches)
    update()
    media.addEventListener?.('change', update)
    return () => media.removeEventListener?.('change', update)
  }, [query])

  return matches
}

export default useMediaQuery
