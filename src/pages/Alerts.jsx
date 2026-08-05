import { useState } from 'react'
import { Link } from 'react-router-dom'
import Icon from '../components/Icons.jsx'
import { Loading } from '../components/Bits.jsx'
import { ALERT_TYPES, alertConfig, alertRuleLabel, normalizeAlertRule, SCORE_BANDS } from '../lib/alertRules.js'
import { enablePushNotifications, pushCapability } from '../lib/pushNotifications.js'
import { useAlerts } from '../lib/useAlerts.js'
import { useAuth } from '../lib/FirebaseAuthContext.jsx'

const initialRule = () => normalizeAlertRule({ type: 'price_cross', threshold: '', ticker: '' })

function RuleFields({ rule, onChange }) {
  const set = (key, value) => onChange({ ...rule, [key]: value })
  if (rule.type === 'pipeline_stale') return <label><span>Stale after</span><span className="input-suffix"><input type="number" min="1" max="168" inputMode="numeric" value={rule.staleHours} onChange={(event) => set('staleHours', event.target.value)} /><em>hours</em></span></label>
  return <>
    <label><span>Ticker</span><input value={rule.ticker} maxLength="10" autoCapitalize="characters" autoCorrect="off" placeholder="MSFT" onChange={(event) => set('ticker', event.target.value.toUpperCase())} /></label>
    {['price_cross', 'percent_move'].includes(rule.type) && <label><span>Direction</span><select value={rule.direction} onChange={(event) => set('direction', event.target.value)}><option value="above">Crosses above</option><option value="below">Crosses below</option></select></label>}
    {rule.type === 'percent_move' && <label><span>Return window</span><select value={rule.periodDays} onChange={(event) => set('periodDays', Number(event.target.value))}><option value="1">1 day</option><option value="5">5 days</option></select></label>}
    {['price_cross', 'stop_trigger'].includes(rule.type) && <label><span>Price level</span><span className="input-prefix"><em>$</em><input type="number" min="0.01" step="0.01" inputMode="decimal" value={Number.isFinite(rule.threshold) ? rule.threshold : ''} onChange={(event) => set('threshold', event.target.value)} /></span></label>}
    {rule.type === 'percent_move' && <label><span>Move threshold</span><span className="input-suffix"><input type="number" min="0.1" step="0.1" inputMode="decimal" value={Number.isFinite(rule.threshold) ? rule.threshold : alertConfig.default_move_threshold_pct} onChange={(event) => set('threshold', event.target.value)} /><em>%</em></span></label>}
    {rule.type === 'stop_trigger' && <label><span>Stop type</span><select value={rule.stopKind} onChange={(event) => set('stopKind', event.target.value)}><option value="trim">Trim stop</option><option value="exit">Exit stop</option></select></label>}
    {rule.type === 'score_band' && <><label><span>Direction</span><select value={rule.direction} onChange={(event) => set('direction', event.target.value)}><option value="above">Rises into</option><option value="below">Drops out of</option></select></label><label><span>Score band</span><select value={rule.band} onChange={(event) => set('band', event.target.value)}>{SCORE_BANDS.map((band) => <option key={band}>{band}</option>)}</select></label></>}
    {rule.type === 'earnings_upcoming' && <label><span>Notice window</span><span className="input-suffix"><input type="number" min="1" max="90" inputMode="numeric" value={rule.daysAhead} onChange={(event) => set('daysAhead', event.target.value)} /><em>days</em></span></label>}
    {rule.type === 'guidance_change' && <p className="alert-form-note">Fires when published guidance changes to Trim or Sell.</p>}
  </>
}

function destination(event) {
  if (!event.ticker) return '/alerts'
  return event.kind === 'pipeline_stale' ? '/' : `/search?q=${encodeURIComponent(event.ticker)}`
}

export default function Alerts() {
  const { currentUser } = useAuth()
  const alerts = useAlerts()
  const [draft, setDraft] = useState(initialRule)
  const [message, setMessage] = useState('')
  const [offerPush, setOfferPush] = useState(false)
  const [saving, setSaving] = useState(false)
  if (!currentUser) return <section className="report-empty-state"><span className="eyebrow">Alerts</span><h1>Sign in to create alerts</h1><p>In-app alerts are private to your account and sync across devices.</p></section>
  if (alerts.loading) return <Loading />

  const submit = async (event) => {
    event.preventDefault(); setSaving(true); setMessage('')
    try {
      const result = await alerts.createRule(draft)
      if (!result.success) setMessage(result.error)
      else {
        setMessage('Alert created. It will be evaluated after each research refresh.')
        setOfferPush(result.firstRule && pushCapability() !== 'unsupported')
        setDraft(initialRule())
      }
    } catch (reason) { setMessage(reason.message) }
    finally { setSaving(false) }
  }

  const enablePush = async () => {
    try {
      const result = await enablePushNotifications(currentUser.uid)
      setMessage(result.enabled ? 'Push notifications enabled.' : 'Push permission was declined. In-app alerts remain active.')
      setOfferPush(false)
    } catch (reason) { setMessage(reason.message) }
  }

  const quietEnabled = alerts.settings?.quietHoursEnabled !== false
  return <div className="alerts-page">
    <header className="page-head"><div><span className="eyebrow">Rules and events</span><h1 className="page-title">Alerts</h1><p className="page-sub">Every alert lands here. Push notifications are optional.</p></div>{alerts.unreadCount > 0 && <button className="secondary-button compact" onClick={alerts.markAllRead}>Mark all read</button>}</header>
    <p className="sr-only" aria-live="polite">{message}</p>
    {(message || alerts.error) && <div className={`alert-status ${alerts.error ? 'error' : ''}`} role={alerts.error ? 'alert' : 'status'}>{alerts.error || message}</div>}
    {offerPush && <section className="push-offer" aria-labelledby="push-offer-title"><Icon name="bell" size={28} /><div><h2 id="push-offer-title">Get alerts when ValueSignal is closed</h2><p>Your in-app alert is already active. Enable push only if you want device notifications too.</p></div><button className="primary-button" onClick={enablePush}>Enable push</button><button className="text-button" onClick={() => setOfferPush(false)}>Not now</button></section>}

    <div className="alerts-layout">
      <section className="alert-rule-builder" aria-labelledby="new-alert-title"><header><span className="eyebrow">New rule</span><h2 id="new-alert-title">Create an alert</h2><small>{alerts.rules.length} of {alertConfig.maximum_rules_per_user} rules used</small></header><form onSubmit={submit}>
        <label><span>Alert type</span><select value={draft.type} onChange={(event) => setDraft(normalizeAlertRule({ ...draft, type: event.target.value }))}>{ALERT_TYPES.map((type) => <option key={type.value} value={type.value}>{type.label}</option>)}</select></label>
        <RuleFields rule={draft} onChange={setDraft} />
        <button className="primary-button" disabled={saving || alerts.rules.length >= alertConfig.maximum_rules_per_user}>{saving ? 'Saving alert…' : 'Create alert'}</button>
      </form></section>

      <section className="alert-events" aria-labelledby="alert-events-title"><header><div><span className="eyebrow">Inbox</span><h2 id="alert-events-title">Recent events</h2></div><strong>{alerts.unreadCount} unread</strong></header>{alerts.events.length ? <div>{alerts.events.map((event) => <Link to={destination(event)} className={`alert-event ${event.readAt ? '' : 'unread'}`} key={event.id} onClick={() => alerts.markRead(event.id)}><span className="alert-event-icon"><Icon name="bell" /></span><span><strong>{event.title || 'Alert fired'}</strong><small>{event.message}</small><time>{String(event.createdAt || '').replace('T', ' ').slice(0, 16)}</time></span><Icon name="chevron" /></Link>)}</div> : <div className="alert-empty"><Icon name="bell" size={30} /><strong>No alert events yet</strong><p>Events appear here after a refresh crosses one of your saved rules.</p></div>}</section>
    </div>

    <section className="alert-rules" aria-labelledby="saved-alerts-title"><header><div><span className="eyebrow">Monitoring</span><h2 id="saved-alerts-title">Saved rules</h2></div></header>{alerts.rules.length ? <div>{alerts.rules.map((rule) => <article key={rule.id}><button className={`alert-rule-toggle ${rule.enabled ? 'active' : ''}`} aria-pressed={rule.enabled} aria-label={`${rule.enabled ? 'Disable' : 'Enable'} ${rule.label || alertRuleLabel(rule)}`} onClick={() => alerts.updateRule(rule.id, { enabled: !rule.enabled })}><span /></button><div><strong>{rule.label || alertRuleLabel(rule)}</strong><small>{rule.enabled ? 'Active after each refresh' : 'Paused'}</small></div><button className="icon-button" aria-label={`Delete ${rule.label || 'alert'}`} onClick={() => alerts.removeRule(rule.id)}><Icon name="close" /></button></article>)}</div> : <p>No saved rules. Create one above to begin monitoring.</p>}</section>

    <section className="alert-preferences" aria-labelledby="quiet-hours-title"><div><h2 id="quiet-hours-title">Quiet hours</h2><p>In-app events still arrive. Device push is suppressed during this window.</p></div><label className="switch"><input type="checkbox" checked={quietEnabled} onChange={(event) => alerts.updateSettings({ quietHoursEnabled: event.target.checked })} /><span aria-hidden="true" /></label><label><span>Start</span><input type="time" value={alerts.settings?.quietHoursStart || alertConfig.default_quiet_hours_start} onChange={(event) => alerts.updateSettings({ quietHoursStart: event.target.value })} /></label><label><span>End</span><input type="time" value={alerts.settings?.quietHoursEnd || alertConfig.default_quiet_hours_end} onChange={(event) => alerts.updateSettings({ quietHoursEnd: event.target.value })} /></label></section>
  </div>
}
