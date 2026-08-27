import { describe, expect, it } from 'vitest'
import { CHART_TYPES, validateRenderer, toTableRows } from './chartContract.js'

describe('CHART_TYPES', () => {
  it('does not include radar — banned in every theme', () => {
    expect(CHART_TYPES).not.toContain('radar')
  })

  it('includes profile as the radar replacement', () => {
    expect(CHART_TYPES).toContain('profile')
  })

  it('includes dial, which must render a labeled scale (unlabeled gauges are banned)', () => {
    expect(CHART_TYPES).toContain('dial')
  })

  it('does not include a bare donut/pie type — composition replaces it', () => {
    expect(CHART_TYPES).not.toContain('donut')
    expect(CHART_TYPES).not.toContain('pie')
    expect(CHART_TYPES).toContain('composition')
  })
})

describe('validateRenderer', () => {
  it('passes a renderer implementing every type', () => {
    const renderer = Object.fromEntries(CHART_TYPES.map((type) => [type, () => null]))
    expect(validateRenderer(renderer)).toEqual({ valid: true, missing: [] })
  })

  it('reports every missing type', () => {
    const result = validateRenderer({ line: () => null })
    expect(result.valid).toBe(false)
    expect(result.missing).toContain('dial')
    expect(result.missing).toContain('profile')
    expect(result.missing).not.toContain('line')
  })

  it('handles an undefined renderer', () => {
    const result = validateRenderer(undefined)
    expect(result.valid).toBe(false)
    expect(result.missing).toHaveLength(CHART_TYPES.length)
  })
})

describe('toTableRows', () => {
  it('converts a series of {x,y} points', () => {
    const rows = toTableRows({ series: [{ x: '2026-01', y: 1 }, { x: '2026-02', y: 2 }] })
    expect(rows).toEqual([{ index: 0, x: '2026-01', y: 1 }, { index: 1, x: '2026-02', y: 2 }])
  })

  it('falls back to a plain values array, indexed', () => {
    const rows = toTableRows({ values: [10, 20, 30] })
    expect(rows).toEqual([{ index: 0, x: 0, y: 10 }, { index: 1, x: 1, y: 20 }, { index: 2, x: 2, y: 30 }])
  })

  it('returns an empty array for no data', () => {
    expect(toTableRows()).toEqual([])
  })
})
