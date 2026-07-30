export const number = new Intl.NumberFormat('en-US', { maximumFractionDigits: 1 })
export const integer = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 })
export const currency = new Intl.NumberFormat('en-US', {
  style: 'currency', currency: 'USD', maximumFractionDigits: 0,
})

export const money = (value, digits = 0) =>
  value == null || !Number.isFinite(Number(value))
    ? 'Unavailable'
    : Number(value).toLocaleString('en-US', {
      style: 'currency', currency: 'USD', minimumFractionDigits: digits, maximumFractionDigits: digits,
    })

export const signedPct = (value, digits = 1) =>
  value == null || !Number.isFinite(Number(value))
    ? 'Unavailable'
    : `${Number(value) >= 0 ? '+' : '−'}${Math.abs(Number(value)).toFixed(digits)}%`

export const ratio = (value, digits = 2) =>
  value == null || !Number.isFinite(Number(value)) ? 'Unavailable' : Number(value).toFixed(digits)

export const humanDate = (value) => {
  const date = new Date(value)
  if (!value || Number.isNaN(date.getTime())) return 'Unknown'
  return new Intl.DateTimeFormat('en-US', {
    month: 'short', day: 'numeric', year: date.getFullYear() !== new Date().getFullYear() ? 'numeric' : undefined,
    hour: 'numeric', minute: '2-digit',
  }).format(date)
}

export const compactCompany = (value = '') => value.replace(/\s+(Corporation|Incorporated)$/i, '')
