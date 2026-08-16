import { useState } from 'react'
import TapChart from '../charts/TapChart'
import Sheet from './Sheet'
import { IconChevronLeft } from '../ui/Icons'
import {
  NOT_A_DIAGNOSIS,
  STATE_HEADING,
  detailBody,
  detailHeadline,
  quotableLine,
  signalFinding,
  stateLine,
  whyReasons,
} from '../lib/copy'

/* C6 — Flag detail.
 *
 * One screen serves all three deep links: "See timeline" from Today, "Open the
 * flag" from Alerts, and "See the taps" from the dashboard. There are no
 * variants.
 *
 * "What this isn't" is not a disclaimer bolted on the end — it is the section
 * that keeps the rest of the screen honest, so it sits above the quotable line
 * rather than below the fold.
 */
export default function FlagDetail({ symptom, data, onBack, asModal }) {
  const { person, flags, medications, doctorList } = data
  const flag = flags.find((f) => f.symptom === symptom)
  const [pending, setPending] = useState(false)
  const added = pending || (!!flag && doctorList.items.includes(flag.tile_label))

  if (!flag) {
    return (
      <Sheet asModal={asModal} onClose={onBack} label="Flag">
        <Bar onBack={onBack} />
        <div className="co-detail">
          <p className="co-detail__body">
            That check isn’t in the list any more. Nothing has been concluded
            about it.
          </p>
        </div>
      </Sheet>
    )
  }

  const signal = signalFinding(flag)
  const medication = signal
    ? medications.active.find(
        (m) => m.name.toLowerCase() === signal.drug.toLowerCase(),
      )
    : null
  const reasons = whyReasons(flag, medications.active)
  const quote = quotableLine(flag)

  return (
    <Sheet asModal={asModal} onClose={onBack} label={STATE_HEADING[flag.outcome]}>
      <Bar onBack={onBack} />

      <div className="co-scroll co-stack co-detail">
        <header className="co-detail__head">
          <p className="co-pill">{STATE_HEADING[flag.outcome] || 'What the check found'}</p>
          <h1 className="co-detail__title">{detailHeadline(flag)}</h1>
          <p className="co-detail__body">
            {signal ? detailBody(flag, person) : stateLine(flag, person.today)}
          </p>
        </header>

        {medication && (
          <section className="co-tapchart">
            <h2 className="co-eyebrow">Every tap, against the medicine</h2>
            <TapChart flag={flag} medication={medication} todayIso={person.today} />
            <div className="co-legend">
              <span className="co-legend__item">
                <span className="co-dot" style={{ background: 'var(--ink)', width: 9, height: 9 }} />
                Tapped {flag.tile_label.toLowerCase()}
              </span>
              <span className="co-legend__item">
                <span
                  className="co-dot"
                  style={{
                    background: 'transparent',
                    border: '2px solid var(--rule-strong)',
                    width: 9,
                    height: 9,
                  }}
                />
                Before the medicine
              </span>
            </div>
          </section>
        )}

        {reasons.length > 0 && (
          <section className="co-why">
            <h2 className="co-eyebrow">Why this was flagged</h2>
            {reasons.map((text, i) => (
              <p className="co-why__row" key={text}>
                <span className="co-why__n">{String(i + 1).padStart(2, '0')}</span>
                <span className="co-why__text">{text}</span>
              </p>
            ))}
          </section>
        )}

        <section className="co-isnt">
          <h2 className="co-isnt__title">What this isn’t</h2>
          <p className="co-isnt__text">{NOT_A_DIAGNOSIS}</p>
        </section>

        {flag.caveats?.length > 0 && (
          <section className="co-why">
            <h2 className="co-eyebrow">Worth knowing</h2>
            {flag.caveats.map((c) => (
              <p className="co-why__row" key={c}>
                <span className="co-why__text">{c}</span>
              </p>
            ))}
          </section>
        )}

        {quote && (
          <section className="co-field">
            <h2 className="co-eyebrow">Take to the appointment</h2>
            <p className="co-quotebox">{quote}</p>
          </section>
        )}
      </div>

      <div className="co-stickyfoot">
        <button
          type="button"
          className="co-btn co-btn--primary co-btn--grow co-btn--lg"
          onClick={async () => {
            setPending(true)
            if (!(await data.addToDoctorList(flag))) setPending(false)
          }}
          disabled={added}
        >
          {added ? 'On the doctor list' : 'Add to doctor list'}
        </button>
      </div>
    </Sheet>
  )
}

function Bar({ onBack }) {
  return (
    <div className="co-modalbar">
      <button type="button" className="co-modalbar__back" onClick={onBack}>
        <IconChevronLeft />
        Today
      </button>
      <span className="co-eyebrow co-push">Share</span>
    </div>
  )
}
