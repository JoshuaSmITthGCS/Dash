import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App.jsx'
import './styles/index.css'
import { PreferencesProvider } from './lib/PreferencesContext.jsx'
import './lib/hudEffects.js'
import { initAdvancedHUD } from './lib/hudAdvanced.jsx'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <PreferencesProvider>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </PreferencesProvider>
  </React.StrictMode>
)

// Initialize advanced HUD effects
setTimeout(() => initAdvancedHUD(), 100)

if ('serviceWorker' in navigator && import.meta.env.PROD) {
  window.addEventListener('load', () => navigator.serviceWorker.register('/sw.js'))
}
