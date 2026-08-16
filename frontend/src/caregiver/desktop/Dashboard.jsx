import SharedTimeline from './SharedTimeline'
import { FeedItem } from '../FlagStates'
import { IconRaise, WordmarkUnderline } from '../../ui/Icons'
import { linkedHeadline, linkedBody } from '../../lib/copy'
import { whatsappLink } from '../../lib/format'

/* The caregiver dashboard at browser width.
 *
 * It replaces the four phone tabs outright rather than sitting beside them.
 * Medicines and Alerts get no desktop screen of their own on purpose: the
 * medication timeline is the lower half of the chart block and the flag feed is
 * the right rail. Splitting them back out would put the start dates on a
 * different surface from the curve, which is the one thing this layout exists
 * to prevent.
 */
const WEIGHT = {
  medication_linked: 0,
  unexplained_deviation: 1,
  within_expected: 2,
  insufficient_history: 3,
  query_failed: 4,
}

export default function Dashboard({ data, onOpenFlag, onAddMedicine }) {
  const { person, flags, medications, trend, notifications, doctorList } = data
  const hero = flags.find((f) => f.outcome === 'medication_linked') || null
  const onList = !!hero && doctorList.items.includes(hero.tile_label)
  const rail = flags
    .filter((f) => f !== hero)
    .sort((a, b) => WEIGHT[a.outcome] - WEIGHT[b.outcome])
  const nudges = notifications.low

  return (
    <main className="co-dash">
      <div className="co-dash__shell">
        <div className="co-dash__chrome" aria-hidden="true">
          <span className="co-dash__dot" />
          <span className="co-dash__dot" />
          <span className="co-dash__dot" />
          <span className="co-dash__url">checkon.app/{person.called.toLowerCase()}</span>
        </div>

        <div className="co-dash__content">
          <header className="co-dash__masthead">
            <div className="co-dash__brand">
              <p className="co-dash__wordmark">
                Check On<span className="co-dash__brandDot" />
              </p>
              <WordmarkUnderline />
            </div>
            <p className="co-hand co-dash__accent">
              you’re looking after {person.name}
            </p>
            <div className="co-dash__mastheadActions">
              <a
                className="co-btn co-btn--outline co-btn--pill"
                href={whatsappLink(person.phone)}
                target="_blank"
                rel="noopener noreferrer"
              >
                Call {person.called}
              </a>
              <button type="button" className="co-btn co-btn--primary co-btn--pill">
                Doctor list · {doctorList.items.length}
              </button>
            </div>
          </header>

          {hero && (
            <section className="co-dash__hero">
              <span className="co-dash__heroIcon">
                <IconRaise />
              </span>
              <div className="co-dash__heroBody">
                <p className="co-eyebrow co-dash__heroEyebrow">Worth asking the doctor</p>
                <h1 className="co-dash__heroTitle">{linkedHeadline(hero)}</h1>
                <p className="co-dash__heroText">{linkedBody(hero, person)}</p>
              </div>
              <div className="co-dash__heroActions">
                <button
                  type="button"
                  className="co-btn co-btn--primary"
                  onClick={() => data.addToDoctorList(hero)}
                  disabled={onList}
                >
                  {onList ? 'On the doctor list' : 'Add to doctor list'}
                </button>
                <button
                  type="button"
                  className="co-btn co-btn--outline"
                  onClick={() => onOpenFlag(hero)}
                >
                  See the taps
                </button>
              </div>
            </section>
          )}

          <div className="co-dash__grid">
            <section className="co-dash__timeline">
              <div className="co-dash__timelineHead">
                <h2 className="co-dash__timelineTitle">
                  How {person.called}’s been, and what she’s been taking
                </h2>
                <p className="co-hand co-dash__accent">same timeline, top to bottom</p>
                <div className="co-legend co-push">
                  <span className="co-legend__item">
                    <span className="co-legend__line" />
                    {person.called}
                  </span>
                  <span className="co-legend__item">
                    <span className="co-legend__band" />
                    Expected for her age
                  </span>
                </div>
              </div>

              <SharedTimeline
                trend={trend}
                medications={medications}
                person={person}
              />

              <div className="co-dash__reading">
                <p className="co-hand co-dash__readingLabel">what this says</p>
                <p className="co-dash__readingText">{readingText(data)}</p>
              </div>

              <button type="button" className="co-med__add" onClick={onAddMedicine}>
                Add a medicine
              </button>
            </section>

            <section className="co-dash__rail">
              <div className="co-dash__railHead">
                <h2 className="co-dash__railTitle">What she’s logged</h2>
                <span className="co-mono co-dash__railWhen">THIS WEEK</span>
              </div>

              {rail.map((flag) => (
                <FeedItem
                  key={flag.symptom}
                  flag={flag}
                  todayIso={person.today}
                  onOpen={onOpenFlag}
                  onRecheck={data.recheck}
                />
              ))}

              {nudges.length > 0 && (
                <div className="co-dash__nudges">
                  <h3 className="co-dash__nudgeTitle">
                    {nudges.length === 1 ? 'Quiet nudge' : 'Quiet nudges'}
                  </h3>
                  {nudges.map((n) => (
                    <p className="co-dash__nudge" key={n.id}>
                      <span className="co-dot" />
                      <span className="co-dash__nudgeText">{n.body || n.message}</span>
                    </p>
                  ))}
                </div>
              )}
            </section>
          </div>
        </div>
      </div>
    </main>
  )
}

/* One paragraph that says what moved, then immediately says what it does not
 * establish, then names where the line came from. All three clauses are load
 * bearing — the first without the second is a diagnosis. */
function readingText(data) {
  const { trend, medications, person } = data
  const recent = medications.active.find((m) => m.days_since_start <= 30)
  const outside = trend.series.at(-1).score > trend.band.high
  const when = recent
    ? new Date(recent.started).toLocaleDateString('en-GB', { day: 'numeric', month: 'long' })
    : null

  return (
    `${outside ? `${person.called} has drifted above the expected band over the last three weeks` : `${person.called} has stayed inside the expected band`}` +
    `${when ? `, and most of that movement sits to the right of ${when}` : ''}. ` +
    'That doesn’t tell us why — it’s the sort of thing worth mentioning at her ' +
    'next appointment, alongside this list. ' +
    trend.provenance
  )
}
