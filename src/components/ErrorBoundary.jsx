import { Component } from 'react'

// Without this, any render-time exception in a page (bad data shape, a null
// dereference, whatever) unmounts the whole app - rail, mobile nav, header,
// everything - leaving a blank screen with no way back except a manual reload.
export default class ErrorBoundary extends Component {
  state = { error: null }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    console.error('Unhandled render error:', error, info)
  }

  retry = () => {
    this.setState({ error: null })
    if (this.props.onRetry) this.props.onRetry()
    else window.location.reload()
  }

  render() {
    if (this.state.error) {
      const pageName = this.props.pageName || 'This page'
      const message = String(this.state.error?.message || '')
      const updatedApp = /chunk|dynamically imported|loading css|failed to fetch/i.test(message)
      return (
        <div className="route-error" role="alert">
          <span className="route-error-kicker">Page interrupted</span>
          <strong>{pageName} didn’t finish loading</strong>
          <p>{updatedApp
            ? 'The app may have updated while this tab was open. Reload to open the newest version.'
            : 'Your saved data is safe. Reload the page to reconnect and try this view again.'}</p>
          <div className="route-error-actions">
            <button className="primary-button" onClick={this.retry}>
              Reload page
            </button>
            <a className="secondary-button" href="/">Open financial report</a>
          </div>
          <small>If it happens again, check your connection and reopen this tab.</small>
        </div>
      )
    }
    return this.props.children
  }
}
