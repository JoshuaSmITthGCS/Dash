import { afterEach, describe, expect, it, vi } from 'vitest'
import { SCREEN_WORKFLOWS, locateDispatchedRun, parseRequestBody, workflowProgress } from '../../netlify/functions/refresh-data.mjs'

describe('parseRequestBody', () => {
  it('allows an explicit full-universe refresh request', () => {
    expect(parseRequestBody(JSON.stringify({
      mode: 'data',
      universe_scope: 'full',
      symbols: ['aapl', 'BRK.B'],
    }))).toEqual({ symbols: ['AAPL', 'BRK.B'], focusSymbols: [], mode: 'data', universeScope: 'full', screen: 'research' })
  })

  it('keeps fast refresh as the safe default for existing controls', () => {
    expect(parseRequestBody(JSON.stringify({ universe_scope: 'unexpected' }))).toEqual({
      symbols: [],
      focusSymbols: [],
      mode: 'data',
      universeScope: 'fast',
      screen: 'research',
    })
  })

  it('keeps a re-ranking request separate from the caller s holdings', () => {
    // They are dispatched as different workflow inputs: `symbols` means "the user owns
    // this" and feeds portfolio coverage, so a screen asking to re-rank its own members
    // through that field would relabel every one of them as a holding.
    const parsed = parseRequestBody(JSON.stringify({
      symbols: ['aapl'],
      focus_symbols: ['nvda', 'etn', 'not a ticker', 'MU'],
    }))
    expect(parsed.symbols).toEqual(['AAPL'])
    expect(parsed.focusSymbols).toEqual(['NVDA', 'ETN', 'MU'])
  })

  it('accepts a whole screen s worth of names to re-rank, not just a portfolio s worth', () => {
    // Truncating here would re-rank a slice of the list while presenting it as the list.
    const many = Array.from({ length: 300 }, (_, index) => `T${index}`)
    expect(parseRequestBody(JSON.stringify({ focus_symbols: many })).focusSymbols).toHaveLength(300)
  })

  it('selects a screen collector by name', () => {
    expect(parseRequestBody(JSON.stringify({ screen: 'congress' })).screen).toBe('congress')
    expect(parseRequestBody(JSON.stringify({ screen: 'institutional' })).screen).toBe('institutional')
  })

  it('falls back to the research refresh rather than dispatching an unknown workflow', () => {
    // The client sends a screen *name*, never a workflow file, so an unrecognised value
    // can only land on the default - it can never reach a workflow nobody intended.
    expect(parseRequestBody(JSON.stringify({ screen: '../../evil' })).screen).toBe('research')
    expect(parseRequestBody(JSON.stringify({ screen: 'constructor' })).screen).toBe('research')
  })

  it('maps every selectable screen to a real workflow file', () => {
    expect(Object.values(SCREEN_WORKFLOWS).map((entry) => entry.workflow)).toEqual([
      'refresh-advisor.yml', 'congress-trades.yml', 'institutional-13f.yml',
      'sec-filings.yml', 'inside-information.yml',
    ])
    // The collectors declare no dispatch inputs; sending any would make GitHub reject it.
    expect(SCREEN_WORKFLOWS.congress.acceptsInputs).toBe(false)
    expect(SCREEN_WORKFLOWS.institutional.acceptsInputs).toBe(false)
    expect(SCREEN_WORKFLOWS.filings.acceptsInputs).toBe(false)
    expect(SCREEN_WORKFLOWS['inside-information'].acceptsInputs).toBe(false)
  })

  it('selects the two new screen collectors by name', () => {
    expect(parseRequestBody(JSON.stringify({ screen: 'filings' })).screen).toBe('filings')
    expect(parseRequestBody(JSON.stringify({ screen: 'inside-information' })).screen).toBe('inside-information')
  })
})

describe('workflowProgress for a screen collector', () => {
  it('scores the collector steps rather than the research workflow ones', () => {
    const jobs = [{ steps: [
      { name: 'Run actions/checkout@v4', status: 'completed', conclusion: 'success' },
      { name: 'Run actions/setup-python@v5', status: 'completed', conclusion: 'success' },
      { name: 'Run pip install -r pipeline/requirements.txt', status: 'completed', conclusion: 'success' },
      { name: 'Collect curated-manager 13F positions and map CUSIPs via OpenFIGI', status: 'in_progress' },
    ] }]

    const progress = workflowProgress(jobs, 'institutional')

    expect(progress.percent).toBe(40)
    expect(progress.stage).toMatch(/Collect curated-manager/)
  })
})

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
