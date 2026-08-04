export const RETIREMENT_AGES = [30, 40, 45, 50, 60, 65]

const DATE_ONLY_PATTERN = /^(\d{4})-(\d{2})-(\d{2})$/

export function parseDateOnly(value) {
  const match = DATE_ONLY_PATTERN.exec(String(value || ''))
  if (!match) return null

  const year = Number(match[1])
  const month = Number(match[2])
  const day = Number(match[3])
  const date = new Date(year, month - 1, day)

  if (date.getFullYear() !== year || date.getMonth() !== month - 1 || date.getDate() !== day) return null
  return { year, month, day }
}

export function calculateAge(birthDate, today = new Date()) {
  const birth = parseDateOnly(birthDate)
  if (!birth || Number.isNaN(today.getTime())) return null

  let age = today.getFullYear() - birth.year
  const birthdayHasPassed = today.getMonth() + 1 > birth.month
    || (today.getMonth() + 1 === birth.month && today.getDate() >= birth.day)
  if (!birthdayHasPassed) age -= 1

  return age >= 0 && age <= 120 ? age : null
}

export function isValidBirthDate(value, today = new Date()) {
  return calculateAge(value, today) !== null
}
