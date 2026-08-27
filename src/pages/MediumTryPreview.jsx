import { useEffect, useState } from 'react'
import { loadMedium } from '../mediums/registry.js'
import { MediumProvider } from '../mediums/core/MediumContext.jsx'
import WallLabel from '../mediums/core/WallLabel.jsx'

/**
 * A genuinely live thumbnail for Settings' "Try a new look" picker (CAPABILITY-LEDGER.md's
 * `control.settings.theme-choice` end-state) — it loads the real medium and renders its real
 * `LabelFrame`/`Container` against one fixed fixture metric, so the swatch is that medium's
 * actual typography and color identity (Gallery's serif display face, Chalkboard's hand-lettered
 * slate box, Newspaper's column rule, Beige Box's title bar, Ticker's flat wire row) rather than
 * a flat color chip. Not the breached fixture — that would paint every preview the same alarm
 * red and hide the medium's own palette; the established, non-alarming reading shows it best.
 */
const PREVIEW_METRIC = Object.freeze({
  id: 'settings_preview_metric', label: 'Deflated Sharpe', status: 'ready', breached: false,
  reads: 'Adjusts the raw ratio for the number of configurations tried.',
  unit: 'ratio', cadence: 'Weekly', value: 0.62, display: '0.62',
})

// Raw text of each medium's tokens.css, loaded on demand only — `?raw` returns the file's
// source instead of letting Vite inject it as a live global stylesheet (which is what
// `manifest.loadTokens()` does, and is NOT what we want here: see scopeTokensForPreview below).
// Never bundled into Settings' own chunk; each entry only fetches once its medium is requested.
const tokenSourceLoaders = import.meta.glob('../mediums/*/tokens.css', { query: '?raw', import: 'default' })

/**
 * Every shipped medium's tokens.css defines its custom properties on `:root[data-medium="<id>"]`
 * and folds its page-level background/ink/font onto `[data-medium="<id>"] body`. `:root` only
 * ever matches the document's actual root element, so setting `data-medium` on a plain nested
 * wrapper div — the obvious way to scope five different mediums into one page at once, since
 * `document.documentElement` can only hold one medium's value at a time — would silently resolve
 * every `var(--ink-primary)`-style reference in that subtree to nothing.
 *
 * Verified directly against gallery, ticker, chalkboard, newspaper, and beige-box's tokens.css:
 * every rule in all five is exactly one of three shapes — `:root[data-medium=".."] { ... }`
 * (the token block), `[data-medium=".."] body { ... }` (page background/ink/font — there's no
 * literal `<body>` descendant inside a thumbnail for this to land on), or a plain
 * `[data-medium=".."] [data-foo] { ... }` / `[data-medium=".."] { ... }` component rule. This
 * rewrites all three to a single plain attribute selector, `[data-preview-medium="<id>"]`, that
 * DOES match a nested element — so each preview's own wrapper div, carrying that attribute
 * locally, gets its own independent set of custom properties and rules, and five of them can be
 * mounted on the page simultaneously without colliding.
 */
export function scopeTokensForPreview(css, mediumId) {
  const globalAttr = `[data-medium="${mediumId}"]`
  const localAttr = `[data-preview-medium="${mediumId}"]`
  return css
    .replaceAll(`${globalAttr} body`, localAttr)
    .replaceAll(`:root${globalAttr}`, localAttr)
    .replaceAll(globalAttr, localAttr)
}

const THUMB_HEIGHT = '104px'

export default function MediumTryPreview({ mediumId }) {
  // null = loading, 'error' = failed, otherwise { manifest, css }
  const [state, setState] = useState(null)

  useEffect(() => {
    let cancelled = false
    setState(null)
    const loadCss = tokenSourceLoaders[`../mediums/${mediumId}/tokens.css`]
    Promise.all([loadMedium(mediumId), loadCss ? loadCss() : Promise.resolve('')])
      .then(([manifest, css]) => {
        if (cancelled) return
        setState({ manifest, css: scopeTokensForPreview(css, mediumId) })
      })
      .catch(() => { if (!cancelled) setState('error') })
    return () => { cancelled = true }
  }, [mediumId])

  const frameStyle = {
    height: THUMB_HEIGHT, minHeight: 0, overflow: 'hidden', borderRadius: '6px',
    border: '1px solid rgba(127, 127, 127, 0.28)', position: 'relative',
  }

  if (!state || state === 'error') {
    return (
      <span aria-hidden="true" style={{ ...frameStyle, display: 'grid', placeItems: 'center', fontSize: '11px', opacity: 0.55 }}>
        {state === 'error' ? 'Preview unavailable' : ''}
      </span>
    )
  }

  const { manifest, css } = state
  const Container = manifest.components?.Container
  const label = <WallLabel metric={PREVIEW_METRIC} capabilityId={`settings.medium-preview.${mediumId}`} />

  return (
    // Decorative only — the enclosing <Choice> button already carries the medium's name as its
    // accessible text, so this whole live-rendered thumbnail is hidden from assistive tech
    // rather than read as a second, confusing copy of the same metric.
    <div aria-hidden="true" data-preview-medium={mediumId} style={{ ...frameStyle, pointerEvents: 'none' }}>
      <style>{css}</style>
      <MediumProvider value={manifest}>
        {Container ? <Container state={{ state: 'established' }} primary>{label}</Container> : label}
      </MediumProvider>
    </div>
  )
}
