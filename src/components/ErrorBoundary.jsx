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

  render() {
    if (this.state.error) {
      return (
        <div className="route-error" role="alert">
          <strong>Something went wrong loading this page.</strong>
          <p>Try again, or head back to the report.</p>
          <div className="route-error-actions">
            <button className="secondary-button" onClick={() => this.setState({ error: null })}>
              Try again
            </button>
            <a className="secondary-button" href="/">Back to report</a>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
