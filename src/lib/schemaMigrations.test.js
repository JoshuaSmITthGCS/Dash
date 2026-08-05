import { describe, expect, it } from 'vitest'
import {
  ADVISOR_SCHEMA_VERSION, ETF_SCHEMA_VERSION, datasetFor, migrate,
} from './schemaMigrations'

const legacyAdvisor = {
  schema_version: 1,
  research: [{
    ticker: 'AAA',
    technical_detail: { trend: 72, risk: 61, return_20d: 4.2 },
  }],
}

describe('advisor migrations', () => {
  it('brings a v1 snapshot up to the version this build expects', () => {
    const migrated = migrate('advisor', legacyAdvisor)
    expect(migrated.schema_version).toBe(ADVISOR_SCHEMA_VERSION)
  })

  it('maps the retired trend and risk fields onto their replacements', () => {
    const detail = migrate('advisor', legacyAdvisor).research[0].technical_detail
    expect(detail.momentum_12_1).toBe(72)
    expect(detail.risk_adjusted).toBe(61)
  })

  it('flags migrated values so the UI never implies a 12-1 figure that was not computed', () => {
    const detail = migrate('advisor', legacyAdvisor).research[0].technical_detail
    expect(detail.momentum_is_legacy_trend).toBe(true)
    expect(detail.risk_is_legacy_formula).toBe(true)
  })

  it('supplies an empty theme screen for snapshots predating the layer', () => {
    const migrated = migrate('advisor', legacyAdvisor)
    expect(migrated.theme_screen.themes).toEqual([])
    expect(migrated.theme_screen.unavailable_reason).toBeTruthy()
  })

  it('leaves a current-version payload untouched', () => {
    const current = { schema_version: 3, research: [], theme_screen: { themes: [] } }
    expect(migrate('advisor', current)).toBe(current)
  })

  it('promotes legacy run metadata into the reproducible model envelope', () => {
    const migrated = migrate('advisor', {
      schema_version: 2,
      generated_at: '2026-08-05T00:00:00Z',
      model_version: '2.4.0',
      run_manifest: { code_commit_hash: 'abc123', config_hash: 'cfg123' },
      research: [],
    })
    expect(migrated.model_metadata).toEqual({
      semantic_version: '2.4.0',
      git_commit_sha: 'abc123',
      config_hash: 'cfg123',
      generated_at: '2026-08-05T00:00:00Z',
    })
  })

  it('does not downgrade a payload newer than this build', () => {
    // Additive-only means a newer writer just adds fields an older reader ignores.
    const future = { schema_version: 99, research: [], brand_new_field: 1 }
    expect(migrate('advisor', future).brand_new_field).toBe(1)
    expect(migrate('advisor', future).schema_version).toBe(99)
  })

  it('preserves fields the migration does not touch', () => {
    const migrated = migrate('advisor', { ...legacyAdvisor, disclaimer: 'keep me' })
    expect(migrated.disclaimer).toBe('keep me')
  })
})

describe('etf migrations', () => {
  const legacyEtfs = {
    schema_version: 2,
    etfs: [{ ticker: 'SPY', category: 'broad_market', scores: { overall: 80 } }],
  }

  it('labels pre-peer-group ranks as cross-asset-class rather than leaving them blank', () => {
    // Old snapshots really were ranked against one mixed batch, so saying so is more
    // honest than a blank field the UI would read as a like-for-like comparison.
    const migrated = migrate('etfs', legacyEtfs)
    expect(migrated.schema_version).toBe(ETF_SCHEMA_VERSION)
    expect(migrated.etfs[0].cross_asset_class_rank).toBe(true)
    expect(migrated.etfs[0].ranked_against).toBe('_pooled')
  })

  it('falls back to the category when no peer group was recorded', () => {
    expect(migrate('etfs', legacyEtfs).etfs[0].peer_group).toBe('broad_market')
  })

  it('marks older ETF snapshots as unavailable for sector look-through', () => {
    expect(migrate('etfs', { schema_version: 3, etfs: [{ ticker: 'SPY' }] }).etfs[0]).toMatchObject({
      sector_weights: null,
      sector_lookthrough_available: false,
      top_holdings: null,
      position_lookthrough_available: false,
    })
  })
})

describe('dataset resolution', () => {
  it('recognizes the datasets that have migrations', () => {
    expect(datasetFor('advisor.json')).toBe('advisor')
    expect(datasetFor('etfs.json?v=123')).toBe('etfs')
  })

  it('passes unknown datasets straight through', () => {
    expect(datasetFor('news.json')).toBeNull()
    const payload = { anything: true }
    expect(migrate('news', payload)).toBe(payload)
  })

  it('tolerates null and non-object payloads', () => {
    expect(migrate('advisor', null)).toBeNull()
    expect(migrate('advisor', 'oops')).toBe('oops')
  })
})
