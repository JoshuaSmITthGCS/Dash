// 2026 IRS annual contribution limits (IRS Notice 2025-67, irs.gov/newsroom/401k-limit-increases-to-24500-for-2026-ira-limit-increases-to-7500).
const LIMITS_2026 = {
  '401k': { base: 24500, catchUp5059: 8000, catchUp6063: 11250 },
  ira: { base: 7500, catchUp50: 1100 },
  hsa_self: { base: 4400, catchUp55: 1000 },
  hsa_family: { base: 8750, catchUp55: 1000 },
}

export const ACCOUNT_TYPES = [
  { key: '401k', label: '401(k) / 403(b)' },
  { key: 'roth_ira', label: 'Roth IRA' },
  { key: 'traditional_ira', label: 'Traditional IRA' },
  { key: 'hsa_self', label: 'HSA (self-only)' },
  { key: 'hsa_family', label: 'HSA (family)' },
  { key: 'personal', label: 'Personal / taxable investing' },
]

/** The 2026 IRS annual contribution limit for an account type, given the holder's age (for catch-up eligibility). Returns null for account types with no IRS cap. */
export function getAnnualLimit(type, age = 0) {
  switch (type) {
    case '401k':
      if (age >= 60 && age <= 63) return LIMITS_2026['401k'].base + LIMITS_2026['401k'].catchUp6063
      if (age >= 50) return LIMITS_2026['401k'].base + LIMITS_2026['401k'].catchUp5059
      return LIMITS_2026['401k'].base
    case 'roth_ira':
    case 'traditional_ira':
      return age >= 50 ? LIMITS_2026.ira.base + LIMITS_2026.ira.catchUp50 : LIMITS_2026.ira.base
    case 'hsa_self':
      return age >= 55 ? LIMITS_2026.hsa_self.base + LIMITS_2026.hsa_self.catchUp55 : LIMITS_2026.hsa_self.base
    case 'hsa_family':
      return age >= 55 ? LIMITS_2026.hsa_family.base + LIMITS_2026.hsa_family.catchUp55 : LIMITS_2026.hsa_family.base
    case 'personal':
    default:
      return null
  }
}

export function accountTypeLabel(type) {
  return ACCOUNT_TYPES.find((item) => item.key === type)?.label || type
}
