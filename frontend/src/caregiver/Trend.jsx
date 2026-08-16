import TrendChart from '../charts/TrendChart'
import { shortDate } from '../lib/format'

/* C3 — Trend.
 *
 * Never a bare frailty number, never a clinical axis label, never a numeric
 * score. The reading underneath states what moved and then immediately states
 * what that does not tell us, because a line going up invites a conclusion the
 * data cannot support.
 */
export default function Trend({ data }) {
  const { person, trend, medications } = data
  const marker = medications.active.find((m) => m.days_since_start <= 30) || null
  const last = trend.series.at(-1)
  const outside = last && last.score > trend.band.high

  return (
    <>
      <header className="co-cg__header">
        <h1 className="co-cg__title">How {person.called}’s been doing</h1>
        <p className="co-cg__sub">Last six months</p>
      </header>

      <div className="co-scroll co-stack co-cg__scroll">
        <div className="co-chartcard">
          <TrendChart
            trend={trend}
            marker={marker?.started}
            label={marker ? `${marker.name.toLowerCase()} started` : undefined}
          />
          <div className="co-legend">
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

        <section className="co-reading">
          <h2 className="co-reading__lede">
            {outside
              ? 'She’s drifted above the expected range over the last three weeks.'
              : 'She’s stayed inside the expected range for her age.'}
          </h2>
          <p className="co-reading__text">
            {marker
              ? `Most of the change came after ${shortDate(marker.started, person.today)}. That doesn’t tell us why — it’s the sort of thing worth mentioning at her next appointment, alongside the medicine list.`
              : 'That doesn’t tell us why — it’s the sort of thing worth mentioning at her next appointment, alongside the medicine list.'}
          </p>
        </section>

        <p className="co-provenance">{trend.provenance}</p>
      </div>
    </>
  )
}
