import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, renderHook, waitFor } from '@testing-library/react'
import { clearCachedData, formatElapsed, useData } from './useData'

describe('useData local caching', () => {
  const file = 'test-fixture.json'

  beforeEach(() => {
    localStorage.clear()
    clearCachedData()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.clear()
    clearCachedData()
  })

  it('caches a successful fetch, but a later mount still shows loading until the fetch resolves', async () => {
    const payload = { generated_at: '2026-08-01T00:00:00Z', research: [] }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(payload),
    }))

    const first = renderHook(() => useData(file))
    await waitFor(() => expect(first.result.current.loading).toBe(false))
    expect(first.result.current.data).toEqual(payload)
    expect(first.result.current.fromCache).toBe(false)

    // A second mount (e.g. a page reload) must not paint last session's cached copy as if
    // it were current - it shows the loading state until the live fetch actually resolves,
    // even though a cached copy already exists.
    const second = renderHook(() => useData(file))
    expect(second.result.current.loading).toBe(true)
    expect(second.result.current.data).toBe(null)
    await waitFor(() => expect(second.result.current.loading).toBe(false))
    expect(second.result.current.fromCache).toBe(false)
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

  it('stays on the loading state while a fetch is in flight, even with a Cache API copy available', async () => {
    const payload = { data: { generated_at: '2026-08-01T00:00:00Z', research: [] }, cachedAt: 1754000000000 }
    const fakeCache = {
      match: vi.fn().mockResolvedValue({ json: () => Promise.resolve(payload) }),
      put: vi.fn(), delete: vi.fn(),
    }
    vi.stubGlobal('caches', { open: vi.fn().mockResolvedValue(fakeCache), delete: vi.fn().mockResolvedValue(true) })
    // Network revalidation never resolves - the cached copy must not sneak onto the screen
    // while it's still pending, even though it's readable.
    vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})))

    const hook = renderHook(() => useData('big-fixture.json'))
    await act(async () => { await Promise.resolve(); await Promise.resolve(); await Promise.resolve() })
    expect(hook.result.current.data).toBe(null)
    expect(hook.result.current.loading).toBe(true)
  })

  it('falls back to the Cache API layer when a fetch fails and no localStorage copy exists', async () => {
    const payload = { data: { generated_at: '2026-08-01T00:00:00Z', research: [] }, cachedAt: 1754000000000 }
    const fakeCache = {
      match: vi.fn().mockResolvedValue({ json: () => Promise.resolve(payload) }),
      put: vi.fn(), delete: vi.fn(),
    }
    vi.stubGlobal('caches', { open: vi.fn().mockResolvedValue(fakeCache), delete: vi.fn().mockResolvedValue(true) })
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')))

    const hook = renderHook(() => useData('big-fixture.json'))
    await waitFor(() => expect(hook.result.current.loading).toBe(false))
    expect(hook.result.current.data).toEqual(payload.data)
    expect(hook.result.current.fromCache).toBe(true)
    expect(hook.result.current.error).toBeTruthy()
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
