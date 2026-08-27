import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { cap, registerLedgerIds, warnIfUnknownCapability } from './capability.js'

describe('cap', () => {
  it('returns a data-capability-id prop for a given id', () => {
    expect(cap('metric.report.deflated-sharpe')).toEqual({ 'data-capability-id': 'metric.report.deflated-sharpe' })
  })

  it('returns an empty object for no id, never a malformed attribute', () => {
    expect(cap()).toEqual({})
    expect(cap(null)).toEqual({})
  })
})

describe('warnIfUnknownCapability', () => {
  let errorSpy

  beforeEach(() => {
    errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
  })

  afterEach(() => {
    errorSpy.mockRestore()
    registerLedgerIds([])
  })

  it('is a no-op until ledger ids are registered', () => {
    warnIfUnknownCapability('nav.dest.portfolio')
    expect(errorSpy).not.toHaveBeenCalled()
  })

  it('warns for an id outside the registered ledger set', () => {
    registerLedgerIds(['nav.dest.portfolio', 'nav.dest.home'])
    warnIfUnknownCapability('nav.dest.made-up')
    expect(errorSpy).toHaveBeenCalledOnce()
  })

  it('stays quiet for a known id', () => {
    registerLedgerIds(['nav.dest.portfolio'])
    warnIfUnknownCapability('nav.dest.portfolio')
    expect(errorSpy).not.toHaveBeenCalled()
  })
})
