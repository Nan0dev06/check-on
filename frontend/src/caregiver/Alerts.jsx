import { alertBody, alertHeadline } from '../lib/copy'

/* C4 — Alerts.
 *
 * Two levels, distinguishable while skimming, and nothing sits between them.
 * That separation is the entire anti-alert-fatigue requirement: the backend
 * pushes exactly two urgencies, and a caregiver who is pinged for everything
 * stops reading the pings.
 *
 * Feed-only items are deliberately absent from this screen. They are visible on
 * Today, where they demand nothing.
 */
export default function Alerts({ data, onOpenFlag }) {
  const { person, notifications, flags } = data
  const high = notifications.high
  const low = notifications.low

  return (
    <>
      <header className="co-cg__header">
        <h1 className="co-cg__title">Alerts</h1>
        <p className="co-cg__sub">Two kinds, on purpose</p>
      </header>

      <div className="co-scroll co-stack co-cg__scroll co-alerts">
        {high.length > 0 && (
          <section className="co-alerts__group">
            <h2 className="co-eyebrow">Needs a conversation</h2>
            {high.map((n) => {
              const flag = flags.find((f) => f.symptom === n.symptom)
              return (
                <article className="co-alert co-on-ink" key={n.id}>
                  <p className="co-alert__kind">
                    <span className="co-dot co-dot--warn" />
                    {n.outcome === 'medication_linked'
                      ? 'Medication-linked flag'
                      : 'Outside her usual pattern'}
                  </p>
                  <h3 className="co-alert__title">
                    {flag ? alertHeadline(flag) : n.message}
                  </h3>
                  <p className="co-alert__text">
                    {flag ? alertBody(flag) : n.message}
                  </p>
                  <div className="co-alert__actions">
                    <button
                      type="button"
                      className="co-btn co-btn--onink-primary co-btn--grow"
                      onClick={() => flag && onOpenFlag(flag)}
                    >
                      Open the flag
                    </button>
                    <a
                      className="co-btn co-btn--onink-secondary co-btn--grow"
                      href={`tel:${person.phone}`}
                    >
                      Call {person.called}
                    </a>
                  </div>
                </article>
              )
            })}
          </section>
        )}

        {low.length > 0 && (
          <section className="co-alerts__group">
            <h2 className="co-eyebrow">Quiet nudges</h2>
            {low.map((n) => (
              <article className="co-nudge" key={n.id}>
                <span className="co-dot co-nudge__dot" />
                <span className="co-col">
                  <h3 className="co-nudge__title">{n.title || 'A gentle reminder'}</h3>
                  <p className="co-nudge__text">{n.body || n.message}</p>
                  {n.at && <p className="co-nudge__at">{n.at}</p>}
                </span>
              </article>
            ))}
          </section>
        )}
      </div>
    </>
  )
}
