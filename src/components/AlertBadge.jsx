import { NavLink } from 'react-router-dom'
import Icon from './Icons.jsx'
import { useAlerts } from '../lib/useAlerts.js'

export default function AlertBadge({ className = 'icon-button' }) {
  const { unreadCount } = useAlerts()
  return <NavLink className={`${className} alert-badge-button`} to="/alerts" aria-label={`Alerts${unreadCount ? `, ${unreadCount} unread` : ''}`}>
    <Icon name="bell" />
    {unreadCount > 0 && <span className="alert-unread-badge" aria-hidden="true">{unreadCount > 99 ? '99+' : unreadCount}</span>}
  </NavLink>
}
