import { createContext, useContext } from 'react'

/**
 * Holds the active medium's loaded manifest (tokens applied, renderer resolved, components
 * ready) once `MediumShell` has finished loading it. Every `core/screens/*` component and
 * `WallLabel` read from this instead of importing a medium directly — the whole point of the
 * manifest system is that `core/` never knows which of the twelve is mounted.
 */
const MediumContext = createContext(null)

export const MediumProvider = MediumContext.Provider

export function useMedium() {
  const manifest = useContext(MediumContext)
  if (!manifest) throw new Error('useMedium must be used within a MediumProvider (inside MediumShell)')
  return manifest
}

/** Non-throwing variant for call sites that can legitimately render before a medium is ready. */
export function useMediumOptional() {
  return useContext(MediumContext)
}
