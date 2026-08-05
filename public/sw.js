self.addEventListener('push', (event) => {
  let payload
  try { payload = event.data?.json() || {} } catch { payload = { title: 'ValueSignal alert', body: event.data?.text() || 'A portfolio alert fired.' } }
  event.waitUntil(self.registration.showNotification(payload.title || 'ValueSignal alert', {
    body: payload.body || 'Open ValueSignal to review the latest alert.',
    icon: '/icons/icon-192.png',
    badge: '/icons/favicon-32.png',
    tag: payload.tag || 'valuesignal-alerts',
    renotify: Boolean(payload.renotify),
    data: { url: payload.url || '/alerts' },
  }))
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const target = new URL(event.notification.data?.url || '/alerts', self.location.origin).href
  event.waitUntil(clients.matchAll({ type: 'window', includeUncontrolled: true }).then((windows) => {
    const existing = windows.find((client) => client.url.startsWith(self.location.origin))
    if (existing) return existing.focus().then(() => existing.navigate(target))
    return clients.openWindow(target)
  }))
})
