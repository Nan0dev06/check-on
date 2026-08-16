/* Display copy, composed from what the backend actually returned.
 *
 * DESIGN_SYSTEM.md §8 is a correctness constraint, not a tone preference:
 * "safe", "cleared", "no risk", "ruled out", "all clear", "normal", "fine" and
 * "healthy" are banned in every string this app renders, seed and placeholder
 * copy included. Absence of a signal is not absence of risk, and this file is
 * where that rule is easiest to break — so every sentence here is built from a
 * field the backend computed, and `npm run lint:copy` reads this file.
 *
 * The permitted vocabulary for a negative is: "no strong signal", "worth
 * watching", "within her usual pattern", "still learning the pattern",
 * "worth asking the doctor", "this is not a result".
 */
import { capitalise, daysBetween, longWeekday, parse, weekday, whenLabel } from './format'

const COUNT = ['no', 'one', 'two', 'three', 'four', 'five', 'six', 'seven',
  'eight', 'nine', 'ten']
const ORDINAL = ['', 'first', 'second', 'third', 'fourth', 'fifth', 'sixth',
  'seventh', 'eighth', 'ninth', 'tenth']

export const countWord = (n) => COUNT[n] ?? String(n)
export const ordinalWord = (n) => ORDINAL[n] ?? `${n}th`

/* Symptom labels come from the backend and mix number: "swollen ankles" is
 * plural, "dizziness" and "weakness" are not. Sentences that put one in subject
 * position have to agree, so the number is derived once here rather than each
 * sentence guessing. Trailing "ss" is the tell that separates "weakness" from
 * "ankles" across all six labels. */
/** "once" / "twice" / "four times" — "one time" is not how anyone says it. */
export const times = (n) =>
  n === 1 ? 'once' : n === 2 ? 'twice' : `${countWord(n)} times`

export const isPlural = (label) => /s$/.test(label) && !/ss$/.test(label)
const verb = (label, plural, singular) => (isPlural(label) ? plural : singular)
const pronoun = (label) => (isPlural(label) ? 'them' : 'it')

/** The FAERS finding that cleared the Evans criteria, if there was one. */
export function signalFinding(flag) {
  return (flag.drug_findings || []).find((f) => f.status === 'signal') || null
}

/** Taps of this symptom on or after the implicated medicine's start date. */
export function tapsSinceMedicine(flag, startedIso) {
  if (!startedIso) return []
  return (flag.taps || []).filter((t) => parse(t) >= parse(startedIso))
}

/** Days between the medicine starting and the first tap that followed it. */
export function onsetGap(flag, startedIso) {
  const after = tapsSinceMedicine(flag, startedIso)
  if (!after.length) return null
  return daysBetween(startedIso, after[0])
}

function implicated(flag) {
  const signal = signalFinding(flag)
  if (!signal) return null
  const med = (flag.recent_medications || []).find((m) => m.name === signal.drug)
  return { drug: signal.drug, started: med?.started || null, finding: signal }
}

/* --- the lead MEDICATION_LINKED card ------------------------------------ */

export function linkedHeadline(flag) {
  const link = implicated(flag)
  if (!link) return capitalise(flag.symptom_label) + ' was logged.'
  const gap = onsetGap(flag, link.started)
  const drug = link.drug.toLowerCase()
  if (gap == null) return `${capitalise(flag.symptom_label)} lines up with ${drug}.`
  return `${capitalise(flag.symptom_label)} started ${gap} ${gap === 1 ? 'day' : 'days'} after ${drug}.`
}

export function linkedBody(flag, person) {
  const link = implicated(flag)
  const her = person?.called === 'Mum' ? 'She' : person?.name || 'She'
  if (!link) return flag.notification.message
  const after = tapsSinceMedicine(flag, link.started)
  const since = after.length ? longWeekday(after[0]) : null
  const tile = flag.tile_label.toLowerCase()
  const drug = link.drug.toLowerCase()

  const first = after.length
    ? `${her}’s tapped “${tile}” ${countWord(after.length)} ${after.length === 1 ? 'time' : 'times'}${since ? ` since ${since}` : ''}.`
    : ''
  // "one of the most commonly reported" is what clearing the Evans criteria
  // means, and it is the strongest claim the data supports. Not "caused by".
  // The drug is the subject so the sentence agrees whichever symptom it is.
  const second = `${capitalise(drug)} has ${flag.symptom_label} among its most commonly reported effects, and this timing lines up.`
  const third = 'Before anyone treats it as something new, it’s worth raising the medicine.'
  return [first, second, third].filter(Boolean).join(' ')
}

/** The compact one-liner used in the feed and the desktop rail. */
export function linkedLine(flag) {
  const link = implicated(flag)
  if (!link) return flag.notification.message
  const after = tapsSinceMedicine(flag, link.started)
  const since = after.length ? weekday(after[0]) : null
  return `${flag.tile_label} — ${ordinalWord(after.length)} tap${since ? ` since ${since}` : ''}, and it follows a new medicine.`
}

/* --- the four quieter states -------------------------------------------- */

export function deviationLine(flag) {
  return `${flag.tile_label} — above her own usual pattern. No medicine change lines up with it.`
}

export function withinLine(flag, todayIso) {
  return `${flag.tile_label}, ${whenLabel(flag.as_of, todayIso)} — within her usual pattern, no strong signal`
}

export function learningLine(flag, todayIso) {
  // The rule is two check-ins, and she answers weekly — so what is missing is
  // one more weekly answer, stated as that rather than as a vague "more data".
  return `${flag.tile_label}, ${whenLabel(flag.as_of, todayIso)} — one more weekly answer is needed before this check means much.`
}

export function failedLine(flag, todayIso) {
  return `${flag.tile_label}, ${whenLabel(flag.as_of, todayIso)} — we couldn’t reach the medicine database. This is not a result. Nothing has been checked yet.`
}

export const STATE_HEADING = {
  medication_linked: 'Worth asking the doctor',
  unexplained_deviation: 'Worth watching',
  insufficient_history: 'Still learning her pattern',
  query_failed: 'The check didn’t run',
}

export function stateLine(flag, todayIso) {
  switch (flag.outcome) {
    case 'medication_linked':
      return linkedLine(flag)
    case 'unexplained_deviation':
      return deviationLine(flag)
    case 'within_expected':
      return withinLine(flag, todayIso)
    case 'insufficient_history':
      return learningLine(flag, todayIso)
    case 'query_failed':
      return failedLine(flag, todayIso)
    default:
      return flag.notification.message
  }
}

/* --- flag detail (C6) ---------------------------------------------------- */

export function detailHeadline(flag) {
  if (flag.outcome !== 'medication_linked') {
    return `${capitalise(flag.symptom_label)}, and what the check found.`
  }
  return `${capitalise(flag.symptom_label)}, and a medicine that’s known to cause ${pronoun(flag.symptom_label)}.`
}

/* --- alerts (C4) ---------------------------------------------------------
 * The alert card needs a headline and a body that say different things. The
 * backend's notification message is one sentence carrying both, so using it
 * twice prints the same text in two sizes. */

export function alertHeadline(flag) {
  if (flag.outcome === 'medication_linked') return linkedHeadline(flag)
  return `${capitalise(flag.symptom_label)} ${verb(flag.symptom_label, 'sit', 'sits')} above her own usual pattern.`
}

export function alertBody(flag) {
  const link = implicated(flag)
  if (flag.outcome === 'medication_linked' && link) {
    const after = tapsSinceMedicine(flag, link.started)
    const since = after.length ? longWeekday(after[0]) : null
    return (
      `${capitalise(countWord(after.length))} tap${after.length === 1 ? '' : 's'}` +
      `${since ? ` since ${since}` : ''}, ${link.finding.days_since_change} days after ` +
      `${link.drug.toLowerCase()} started. Worth asking her doctor before it’s ` +
      `treated as something new.`
    )
  }
  return (
    'Her recent weekly answers have moved above the range expected for her age, ' +
    'and no medicine change lines up with it. Worth mentioning at her next ' +
    'appointment.'
  )
}

export function detailBody(flag, person) {
  const link = implicated(flag)
  const who = person?.called || 'She'
  if (!link) return flag.reasoning
  const after = tapsSinceMedicine(flag, link.started)
  const since = after.length ? longWeekday(after[0]) : null
  const gap = onsetGap(flag, link.started)
  return (
    `${who} has tapped “${flag.tile_label.toLowerCase()}” ${countWord(after.length)} ` +
    `${after.length === 1 ? 'time' : 'times'}${since ? ` since ${since}` : ''}. ` +
    `${capitalise(link.drug)} started ${shortWhen(link.started)}, ` +
    `${countWord(gap)} ${gap === 1 ? 'day' : 'days'} before the first tap. ` +
    `This is one of the most commonly reported effects of that medicine.`
  )
}

function shortWhen(iso) {
  const d = parse(iso)
  const months = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
    'August', 'September', 'October', 'November', 'December']
  return `${d.getDate()} ${months[d.getMonth()]}`
}

/** The three numbered reasons on C6, each built from a real figure. */
export function whyReasons(flag, medications) {
  const link = implicated(flag)
  if (!link) return []
  const after = tapsSinceMedicine(flag, link.started)
  const before = (flag.taps || []).filter((t) => parse(t) < parse(link.started))
  const span = after.length
    ? daysBetween(after[0], after[after.length - 1]) + 1
    : 0

  const others = (medications || []).filter(
    (m) => m.name !== link.drug && Math.abs(daysBetween(m.started, link.started)) <= 30,
  )

  return [
    `The interaction data reports ${flag.symptom_label} for ${link.drug.toLowerCase()} ` +
      `${link.finding.prr.toFixed(1)} times more often than for other medicines, ` +
      `across ${link.finding.cases.toLocaleString()} reports. Not a borderline signal.`,
    before.length
      ? `She logged it ${times(before.length)} before ${shortWhen(link.started)}, ` +
        `and ${times(after.length)} in the ${span} days after.`
      : `Every tap of this symptom has come after ${shortWhen(link.started)}.`,
    others.length
      ? `${others.map((m) => m.name).join(' and ')} also started near this date, so this ` +
        `medicine is not the only candidate.`
      : 'Nothing else on her list started near this date.',
  ]
}

/** The line to take to the appointment. Newsreader, quoted, one sentence. */
export function quotableLine(flag) {
  const link = implicated(flag)
  if (!link) return null
  const after = tapsSinceMedicine(flag, link.started)
  if (!after.length) return null
  const d = parse(after[0])
  return (
    `“She started ${link.drug.toLowerCase()} on ${shortWhen(link.started)} and her ` +
    `${flag.symptom_label} have been happening since around the ${ordinalDay(d.getDate())}. ` +
    `Could the two be connected?”`
  )
}

function ordinalDay(n) {
  const s = ['th', 'st', 'nd', 'rd']
  const v = n % 100
  return n + (s[(v - 20) % 10] || s[v] || s[0])
}

export const NOT_A_DIAGNOSIS =
  'This is a signal in the data, not a diagnosis, and Check On can’t tell you ' +
  'whether the medicine should change. That’s a conversation for her doctor.'
