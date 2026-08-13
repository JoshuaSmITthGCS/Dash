const title = (value = '') => String(value)
  .replace(/_/g, ' ')
  .replace(/\b\w/g, (letter) => letter.toUpperCase())

const pct = (value) => (value == null ? '–' : `${Math.round(value * 100)}%`)
const score = (value) => (Number.isFinite(value) ? Math.round(value) : '–')

function companyCopy(label) {
  return {
    buy: 'Entry requirements currently pass, subject to portfolio capacity.',
    accumulate: 'Business quality is strong. Timing supports gradual additions.',
    hold_existing_position: 'Current evidence supports maintaining an existing position. This is not an entry signal.',
    quality_watch: 'Business quality is strong, but timing is weak.',
    quality_watch_timeliness_unavailable: 'Business quality is strong. No timing evidence was obtained, so this cannot be called an entry.',
    hold_or_watch_timeliness_unavailable: 'Business quality is acceptable. No timing evidence was obtained.',
    watch: 'Evidence is incomplete or mixed. No position change is implied.',
    tactical_candidate: 'Timing is favorable, but structural quality does not qualify as a long-term buy.',
    avoid: 'Do not initiate new exposure under the current company evidence.',
    sell_thesis: 'Verified company evidence has invalidated the investment thesis.',
    insufficient_evidence: 'Company evidence is too limited for prescriptive guidance.',
  }[label] || 'No company-level instruction is available.'
}

function positionCopy(action) {
  const reasons = action?.reason_codes || []
  if (action?.label === 'exit' && reasons.some((reason) => reason.includes('stop'))) {
    return 'A predefined position rule triggered. This does not imply fundamental impairment.'
  }
  if (action?.label === 'trim' && action.reason_namespace === 'portfolio_concentration') {
    return 'Reduce portfolio concentration independently of the company thesis.'
  }
  if (action?.label === 'trim') return 'Reduction size reflects severity, confidence, concentration, and trading friction.'
  if (action?.label === 'review') return 'The calculated trade is economically immaterial and needs review.'
  if (action?.label === 'hold') return 'No position-level rule requires a change.'
  return 'No user position was supplied to the shadow backend, so position rules were not assessed.'
}

/**
 * A layer with no effective score gets its stated reason, not a number. Rendering
 * "50 effective · 0% confidence" for a layer that resolved nothing presented a placeholder
 * as a measurement.
 */
function layerDetail(layer) {
  if (!layer || layer.effective_score == null) {
    return layer?.unavailable_reason || 'No inputs resolved, so no score is published'
  }
  return `${score(layer.effective_score)} effective · ${pct(layer.evidence_weight_resolved)} of evidence weight resolved`
}

function Layer({ label, value, detail }) {
  return (
    <div className="shadow-layer">
      <span>{label}</span>
      <strong>{title(value || 'unavailable')}</strong>
      {detail && <small>{detail}</small>}
    </div>
  )
}

export default function RecommendationShadowPanel({ legacy, shadow }) {
  if (!shadow) return null
  const company = shadow.company?.action || {}
  const position = shadow.position_action || {}
  const structural = shadow.company_structural_state || shadow.company?.structural || {}
  const timeliness = shadow.company_timeliness_state || shadow.company?.timeliness || {}
  const portfolio = shadow.portfolio_fit_state || shadow.portfolio_fit || {}
  const ruleState = shadow.position_rule_state || {}
  const dataQuality = shadow.data_quality || {}
  const flagged = (shadow.company?.deterioration_groups || []).filter((group) => group.flagged)

  return (
    <section className="shadow-decision-panel" aria-label="Shadow recommendation policy comparison">
      <div className="shadow-heading">
        <div>
          <span className="kpi-label">Policy comparison</span>
          <h3>Active guidance vs. shadow model</h3>
        </div>
        <span className="chip">Shadow · {shadow.model_version}</span>
      </div>

      <div className="shadow-comparison">
        <div>
          <span>Active legacy policy</span>
          <strong>{legacy?.action || 'Unavailable'}{legacy?.suggestedTrimPct ? ` ${legacy.suggestedTrimPct}%` : ''}</strong>
          <small>Displayed for comparison; production behavior is unchanged.</small>
        </div>
        <div>
          <span>Shadow company action</span>
          <strong>{title(company.label)}</strong>
          <small>{companyCopy(company.label)}</small>
        </div>
        <div>
          <span>Shadow position action</span>
          <strong>
            {title(position.label)}
            {position.trim_percent > 0 ? ` ${Math.round(position.trim_percent * 100)}%` : ''}
          </strong>
          <small>{positionCopy(position)}</small>
        </div>
      </div>

      <div className="shadow-layers">
        <Layer label="Structural" value={structural.classification} detail={layerDetail(structural)} />
        <Layer label="Timeliness" value={timeliness.classification} detail={layerDetail(timeliness)} />
        {/* "Below target" against a default 3% target is what this reads for every company
            when no portfolio is supplied, which is not an assessment. Say so instead. */}
        <Layer
          label="Portfolio fit"
          value={portfolio.current_weight ? portfolio.classification : 'not assessed'}
          detail={(portfolio.reason_codes || []).map(title).join(' · ')
            || (portfolio.current_weight ? '' : 'No portfolio supplied, so fit was not assessed')}
        />
        <Layer label="Position rules" value={ruleState.classification} detail={ruleState.profile ? `Profile: ${title(ruleState.profile)}` : 'Requires user position inputs'} />
      </div>

      <div className="shadow-evidence">
        <span>
          Company evidence: <b>{pct(dataQuality.evidence_weight_resolved)} of evidence weight resolved</b> · <b>{pct(dataQuality.data_coverage)} data coverage</b>
          {(dataQuality.unassessed_layers || []).length > 0 && (
            <> · <b>not assessed: {dataQuality.unassessed_layers.map(title).join(', ')}</b></>
          )}
        </span>
        <span>{flagged.length} of 3 independent deterioration groups flagged</span>
      </div>

      {(company.reason_codes?.length > 0 || position.reason_codes?.length > 0) && (
        <ul className="shadow-reasons">
          {[...(company.reason_codes || []), ...(position.reason_codes || [])]
            .filter((reason, index, all) => all.indexOf(reason) === index)
            .map((reason) => <li key={reason}>{title(reason)}</li>)}
        </ul>
      )}
    </section>
  )
}
