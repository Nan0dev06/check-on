import { shortDate, startedLabel, capitalise } from '../lib/format'
import { countWord } from '../lib/copy'

/* C2 — Medicines.
 *
 * The most important data in the app, and the start date carries the visual
 * weight: mono, 26px, ink on the medicine a flag points at. The interaction
 * check is a question about timing, so a list that buried the dates would make
 * the rest of the product unreadable.
 */
export default function Medicines({ data, onAdd }) {
  const { person, medications, flags } = data
  const active = medications.active
  const newest = active[0]

  return (
    <>
      <header className="co-cg__header">
        <h1 className="co-cg__title">{person.called}’s medicines</h1>
        <p className="co-cg__sub">Newest first — start dates matter most</p>
      </header>

      <div className="co-scroll co-stack co-cg__scroll co-meds">
        {active.map((med) => (
          <Medicine
            key={med.id}
            med={med}
            today={person.today}
            flagged={med.id === newest?.id}
            note={noteFor(med, flags)}
          />
        ))}

        {medications.stopped.length > 0 && (
          <section className="co-med co-med--stopped">
            <h2 className="co-eyebrow">Stopped</h2>
            {medications.stopped.map((med) => (
              <p className="co-med__name-row" key={med.id}>
                <span className="co-med__struck">{med.name}</span>
                <span className="co-med__age">
                  stopped {shortDate(med.stopped, person.today)}
                </span>
              </p>
            ))}
          </section>
        )}

        <button type="button" className="co-med__add" onClick={onAdd}>
          Add a medicine
        </button>
      </div>
    </>
  )
}

function Medicine({ med, today, flagged, note }) {
  return (
    <article className={`co-med${flagged ? ' co-med--flagged' : ''}`}>
      <h2 className="co-med__name-row">
        <span className="co-med__name">{med.name}</span>
        <span className="co-med__dose">
          {[med.dose_value && `${med.dose_value} ${med.dose_unit}`,
            med.frequency?.toLowerCase()].filter(Boolean).join(', ')}
        </span>
      </h2>
      <p className="co-med__date-row">
        <span className="co-med__date">{shortDate(med.started, today)}</span>
        <span className="co-med__age">{startedLabel(med.started, today)}</span>
      </p>
      {note && (
        <>
          <hr className="co-rule" />
          <p className="co-med__note">{note}</p>
        </>
      )}
    </article>
  )
}

/* What this medicine has been implicated in, counted from real flags. Silent
 * when there is nothing — an empty reassurance would be the worst line on the
 * screen. */
function noteFor(med, flags) {
  const linked = flags.filter(
    (f) =>
      f.outcome === 'medication_linked' &&
      (f.drug_findings || []).some(
        (d) => d.status === 'signal' && d.drug.toLowerCase() === med.name.toLowerCase(),
      ),
  )
  if (!linked.length) return null
  const f = linked[0]
  const taps = (f.taps || []).filter((t) => t >= med.started)
  return (
    `${capitalise(countWord(linked.length))} ${linked.length === 1 ? 'flag' : 'flags'} ` +
    `since this started — ${f.tile_label.toLowerCase()}, ${countWord(taps.length)} ` +
    `${taps.length === 1 ? 'tap' : 'taps'}. Worth watching.`
  )
}
