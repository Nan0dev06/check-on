/* Date and copy formatting.
 *
 * Everything here is en-GB: "2 Aug", not "Aug 2". The medicines screen sets the
 * start date in mono at 26px, so these strings are load-bearing typography, not
 * incidental labels.
 */

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']

export function parse(iso) {
  if (!iso) return null
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(y, m - 1, d)
}

export function daysBetween(iso, todayIso) {
  const a = parse(iso)
  const b = todayIso ? parse(todayIso) : new Date()
  return Math.round((b - a) / 86400000)
}

/** "2 Aug" for this year, "Jan 2019" for anything older than a year. */
export function shortDate(iso, todayIso) {
  const d = parse(iso)
  if (!d) return ''
  if (daysBetween(iso, todayIso) > 365) return `${MONTHS[d.getMonth()]} ${d.getFullYear()}`
  return `${d.getDate()} ${MONTHS[d.getMonth()]}`
}

/** "2 AUG 2026" — the add-a-medicine start-date field. */
export function monoDate(iso) {
  const d = parse(iso)
  if (!d) return ''
  return `${d.getDate()} ${MONTHS[d.getMonth()].toUpperCase()} ${d.getFullYear()}`
}

/** "AUG 16" — chart axis ends. */
export function monoAxis(iso) {
  const d = parse(iso)
  if (!d) return ''
  return `${MONTHS[d.getMonth()].toUpperCase()} ${d.getDate()}`
}

export function weekday(iso) {
  const d = parse(iso)
  return d ? DAYS[d.getDay()] : ''
}

const LONG_DAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday',
  'Friday', 'Saturday']

/** "Tuesday" — for prose. The abbreviated form is for labels and timestamps. */
export function longWeekday(iso) {
  const d = parse(iso)
  return d ? LONG_DAYS[d.getDay()] : ''
}

/** "Tue" this week, "16 Mar" beyond it — a weekday alone stops meaning
 * anything once it is more than a week old. */
export function whenLabel(iso, todayIso) {
  const days = daysBetween(iso, todayIso)
  if (days <= 6) return weekday(iso)
  return shortDate(iso, todayIso)
}

/** Within the last week: "today" / "yesterday" / "Friday". Older: the date.
 * "2 days ago" is technically right and reads as filler; the day she actually
 * answered is what the caregiver is checking. */
export function whenPhrase(iso, todayIso) {
  const days = daysBetween(iso, todayIso)
  if (days === 0) return 'today'
  if (days === 1) return 'yesterday'
  if (days <= 6) return longWeekday(iso)
  return shortDate(iso, todayIso)
}

/** "13 days ago" / "5 months ago" / "" for anything over a year. */
export function ageLabel(iso, todayIso) {
  const days = daysBetween(iso, todayIso)
  if (days < 0) return 'starts in the future'
  if (days === 0) return 'today'
  if (days === 1) return 'yesterday'
  if (days < 60) return `${days} days ago`
  if (days < 365) return `${Math.round(days / 30)} months ago`
  return ''
}

/** The line under a medicine's start date. */
export function startedLabel(iso, todayIso) {
  const age = ageLabel(iso, todayIso)
  return age ? `started ${age}` : 'long-standing'
}

export function capitalise(s) {
  return s ? s[0].toUpperCase() + s.slice(1) : s
}
