import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import { useAdvisorRefresh } from './useAdvisorRefresh'
import { useAuth } from './FirebaseAuthContext'

vi.mock('./FirebaseAuthContext', () => ({ useAuth: vi.fn() }))

const POLL_INTERVAL_MS = 20_000

describe('useAdvisorRefresh', () => {
  beforeEach(() => {
    useAuth.mockReturnValue({ currentUser: { getIdToken: () => Promise.resolve('token') } })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  it('treats a successful GitHub Actions run as done, even when a rescore leaves generated_at unchanged', async () => {
    vi.useFakeTimers()
    const reload = vi.fn().mockResolvedValue({ generated_at: '2026-08-01T00:00:00Z' })
    vi.stubGlobal('fetch', vi.fn((url, init) => {
      if (init?.method === 'POST') {
        return Promise.resolve({ ok: true, status: 202, json: () => Promise.resolve({ ok: true }) })
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
          run_id: 1, status: 'completed', conclusion: 'success', percent: 100, stage: 'Publishing the website update',
        }),
      })
    }))

    const { result } = renderHook(() => useAdvisorRefresh('2026-08-01T00:00:00Z', reload, []))

    await act(async () => { await result.current.requestReanalyze() })
    expect(result.current.status).toBe('pending')

    await act(async () => { await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS) })

    expect(result.current.status).toBe('success')
    expect(result.current.message).toBe('Reanalysis complete. You are viewing the newly rescored data.')
    expect(reload).toHaveBeenCalled()
  })

  it('falls back to comparing generated_at when the progress endpoint is unavailable', async () => {
    vi.useFakeTimers()
    const reload = vi.fn().mockResolvedValue({ generated_at: '2026-08-02T00:00:00Z' })
    vi.stubGlobal('fetch', vi.fn((url, init) => {
      if (init?.method === 'POST') {
        return Promise.resolve({ ok: true, status: 202, json: () => Promise.resolve({ ok: true }) })
      }
      return Promise.resolve({ ok: false })
    }))

    const { result } = renderHook(() => useAdvisorRefresh('2026-08-01T00:00:00Z', reload, []))

    await act(async () => { await result.current.requestRefresh() })
    await act(async () => { await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS) })

    expect(result.current.status).toBe('success')
    expect(result.current.message).toBe('Market data updated. You are viewing the latest published refresh.')
  })

  it('requests a full-universe workflow and exposes its loading state', async () => {
    const reload = vi.fn().mockResolvedValue({ generated_at: '2026-08-01T00:00:00Z' })
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 202,
      json: () => Promise.resolve({ ok: true, run_id: 888 }),
    })
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useAdvisorRefresh('2026-08-01T00:00:00Z', reload, ['AAPL']))
    await act(async () => { await result.current.requestFullRefresh() })

    const [, init] = fetchMock.mock.calls[0]
    // focus_symbols is empty unless the caller asked for a focused re-rank: an ordinary
    // refresh must never narrow itself to a named set by accident.
    expect(JSON.parse(init.body)).toEqual({ mode: 'data', universe_scope: 'full', symbols: ['AAPL'], focus_symbols: [] })
    expect(result.current).toMatchObject({
      status: 'pending',
      refreshing: true,
      activeMode: 'data',
      activeScope: 'full',
      stage: 'Waiting for a full-universe runner',
    })
    expect(result.current.message).toMatch(/Full-universe refresh started/)
  })

  it('sends a focused re-rank as its own field, keeping holdings separate', async () => {
    // The two lists mean different things to the pipeline: `symbols` is dispatched as the
    // user's holdings and feeds portfolio coverage, so a screen re-ranking its own members
    // through that field would tag every one of them as something the user owns.
    const reload = vi.fn().mockResolvedValue({ generated_at: '2026-08-01T00:00:00Z' })
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 202,
      json: () => Promise.resolve({ ok: true, run_id: 999 }),
    })
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(
      () => useAdvisorRefresh('2026-08-01T00:00:00Z', reload, ['AAPL'], ['nvda', 'etn']))
    await act(async () => { await result.current.requestFocusedRefresh() })

    const [, init] = fetchMock.mock.calls[0]
    expect(JSON.parse(init.body)).toEqual({
      mode: 'data',
      universe_scope: 'fast',
      symbols: ['AAPL'],
      focus_symbols: ['NVDA', 'ETN'],
    })
    expect(result.current.activeFocused).toBe(true)
  })

  it('locks onto the run_id returned by the dispatch so the first poll targets it directly', async () => {
    vi.useFakeTimers()
    const reload = vi.fn().mockResolvedValue({ generated_at: '2026-08-01T00:00:00Z' })
    const fetchMock = vi.fn((url, init) => {
      if (init?.method === 'POST') {
        return Promise.resolve({ ok: true, status: 202, json: () => Promise.resolve({ ok: true, run_id: 777 }) })
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
          run_id: 777, status: 'in_progress', conclusion: null, percent: 10, stage: 'Restore the Yahoo/Alpha Vantage/SEC response cache',
        }),
      })
    })
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useAdvisorRefresh('2026-08-01T00:00:00Z', reload, []))
    await act(async () => { await result.current.requestReanalyze() })
    await act(async () => { await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS) })

    const getCall = fetchMock.mock.calls.find(([, init]) => init?.method !== 'POST')
    expect(getCall[0]).toContain('run_id=777')
  })

  it('keeps waiting past the 5-minute estimate while GitHub confirms the reanalysis is still running', async () => {
    // The rescore path outgrew its old "under a minute" estimate - it now re-runs every
    // disk-only screen build plus the validation suite - and the fixed 5-minute timer was
    // erroring out every healthy reanalysis while the run went on to succeed. A run the
    // status endpoint reports as in_progress is never a timeout.
    vi.useFakeTimers()
    const reload = vi.fn().mockResolvedValue({ generated_at: '2026-08-01T00:00:00Z' })
    vi.stubGlobal('fetch', vi.fn((url, init) => {
      if (init?.method === 'POST') {
        return Promise.resolve({ ok: true, status: 202, json: () => Promise.resolve({ ok: true, run_id: 1 }) })
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ active: true, run_id: 1, status: 'in_progress', conclusion: null, percent: 10, stage: 'still going' }),
      })
    }))

    const { result } = renderHook(() => useAdvisorRefresh('2026-08-01T00:00:00Z', reload, []))
    await act(async () => { await result.current.requestReanalyze() })

    await act(async () => { await vi.advanceTimersByTimeAsync(12 * 60_000) })
    expect(result.current.status).toBe('pending')
  })

  it('times out a reanalysis after 5 minutes when no live run can be found at all', async () => {
    // The soft deadline still matters for the case it was always really about: the
    // dispatch never produced a run the status endpoint can see, so there is nothing to
    // wait on and generated_at is never going to move.
    vi.useFakeTimers()
    const reload = vi.fn().mockResolvedValue({ generated_at: '2026-08-01T00:00:00Z' })
    vi.stubGlobal('fetch', vi.fn((url, init) => {
      if (init?.method === 'POST') {
        return Promise.resolve({ ok: true, status: 202, json: () => Promise.resolve({ ok: true }) })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ active: false }) })
    }))

    const { result } = renderHook(() => useAdvisorRefresh('2026-08-01T00:00:00Z', reload, []))
    await act(async () => { await result.current.requestReanalyze() })

    await act(async () => { await vi.advanceTimersByTimeAsync(4 * 60_000) })
    expect(result.current.status).toBe('pending')

    await act(async () => { await vi.advanceTimersByTimeAsync(2 * 60_000) })
    expect(result.current.status).toBe('error')
    expect(result.current.message).toMatch(/taking longer than expected/)
  })

  it('reports a cancelled workflow run instead of polling until the timeout', async () => {
    vi.useFakeTimers()
    const reload = vi.fn().mockResolvedValue({ generated_at: '2026-08-01T00:00:00Z' })
    vi.stubGlobal('fetch', vi.fn((url, init) => {
      if (init?.method === 'POST') {
        return Promise.resolve({ ok: true, status: 202, json: () => Promise.resolve({ ok: true, run_id: 1 }) })
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ run_id: 1, status: 'completed', conclusion: 'cancelled', percent: 40, stage: 'Fetch and score stock research' }),
      })
    }))

    const { result } = renderHook(() => useAdvisorRefresh('2026-08-01T00:00:00Z', reload, []))
    await act(async () => { await result.current.requestRefresh() })
    await act(async () => { await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS) })

    expect(result.current.status).toBe('error')
    expect(result.current.message).toMatch(/cancelled before it could publish/)
  })

  it('reports a failed workflow run instead of waiting for the timeout', async () => {
    vi.useFakeTimers()
    const reload = vi.fn().mockResolvedValue({ generated_at: '2026-08-01T00:00:00Z' })
    vi.stubGlobal('fetch', vi.fn((url, init) => {
      if (init?.method === 'POST') {
        return Promise.resolve({ ok: true, status: 202, json: () => Promise.resolve({ ok: true }) })
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ run_id: 1, status: 'completed', conclusion: 'failure', percent: 40, stage: 'Fetch and score stock research' }),
      })
    }))

    const { result } = renderHook(() => useAdvisorRefresh('2026-08-01T00:00:00Z', reload, []))

    await act(async () => { await result.current.requestRefresh() })
    await act(async () => { await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS) })

    expect(result.current.status).toBe('error')
    expect(result.current.message).toMatch(/failed before it could publish/)
  })
})
