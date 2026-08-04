import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, renderHook, waitFor } from '@testing-library/react'
import { clearCachedData, formatElapsed, useData } from './useData'

describe('useData local caching', () => {
  const file = 'test-fixture.json'

  beforeEach(() => {
    localStorage.clear()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  it('caches a successful fetch and serves it instantly on the next mount', async () => {
    const payload = { generated_at: '2026-08-01T00:00:00Z', research: [] }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(payload),
    }))

    const first = renderHook(() => useData(file))
    await waitFor(() => expect(first.result.current.loading).toBe(false))
    expect(first.result.current.data).toEqual(payload)
    expect(first.result.current.fromCache).toBe(false)

    // A second mount (e.g. a page reload) should paint from the cached copy immediately,
    // with no loading spinner, even though the network call hasn't resolved yet.
    const second = renderHook(() => useData(file))
    expect(second.result.current.loading).toBe(false)
    expect(second.result.current.fromCache).toBe(true)
    expect(second.result.current.data).toEqual(payload)
  })

  it('falls back to the cached payload when a revalidation fetch fails', async () => {
    const payload = { generated_at: '2026-08-01T00:00:00Z', research: [] }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(payload),
    }))
    const first = renderHook(() => useData(file))
    await waitFor(() => expect(first.result.current.loading).toBe(false))

    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')))
    const second = renderHook(() => useData(file))
    await waitFor(() => expect(second.result.current.error).toBeTruthy())
    expect(second.result.current.data).toEqual(payload)
  })

  it('clearCachedData removes a single cached file without touching others', async () => {
    const payload = { generated_at: '2026-08-01T00:00:00Z', research: [] }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(payload),
    }))
    const other = 'other-fixture.json'
    await act(async () => {
      renderHook(() => useData(file))
      renderHook(() => useData(other))
    })
    await waitFor(() => expect(localStorage.getItem('dash:last-refresh:' + file)).toBeTruthy())

    clearCachedData(file)
    expect(localStorage.getItem('dash:last-refresh:' + file)).toBeNull()
    expect(localStorage.getItem('dash:last-refresh:' + other)).toBeTruthy()
  })

  it('ignores a stale response after the requested file changes', async () => {
    let resolveFirst
    const firstResponse = new Promise((resolve) => { resolveFirst = resolve })
    vi.stubGlobal('fetch', vi.fn((url) => url.includes('first.json')
      ? firstResponse
      : Promise.resolve({ ok: true, json: () => Promise.resolve({ id: 'second' }) })))
    const hook = renderHook(({ file: requested }) => useData(requested), { initialProps: { file: 'first.json' } })
    hook.rerender({ file: 'second.json' })
    await waitFor(() => expect(hook.result.current.data).toEqual({ id: 'second' }))
    resolveFirst({ ok: true, json: () => Promise.resolve({ id: 'first' }) })
    await act(async () => { await Promise.resolve(); await Promise.resolve() })
    expect(hook.result.current.data).toEqual({ id: 'second' })
  })
})

describe('formatElapsed', () => {
  it('shows seconds only under a minute', () => {
    expect(formatElapsed(45_000)).toBe('45s')
  })

  it('shows minutes and seconds past a minute', () => {
    expect(formatElapsed(102_000)).toBe('1m 42s')
  })

  it('never goes negative on a clock skew', () => {
    expect(formatElapsed(-500)).toBe('0s')
  })

  it('rounds down mid-second', () => {
    expect(formatElapsed(59_900)).toBe('59s')
  })
})
