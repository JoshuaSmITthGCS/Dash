import { afterEach, describe, expect, it, vi } from 'vitest'
import { locateDispatchedRun, workflowProgress } from '../../netlify/functions/refresh-data.mjs'

describe('workflowProgress', () => {
  it('weights completed workflow stages and reports the active stage', () => {
    const jobs = [{ steps: [
      { name: 'Select the Eastern-time refresh window', status: 'completed', conclusion: 'success' },
      { name: 'Run actions/checkout@v4', status: 'completed', conclusion: 'success' },
      { name: 'Restore the Yahoo/Alpha Vantage/SEC response cache', status: 'completed', conclusion: 'success' },
      { name: 'Run actions/setup-python@v5', status: 'completed', conclusion: 'success' },
      { name: 'Run pip install -r pipeline/requirements.txt', status: 'completed', conclusion: 'success' },
      { name: 'Append point-in-time estimate snapshots', status: 'completed', conclusion: 'success' },
      { name: 'Fetch and score stock research', status: 'completed', conclusion: 'success' },
      { name: 'Fetch ETF growth screen', status: 'in_progress', conclusion: null },
    ] }]

    expect(workflowProgress(jobs)).toEqual({ percent: 50, stage: 'Fetch ETF growth screen' })
  })
})

describe('locateDispatchedRun', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('finds the one run not present before dispatch, even on the first poll', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ workflow_runs: [{ id: 1 }, { id: 2 }] }),
    }))

    const runId = await locateDispatchedRun('https://api.github.com/repos/x/y/actions/workflows/z.yml', {}, new Set([1]))
    expect(runId).toBe(2)
  })

  it('retries with a no-op sleep until the new run appears', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({ workflow_runs: [{ id: 1 }] }) })
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({ workflow_runs: [{ id: 1 }, { id: 9 }] }) })
    vi.stubGlobal('fetch', fetchMock)

    const runId = await locateDispatchedRun('https://api.github.com/repos/x/y/actions/workflows/z.yml', {}, new Set([1]), { sleep: () => Promise.resolve() })
    expect(runId).toBe(9)
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('gives up and returns null after the run never shows up', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ workflow_runs: [{ id: 1 }] }),
    }))

    const runId = await locateDispatchedRun('https://api.github.com/repos/x/y/actions/workflows/z.yml', {}, new Set([1]), { attempts: 2, sleep: () => Promise.resolve() })
    expect(runId).toBeNull()
  })

  it('tolerates a failed poll and keeps retrying', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: false })
      .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({ workflow_runs: [{ id: 1 }, { id: 5 }] }) })
    vi.stubGlobal('fetch', fetchMock)

    const runId = await locateDispatchedRun('https://api.github.com/repos/x/y/actions/workflows/z.yml', {}, new Set([1]), { sleep: () => Promise.resolve() })
    expect(runId).toBe(5)
  })
})
