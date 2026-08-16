import { FeedItem, LeadFlag } from './FlagStates'
import { daysBetween, whenPhrase } from '../lib/format'

/* C1 — Today.
 *
 * One lead flag if there is a medication-linked one, then the rest of the week
 * in descending visual weight. The order is the outcome's weight, not
 * recency: a medication-linked flag from Friday outranks a quiet row from
 * Saturday, because the caregiver is skimming for the one that needs a
 * conversation.
 */
/* Descending visual weight, with the failed check last.
 *
 * It is the loudest object in the list, but it is loud because it is
 * unresolved, not because it is urgent — the backend gives it no push at all.
 * Putting it above a real finding would make the one thing that needs a
 * conversation harder to find, which is the failure mode this ordering exists
 * to avoid. */
const WEIGHT = {
  medication_linked: 0,
  unexplained_deviation: 1,
  within_expected: 2,
  insufficient_history: 3,
  query_failed: 4,
}

export default function Today({ data, onOpenFlag }) {
  const { person, flags } = data
  const lead = flags.find((f) => f.outcome === 'medication_linked') || null
  const rest = flags
    .filter((f) => f !== lead)
    .sort((a, b) => WEIGHT[a.outcome] - WEIGHT[b.outcome] || b.as_of.localeCompare(a.as_of))

  // A check is a snapshot of the day it ran, and the feed says so. A flag from
  // March under a "This week" heading would misdate it, and a check that could
  // not be evaluated is exactly the one you don't want to look more recent than
  // it is.
  const thisWeek = rest.filter((f) => daysBetween(f.as_of, person.today) <= 6)
  const earlier = rest.filter((f) => daysBetween(f.as_of, person.today) > 6)

  return (
    <>
      <header className="co-today__person">
        <span className="co-avatar" aria-hidden="true">{person.initials}</span>
        <span className="co-col">
          <h1 className="co-today__name">{person.called}</h1>
          <span className="co-today__last">
            Checked in {whenPhrase(person.last_checkin, person.today)},{' '}
            {person.last_checkin_time}
          </span>
        </span>
        <a className="co-today__call" href={`tel:${person.phone}`}>
          Call
        </a>
      </header>

      <div className="co-scroll co-stack co-cg__scroll" style={{ paddingTop: 8 }}>
        {lead && (
          <LeadFlag
            flag={lead}
            person={person}
            onSeeTimeline={onOpenFlag}
            onAddToDoctorList={data.addToDoctorList}
            onList={data.doctorList.items.includes(lead.tile_label)}
          />
        )}

        {thisWeek.length > 0 && (
          <section className="co-feed">
            <h2 className="co-eyebrow">This week</h2>
            {thisWeek.map((flag) => (
              <FeedItem
                key={flag.symptom}
                flag={flag}
                todayIso={person.today}
                onOpen={onOpenFlag}
                onRecheck={data.recheck}
              />
            ))}
          </section>
        )}

        {earlier.length > 0 && (
          <section className="co-feed">
            <h2 className="co-eyebrow">Earlier</h2>
            {earlier.map((flag) => (
              <FeedItem
                key={flag.symptom}
                flag={flag}
                todayIso={person.today}
                onOpen={onOpenFlag}
                onRecheck={data.recheck}
              />
            ))}
          </section>
        )}
      </div>
    </>
  )
}
