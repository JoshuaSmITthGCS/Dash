import { describe, expect, it, vi } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { useRenderer } from './useRenderer.js'
import { MediumProvider } from './MediumContext.jsx'

function wrapperFor(manifest) {
  return function Wrapper({ children }) {
    return <MediumProvider value={manifest}>{children}</MediumProvider>
  }
}

describe('useRenderer', () => {
  it('returns null until manifest.loadRenderer() resolves', async () => {
    let resolveRenderer
    const fakeRenderer = { line: () => null }
    const manifest = { loadRenderer: () => new Promise((resolve) => { resolveRenderer = resolve }) }

    const { result } = renderHook(() => useRenderer(), { wrapper: wrapperFor(manifest) })
    expect(result.current).toBeNull()

    resolveRenderer(fakeRenderer)
    await waitFor(() => expect(result.current).toBe(fakeRenderer))
  })

  it('calls loadRenderer only once for a stable manifest, even across re-renders', async () => {
    const fakeRenderer = { line: () => null }
    const loadRenderer = vi.fn().mockResolvedValue(fakeRenderer)
    const manifest = { loadRenderer }

    const { result, rerender } = renderHook(() => useRenderer(), { wrapper: wrapperFor(manifest) })
    await waitFor(() => expect(result.current).toBe(fakeRenderer))

    rerender()
    rerender()

    expect(loadRenderer).toHaveBeenCalledTimes(1)
  })

  it('ignores a stale resolution after the medium changes mid-flight (the cancelled-flag guard)', async () => {
    const rendererA = { line: () => 'a' }
    const rendererB = { line: () => 'b' }
    let resolveA
    const manifestA = { loadRenderer: () => new Promise((resolve) => { resolveA = resolve }) }
    const manifestB = { loadRenderer: vi.fn().mockResolvedValue(rendererB) }

    // The wrapper reads from a mutable box rather than a prop, since renderHook's `rerender`
    // only re-invokes the hook callback — it doesn't pass new props to `wrapper`. Mutating the
    // box before calling rerender() is what makes the *next* render mount under manifestB.
    const active = { manifest: manifestA }
    function Wrapper({ children }) {
      return <MediumProvider value={active.manifest}>{children}</MediumProvider>
    }

    const { result, rerender } = renderHook(() => useRenderer(), { wrapper: Wrapper })
    expect(result.current).toBeNull()

    active.manifest = manifestB
    rerender()
    await waitFor(() => expect(result.current).toBe(rendererB))

    // manifestA's load resolves late, after the medium already changed. Its result must never
    // land — the effect cleanup for manifestA's run set `cancelled = true` when the medium
    // changed, exactly like E2EHarness.jsx's own guard.
    resolveA(rendererA)
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(result.current).toBe(rendererB)
  })

  it('swallows a loadRenderer rejection and stays null rather than throwing', async () => {
    const manifest = { loadRenderer: () => Promise.reject(new Error('renderer.js failed to build')) }

    const { result } = renderHook(() => useRenderer(), { wrapper: wrapperFor(manifest) })
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(result.current).toBeNull()
  })
})
