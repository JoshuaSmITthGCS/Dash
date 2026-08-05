import { collection, doc, setDoc } from 'firebase/firestore'
import { db } from './firebase.js'

function applicationServerKey(value) {
  const padding = '='.repeat((4 - value.length % 4) % 4)
  const base64 = (value + padding).replace(/-/g, '+').replace(/_/g, '/')
  const bytes = window.atob(base64)
  return Uint8Array.from(bytes, (character) => character.charCodeAt(0))
}

async function endpointId(endpoint) {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(endpoint))
  return [...new Uint8Array(digest)].map((value) => value.toString(16).padStart(2, '0')).join('')
}

export function pushCapability() {
  if (!('serviceWorker' in navigator) || !('PushManager' in window) || !('Notification' in window)) return 'unsupported'
  return Notification.permission
}

export async function enablePushNotifications(userId) {
  const publicKey = import.meta.env.VITE_VAPID_PUBLIC_KEY
  if (!publicKey) throw new Error('Push delivery is not configured for this deployment.')
  const permission = await Notification.requestPermission()
  if (permission !== 'granted') return { enabled: false, permission }
  const registration = await navigator.serviceWorker.ready
  const existing = await registration.pushManager.getSubscription()
  const subscription = existing || await registration.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: applicationServerKey(publicKey),
  })
  const payload = subscription.toJSON()
  const id = await endpointId(payload.endpoint)
  await setDoc(doc(collection(db, 'alerts', userId, 'subscriptions'), id), {
    ...payload,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    userAgent: navigator.userAgent,
  }, { merge: true })
  return { enabled: true, permission }
}
