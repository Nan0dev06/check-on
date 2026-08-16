import { useState } from 'react'
import {
  IconFailed,
  IconLearning,
  IconRise,
  IconWatch,
} from '../ui/Icons'
import { STATE_HEADING, linkedBody, linkedHeadline, stateLine } from '../lib/copy'
import { whenLabel } from '../lib/format'

/* The five outcome states, §7.
 *
 * These are the only components that render an outcome, so the treatment table
 * is enforced in one place: solid border and two buttons for MEDICATION_LINKED,
 * a plain border for UNEXPLAINED_DEVIATION, no card at all for WITHIN_EXPECTED,
 * a dashed border for INSUFFICIENT_HISTORY, and an inverted diagonal stripe for
 * QUERY_FAILED. Framing carries the meaning; two states never differ by colour
 * alone.
 *
 * The same components serve the phone feed and the desktop rail. Building a
 * second set at desktop scale is how the two drift apart.
 */

export function FeedItem({ flag, todayIso, onOpen, onRecheck }) {
  switch (flag.outcome) {
    case 'medication_linked':
      return <LinkedRow flag={flag} todayIso={todayIso} onOpen={onOpen} />
    case 'unexplained_deviation':
      return <DeviationRow flag={flag} todayIso={todayIso} />
    case 'within_expected':
      return <WithinRow flag={flag} todayIso={todayIso} />
    case 'insufficient_history':
      return <LearningRow flag={flag} todayIso={todayIso} />
    case 'query_failed':
      return <FailedRow flag={flag} todayIso={todayIso} onRecheck={onRecheck} />
    default:
      return null
  }
}

/* --- MEDICATION_LINKED --------------------------------------------------- */

/** The lead card: eyebrow bar, headline, reasoning, two actions. */
export function LeadFlag({ flag, person, onSeeTimeline, onAddToDoctorList, onList }) {
  const [pending, setPending] = useState(false)
  const added = onList || pending

  // Optimistic while the write is in flight, then the server's answer takes
  // over — a failed add must not leave the button claiming it succeeded.
  async function add() {
    setPending(true)
    const ok = await onAddToDoctorList?.(flag)
    if (!ok) setPending(false)
  }

  return (
    <article className="co-lead">
      <h2 className="co-lead__bar">{STATE_HEADING.medication_linked}</h2>
      <div className="co-lead__body">
        <p className="co-lead__title">{linkedHeadline(flag)}</p>
        <p className="co-lead__text">{linkedBody(flag, person)}</p>
        <div className="co-lead__actions">
          <button
            type="button"
            className="co-btn co-btn--primary co-btn--grow"
            onClick={add}
            disabled={added}
          >
            {added ? 'On the doctor list' : 'Add to doctor list'}
          </button>
          <button
            type="button"
            className="co-btn co-btn--secondary co-btn--grow"
            onClick={() => onSeeTimeline?.(flag)}
          >
            See timeline
          </button>
        </div>
      </div>
    </article>
  )
}

function LinkedRow({ flag, todayIso, onOpen }) {
  return (
    <button
      type="button"
      className="co-state co-state--linked"
      onClick={() => onOpen?.(flag)}
    >
      <span className="co-state__head">
        <IconRise />
        <span className="co-state__label">{STATE_HEADING.medication_linked}</span>
        <span className="co-state__when">{whenLabel(flag.as_of, todayIso)}</span>
      </span>
      <span className="co-state__text">{stateLine(flag, todayIso)}</span>
    </button>
  )
}

/* --- UNEXPLAINED_DEVIATION ----------------------------------------------- */

function DeviationRow({ flag, todayIso }) {
  return (
    <article className="co-state">
      <div className="co-state__head">
        <IconWatch />
        <h3 className="co-state__label">{STATE_HEADING.unexplained_deviation}</h3>
        <span className="co-state__when">{whenLabel(flag.as_of, todayIso)}</span>
      </div>
      <p className="co-state__text">{stateLine(flag, todayIso)}</p>
    </article>
  )
}

/* --- WITHIN_EXPECTED — no card at all ------------------------------------ */

function WithinRow({ flag, todayIso }) {
  return (
    <p className="co-quiet">
      <span className="co-dot" />
      <span className="co-quiet__text">{stateLine(flag, todayIso)}</span>
    </p>
  )
}

/* --- INSUFFICIENT_HISTORY — neither good nor bad ------------------------- */

function LearningRow({ flag, todayIso }) {
  return (
    <article className="co-state co-state--learning">
      <div className="co-state__head">
        <IconLearning />
        <h3 className="co-state__label">{STATE_HEADING.insufficient_history}</h3>
        <span className="co-state__when">{whenLabel(flag.as_of, todayIso)}</span>
      </div>
      <p className="co-state__text">{stateLine(flag, todayIso)}</p>
    </article>
  )
}

/* --- QUERY_FAILED — inverted, and it stays inverted ---------------------- */

function FailedRow({ flag, todayIso, onRecheck }) {
  const [running, setRunning] = useState(false)

  async function retry() {
    setRunning(true)
    try {
      await onRecheck?.(flag)
    } finally {
      // If it failed again the card stays exactly as it is. A failed check must
      // never decay into a quiet or settled-looking state.
      setRunning(false)
    }
  }

  return (
    <article className="co-failed co-on-ink">
      <div className="co-failed__head">
        <IconFailed />
        <h3 className="co-failed__label">{STATE_HEADING.query_failed}</h3>
        <span className="co-failed__when">{whenLabel(flag.as_of, todayIso)}</span>
      </div>
      <p className="co-failed__text">{stateLine(flag, todayIso)}</p>
      <button
        type="button"
        className="co-failed__retry"
        onClick={retry}
        disabled={running}
        aria-busy={running}
      >
        {running ? 'Running the check…' : 'Run the check again'}
      </button>
    </article>
  )
}
