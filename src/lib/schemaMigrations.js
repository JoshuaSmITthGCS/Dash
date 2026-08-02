// Read-time schema migration for the pipeline's JSON snapshots.
//
// The frontend reads committed JSON files directly, so a schema change breaks it silently
// unless something reconciles the versions. The rule the pipeline follows is additive-only:
// new fields may appear, existing fields are never renamed or removed. That keeps old
// readers working against new data. The remaining case is the reverse — a new reader
// against an older committed snapshot, which happens on every deploy where the site ships
// before the next data refresh runs.
//
// So: deploy readers before writers, and migrate N -> N+1 here at load time. Each migration
// only has to know how to get from one version to the next; the runner chains them.

export const ADVISOR_SCHEMA_VERSION = 2
export const ETF_SCHEMA_VERSION = 3

// v1 -> v2: market-behavior detail keys changed when the ad hoc trend/risk formulas were
// replaced with 12-1 momentum and real Sharpe/Sortino ratios, and the theme screen and
// data-freshness blocks were added. Old snapshots get the new key names filled in from the
// closest old equivalent, so a component can read one shape regardless of file age.
function advisorV1ToV2(payload) {
  const migrateRow = (row) => {
    const technical = row.technical_detail
    if (!technical) return row
    const migrated = { ...technical }
    // `trend` was 50 + 20d*2 + 60d*0.5; the nearest honest stand-in is the same directional
    // reading, flagged so the UI can say it predates the rebuild rather than implying a
    // 12-1 momentum figure that was never computed.
    if (migrated.momentum_12_1 == null && technical.trend != null) {
      migrated.momentum_12_1 = technical.trend
      migrated.momentum_is_legacy_trend = true
    }
    if (migrated.risk_adjusted == null && technical.risk != null) {
      migrated.risk_adjusted = technical.risk
      migrated.risk_is_legacy_formula = true
    }
    return { ...row, technical_detail: migrated }
  }

  return {
    ...payload,
    schema_version: 2,
    research: (payload.research || []).map(migrateRow),
    screen_universe: (payload.screen_universe || []).map(migrateRow),
    theme_screen: payload.theme_screen || {
      themes: [],
      by_ticker: {},
      unavailable_reason: 'This snapshot predates the trend-exposure layer.',
    },
  }
}

// v2 -> v3: peer-group ranking. Older ETF snapshots ranked every fund against one mixed
// batch, so their ranks are cross-asset-class whether they said so or not. Labelling them
// is more honest than leaving the field blank and letting the UI imply a like-for-like rank.
function etfV2ToV3(payload) {
  return {
    ...payload,
    schema_version: 3,
    etfs: (payload.etfs || []).map((row) => ({
      ...row,
      peer_group: row.peer_group || row.category || 'other',
      ranked_against: row.ranked_against || '_pooled',
      cross_asset_class_rank: row.cross_asset_class_rank ?? true,
    })),
  }
}

const MIGRATIONS = {
  advisor: { 1: advisorV1ToV2 },
  etfs: { 2: etfV2ToV3 },
}

const TARGETS = { advisor: ADVISOR_SCHEMA_VERSION, etfs: ETF_SCHEMA_VERSION }

/**
 * Bring a payload up to the version this build expects.
 *
 * Unknown datasets pass through untouched. A payload newer than this build is also left
 * alone: additive-only means the extra fields are simply ignored, which is the whole point
 * of the convention.
 */
export function migrate(dataset, payload) {
  if (!payload || typeof payload !== 'object') return payload
  const target = TARGETS[dataset]
  const steps = MIGRATIONS[dataset]
  if (!target || !steps) return payload

  let current = payload
  let version = Number(current.schema_version) || 1
  let guard = 0
  while (version < target && steps[version] && guard < 10) {
    current = steps[version](current)
    const next = Number(current.schema_version) || version + 1
    if (next <= version) break
    version = next
    guard += 1
  }
  return current
}

/** Which dataset a data filename belongs to, for the loader to pick a migration chain. */
export function datasetFor(file) {
  const name = String(file).split('?')[0].replace(/\.json$/, '')
  return name in TARGETS ? name : null
}
