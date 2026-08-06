import modelSettings from '../../pipeline/config/settings.json'

// Read-time schema migration for the pipeline's JSON snapshots.
//
// The frontend reads committed JSON files directly, so a schema change breaks it silently
// unless something reconciles the versions. The rule the pipeline follows is additive-only:
// new fields may appear, existing fields are never renamed or removed. That keeps old
// readers working against new data. The remaining case is the reverse – a new reader
// against an older committed snapshot, which happens on every deploy where the site ships
// before the next data refresh runs.
//
// So: deploy readers before writers, and migrate N -> N+1 here at load time. Each migration
// only has to know how to get from one version to the next; the runner chains them.

export const ADVISOR_SCHEMA_VERSION = modelSettings.model.advisor_schema_version
export const ETF_SCHEMA_VERSION = modelSettings.model.etf_schema_version

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

// v2 -> v3: all artifacts now publish one reproducible model metadata envelope. Older
// advisor snapshots already carried most of the same facts in run_manifest, so the reader
// promotes them without inventing values and labels unavailable facts explicitly.
function advisorV2ToV3(payload) {
  const manifest = payload.run_manifest || {}
  const generatedAt = payload.generated_at || manifest.generated_at || null
  const semanticVersion = payload.model_version || manifest.model_version || 'unknown'
  return {
    ...payload,
    schema_version: 3,
    model_version: semanticVersion,
    model_metadata: payload.model_metadata || {
      semantic_version: semanticVersion,
      git_commit_sha: manifest.code_commit_hash || 'unknown',
      config_hash: manifest.config_hash || 'unknown',
      generated_at: generatedAt,
    },
  }
}

// v3 -> v4: explainability is additive. Old snapshots cannot recreate historical points
// or exact attribution, so the reader exposes a truthful accumulating contract.
function advisorV3ToV4(payload) {
  const migrateRow = (row) => ({
    ...row,
    explainability: row.explainability || {
      active_variant: 'champion',
      attribution: {},
      factor_bars: {},
      metrics: { champion: [], challenger: [] },
      score_history: {
        status: 'accumulating',
        stored_months: 0,
        required_months: modelSettings.explainability.score_history_minimum_months,
        points: [],
      },
      anomalies: [],
    },
    theme_exposure: row.theme_exposure || [],
  })
  return {
    ...payload,
    schema_version: 4,
    research: (payload.research || []).map(migrateRow),
    portfolio_coverage: (payload.portfolio_coverage || []).map(migrateRow),
  }
}

// v4 -> v5: news scoring now records its filtering and weighting inputs. Historical
// snapshots retain their old flat score and are labelled as legacy so the interface never
// implies recency, source, entity-confidence, or novelty processing that did not occur.
function advisorV4ToV5(payload) {
  const migrateRow = (row) => ({
    ...row,
    sentiment_detail: {
      weighting_method: 'legacy_flat_average',
      full_coverage_article_count: modelSettings.news_intelligence.full_coverage_article_count,
      syndicated_copies_removed: 0,
      discarded_low_confidence: 0,
      articles: [],
      ...(row.sentiment_detail || {}),
    },
  })
  return {
    ...payload,
    schema_version: 5,
    research: (payload.research || []).map(migrateRow),
    portfolio_coverage: (payload.portfolio_coverage || []).map(migrateRow),
    news: (payload.news || []).map((item) => ({
      content_type: 'commentary',
      source_quality_tier: 'legacy_unclassified',
      ...item,
    })),
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

// v3 -> v4: ETF rows may carry holdings-sector weights for portfolio look-through.
// Older snapshots cannot reconstruct those weights, so the migration marks them missing.
function etfV3ToV4(payload) {
  return {
    ...payload,
    schema_version: 4,
    etfs: (payload.etfs || []).map((row) => ({
      ...row,
      sector_weights: row.sector_weights || null,
      sector_lookthrough_available: Boolean(row.sector_weights),
    })),
  }
}

// v4 -> v5: rows may also carry the fund's published largest constituents. Historical
// snapshots cannot reconstruct them, so position look-through remains explicitly absent.
function etfV4ToV5(payload) {
  return {
    ...payload,
    schema_version: 5,
    etfs: (payload.etfs || []).map((row) => ({
      ...row,
      top_holdings: row.top_holdings || null,
      position_lookthrough_available: Boolean(row.top_holdings),
    })),
  }
}

const MIGRATIONS = {
  advisor: { 1: advisorV1ToV2, 2: advisorV2ToV3, 3: advisorV3ToV4, 4: advisorV4ToV5 },
  etfs: { 2: etfV2ToV3, 3: etfV3ToV4, 4: etfV4ToV5 },
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
