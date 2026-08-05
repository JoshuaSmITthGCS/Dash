import webpush from 'web-push'
import { cert, getApps, initializeApp } from 'firebase-admin/app'
import { getFirestore } from 'firebase-admin/firestore'

const json = (statusCode, body) => ({ statusCode, headers: { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' }, body: JSON.stringify(body) })

function firebaseApp() {
  if (getApps().length) return getApps()[0]
  const raw = process.env.FIREBASE_SERVICE_ACCOUNT_JSON
  if (!raw) throw new Error('FIREBASE_SERVICE_ACCOUNT_JSON is not configured')
  return initializeApp({ credential: cert(JSON.parse(raw)) })
}

function timeParts(now, timeZone) {
  let formatter
  try { formatter = new Intl.DateTimeFormat('en-CA', { timeZone, hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }) }
  catch { formatter = new Intl.DateTimeFormat('en-CA', { timeZone: 'UTC', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }) }
  const parts = formatter.formatToParts(now)
  const value = Object.fromEntries(parts.map((part) => [part.type, part.value]))
  return Number(value.hour) * 60 + Number(value.minute)
}

const minutes = (value) => {
  const [hour, minute] = String(value || '').split(':').map(Number)
  return Number.isFinite(hour) && Number.isFinite(minute) ? hour * 60 + minute : null
}

export function isQuietTime(settings = {}, now = new Date()) {
  if (settings.quietHoursEnabled === false) return false
  const start = minutes(settings.quietHoursStart || '22:00')
  const end = minutes(settings.quietHoursEnd || '07:00')
  if (start == null || end == null || start === end) return false
  const current = timeParts(now, settings.timeZone || 'America/New_York')
  return start < end ? current >= start && current < end : current >= start || current < end
}

export function buildPushPayload(events = []) {
  const first = events[0] || {}
  if (events.length === 1) return { title: first.title || 'ValueSignal alert', body: first.message || 'One alert fired.', url: first.url || '/alerts', tag: `valuesignal-${first.id || 'alert'}` }
  return { title: `${events.length} ValueSignal alerts`, body: events.slice(0, 3).map((event) => event.title || event.message).join(' · '), url: '/alerts', tag: 'valuesignal-grouped-alerts', renotify: true }
}

async function deliverForUser(db, delivery) {
  const userRoot = db.collection('alerts').doc(delivery.uid)
  const [settingsSnapshot, subscriptionsSnapshot] = await Promise.all([
    userRoot.collection('settings').doc('preferences').get(),
    userRoot.collection('subscriptions').get(),
  ])
  if (isQuietTime(settingsSnapshot.data() || {})) return { uid: delivery.uid, delivered: 0, quiet: true }
  const subscriptions = subscriptionsSnapshot.docs.map((item) => ({ id: item.id, ...item.data() }))
  if (!subscriptions.length) return { uid: delivery.uid, delivered: 0, quiet: false }
  const payload = JSON.stringify(buildPushPayload(delivery.events))
  let delivered = 0
  await Promise.all(subscriptions.map(async (subscription) => {
    try {
      await webpush.sendNotification({ endpoint: subscription.endpoint, keys: subscription.keys }, payload)
      delivered += 1
    } catch (error) {
      if ([404, 410].includes(error.statusCode)) await userRoot.collection('subscriptions').doc(subscription.id).delete()
      else throw error
    }
  }))
  if (delivered) {
    const batch = db.batch()
    delivery.events.forEach((event) => batch.set(userRoot.collection('events').doc(event.id), { pushedAt: new Date().toISOString() }, { merge: true }))
    await batch.commit()
  }
  return { uid: delivery.uid, delivered, quiet: false }
}

export async function handler(event) {
  if (event.httpMethod !== 'POST') return json(405, { error: 'Method not allowed.' })
  const deliverySecret = event.headers?.['x-alert-delivery-secret'] || event.headers?.['X-Alert-Delivery-Secret']
  if (!process.env.ALERT_DELIVERY_SECRET || deliverySecret !== process.env.ALERT_DELIVERY_SECRET) return json(401, { error: 'Unauthorized.' })
  if (!process.env.VAPID_PUBLIC_KEY || !process.env.VAPID_PRIVATE_KEY || !process.env.VAPID_SUBJECT) return json(503, { error: 'Web Push is not configured.' })
  let body
  try { body = JSON.parse(event.body || '{}') } catch { return json(400, { error: 'Invalid JSON.' }) }
  const deliveries = Array.isArray(body.deliveries) ? body.deliveries.filter((item) => item?.uid && Array.isArray(item.events) && item.events.length).slice(0, 100) : []
  if (!deliveries.length) return json(200, { delivered: 0, users: [] })
  try {
    webpush.setVapidDetails(process.env.VAPID_SUBJECT, process.env.VAPID_PUBLIC_KEY, process.env.VAPID_PRIVATE_KEY)
    const db = getFirestore(firebaseApp())
    const users = []
    for (const delivery of deliveries) users.push(await deliverForUser(db, delivery))
    return json(200, { delivered: users.reduce((sum, item) => sum + item.delivered, 0), users })
  } catch (error) {
    console.error('Alert push delivery failed:', error)
    return json(500, { error: 'Alert push delivery failed.' })
  }
}
