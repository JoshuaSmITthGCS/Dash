import { useState } from 'react'

export default function CompanyLogo({ company, size = 42, className = '' }) {
  const [failed, setFailed] = useState(false)
  const ticker = String(company?.ticker || '').toUpperCase()
  const logo = company?.logo_url || company?.logo || company?.image
  if (logo && !failed) return <img className={`company-logo ${className}`} src={logo} width={size} height={size} loading="lazy" alt={`${company?.name || ticker} logo`} onError={() => setFailed(true)} />
  return <span className={`company-logo-fallback ${className}`} style={{ width: size, height: size }} role="img" aria-label={`${company?.name || ticker || 'Company'} logo unavailable`}>{ticker.slice(0, 2) || '?'}</span>
}
