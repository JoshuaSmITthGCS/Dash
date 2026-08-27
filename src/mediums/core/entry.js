/**
 * Entry-page mechanics: skippable, choice persisted, deep-link bypass is STRUCTURAL (never a
 * runtime check that could regress) — interception only ever evaluates on the bare destination
 * root with no query params, so any other path or any param can never hit it.
 *
 * Pure logic lives here so it's unit-testable without mounting a router; `useEntryDecision`
 * below is the thin React hook `MediumShell` calls.
 */
import { useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'

export function sessionSeenKey(mediumId) {
  return `valuesignal.entry-seen.${mediumId}`
}

/** True only on the exact destination root with no search params — the structural bypass. */
export function isEntryEligiblePath(pathname, search, rootPath) {
  return pathname === rootPath && (!search || search === '' || search === '?')
}

/** Pure decision function — easy to table-test every combination without a DOM. */
export function computeShowEntry({ hasEntry, pathname, search, rootPath, seen, entrySkip }) {
  if (!hasEntry) return false
  if (!isEntryEligiblePath(pathname, search, rootPath)) return false
  if (entrySkip) return false
  if (seen) return false
  return true
}

function readSeen(mediumId) {
  try { return globalThis.sessionStorage?.getItem(sessionSeenKey(mediumId)) === '1' } catch { return false }
}

function writeSeen(mediumId) {
  try { globalThis.sessionStorage?.setItem(sessionSeenKey(mediumId), '1') } catch { /* storage unavailable */ }
}

/**
 * `hasEntry` — whether the active manifest declares an entry component.
 * `rootPath` — the destination root this medium's entry can ever intercept (e.g. '/v2').
 * `entrySkip` — the user's persisted "don't show this again" preference for this medium.
 */
export function useEntryDecision({ mediumId, hasEntry, rootPath, entrySkip = false }) {
  const location = useLocation()
  const [seen, setSeen] = useState(() => readSeen(mediumId))

  // A medium switch resets the in-memory `seen` read for the new medium's own session key.
  useEffect(() => { setSeen(readSeen(mediumId)) }, [mediumId])

  const showEntry = computeShowEntry({
    hasEntry, pathname: location.pathname, search: location.search, rootPath, seen, entrySkip,
  })

  const dismiss = () => { writeSeen(mediumId); setSeen(true) }

  return { showEntry, dismiss }
}
