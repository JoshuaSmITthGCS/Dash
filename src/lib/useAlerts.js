import { useEffect, useMemo, useState } from 'react'
import { collection, deleteDoc, doc, onSnapshot, setDoc, updateDoc } from 'firebase/firestore'
import { db } from './firebase.js'
import { useAuth } from './FirebaseAuthContext.jsx'
import { alertConfig, alertRuleLabel, validateAlertRule } from './alertRules.js'

const byNewest = (left, right) => String(right.createdAt || '').localeCompare(String(left.createdAt || ''))

export function useAlerts() {
  const { currentUser } = useAuth()
  const [rules, setRules] = useState([])
  const [events, setEvents] = useState([])
  const [settings, setSettings] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!currentUser) {
      setRules([]); setEvents([]); setSettings(null); setLoading(false)
      return undefined
    }
    setLoading(true)
    const root = ['alerts', currentUser.uid]
    const stopRules = onSnapshot(collection(db, ...root, 'rules'), (snapshot) => {
      setRules(snapshot.docs.map((item) => ({ id: item.id, ...item.data() })).sort(byNewest))
      setLoading(false)
    }, (reason) => { setError(reason.message); setLoading(false) })
    const stopEvents = onSnapshot(collection(db, ...root, 'events'), (snapshot) => {
      setEvents(snapshot.docs.map((item) => ({ id: item.id, ...item.data() })).sort(byNewest))
    }, (reason) => setError(reason.message))
    const stopSettings = onSnapshot(doc(db, ...root, 'settings', 'preferences'), (snapshot) => {
      setSettings(snapshot.exists() ? snapshot.data() : null)
    }, (reason) => setError(reason.message))
    return () => { stopRules(); stopEvents(); stopSettings() }
  }, [currentUser])

  const createRule = async (input) => {
    if (!currentUser) return { success: false, error: 'Reconnect Firebase before creating an alert.' }
    if (rules.length >= alertConfig.maximum_rules_per_user) return { success: false, error: `You can create up to ${alertConfig.maximum_rules_per_user} alert rules.` }
    const checked = validateAlertRule(input)
    if (!checked.valid) return { success: false, error: checked.error }
    const createdAt = new Date().toISOString()
    const reference = doc(collection(db, 'alerts', currentUser.uid, 'rules'))
    const rule = { ...checked.rule, label: alertRuleLabel(checked.rule), createdAt, updatedAt: createdAt, lastState: null }
    await setDoc(reference, rule)
    return { success: true, id: reference.id, firstRule: rules.length === 0 }
  }

  const updateRule = async (id, patch) => {
    if (!currentUser) return { success: false, error: 'Reconnect Firebase before changing an alert.' }
    await updateDoc(doc(db, 'alerts', currentUser.uid, 'rules', id), { ...patch, updatedAt: new Date().toISOString() })
    return { success: true }
  }

  const removeRule = async (id) => {
    if (!currentUser) return
    await deleteDoc(doc(db, 'alerts', currentUser.uid, 'rules', id))
  }

  const markRead = async (id) => {
    if (!currentUser) return
    await updateDoc(doc(db, 'alerts', currentUser.uid, 'events', id), { readAt: new Date().toISOString() })
  }

  const markAllRead = async () => Promise.all(events.filter((event) => !event.readAt).map((event) => markRead(event.id)))

  const updateSettings = async (patch) => {
    if (!currentUser) return
    await setDoc(doc(db, 'alerts', currentUser.uid, 'settings', 'preferences'), {
      quietHoursEnabled: true,
      quietHoursStart: alertConfig.default_quiet_hours_start,
      quietHoursEnd: alertConfig.default_quiet_hours_end,
      timeZone: Intl.DateTimeFormat().resolvedOptions().timeZone,
      ...settings,
      ...patch,
      updatedAt: new Date().toISOString(),
    }, { merge: true })
  }

  const unreadCount = useMemo(() => events.filter((event) => !event.readAt).length, [events])
  return { rules, events, settings, loading, error, unreadCount, createRule, updateRule, removeRule, markRead, markAllRead, updateSettings }
}
