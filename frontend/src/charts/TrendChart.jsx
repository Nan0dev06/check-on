import { makeAxis, makeValueScale, monthStart, wobblyPath } from './axis'

/* The frailty trend, phone size.
 *
 * Hand-authored SVG at a fixed viewBox, scaled with width:100%. No charting
 * library — the wobble and the hand-lettered annotation are the point.
 *
 * Nothing on this chart carries a number. §C3: never a bare frailty score,
 * never a clinical axis label. The y-axis has no ticks at all, because the only
 * true statement it could make is a relative one.
 */
export default function TrendChart({ trend, marker, label = 'amlodipine started' }) {
  const series = trend.series
  if (series.length < 2) return null

  const axis = makeAxis({
    from: monthStart(series[0].date),
    to: series[series.length - 1].date,
    x0: 14,
    x1: 316,
  })
  const scale = makeValueScale({
    series,
    band: trend.band,
    yTop: 40,
    yBottom: 168,
  })

  const points = series.map((p) => ({ x: axis.x(p.date), y: scale.y(p.score) }))
  const last = points[points.length - 1]
  const bandTop = scale.y(trend.band.high)
  const bandBottom = scale.y(trend.band.low)
  const markerX = marker && axis.covers(marker) ? axis.x(marker) : null

  return (
    <svg
      viewBox="0 0 330 200"
      style={{ width: '100%', height: '210px', display: 'block' }}
      role="img"
      aria-label={ariaLabel(trend, marker)}
    >
      {/* Expected for her age.
          Flat, because the fitted population curve moves about half a
          thousandth of a point per week — it is a band to compare against, not
          a forecast, and drawing it as a widening cone would imply a growing
          uncertainty the model does not have.
          The top edge is stroked: where the band ends is the only actionable
          thing on this chart, and a plain fill leaves that edge to be inferred
          from a colour change. */}
      <rect
        x={axis.x0}
        y={bandTop}
        width={axis.x1 - axis.x0}
        height={Math.max(2, bandBottom - bandTop)}
        fill="var(--ink-tint)"
      />
      <line
        x1={axis.x0}
        y1={bandTop}
        x2={axis.x1}
        y2={bandTop}
        stroke="var(--rule-strong)"
        strokeWidth="1.5"
      />

      {markerX !== null && (
        <>
          <line
            x1={markerX}
            y1="30"
            x2={markerX}
            y2="176"
            stroke="var(--rule-strong)"
            strokeWidth="1.5"
            strokeDasharray="4 5"
          />
          <text
            x={markerX - 6}
            y="24"
            textAnchor="end"
            fontFamily="IBM Plex Mono, monospace"
            fontSize="11"
            fill="var(--ink-mute)"
          >
            {label}
          </text>
        </>
      )}

      <path
        d={wobblyPath(points)}
        fill="none"
        stroke="var(--ink)"
        strokeWidth="3.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx={last.x} cy={last.y} r="6" fill="var(--ink)" />

      <text
        x={axis.x0}
        y="192"
        fontFamily="IBM Plex Mono, monospace"
        fontSize="11"
        fill="var(--ink-mute)"
      >
        {axis.monthTicks()[0]?.label}
      </text>
      <text
        x={axis.x1}
        y="192"
        textAnchor="end"
        fontFamily="IBM Plex Mono, monospace"
        fontSize="11"
        fill="var(--ink-mute)"
      >
        {axis.monthTicks().at(-1)?.label}
      </text>
    </svg>
  )
}

/* A chart is not readable by a screen reader, so it gets the same sentence the
 * caregiver would read off it — and the same restriction: no score, no number
 * that could be mistaken for a clinical measurement. */
function ariaLabel(trend, marker) {
  const series = trend.series
  const last = series.at(-1).score
  const outside = last > trend.band.high
  return (
    `Her weekly answers over ${series.length} weeks, against the range expected ` +
    `for her age. The line ends ${outside ? 'above' : 'inside'} that range` +
    `${marker ? ', with a marker where the new medicine started' : ''}.`
  )
}
