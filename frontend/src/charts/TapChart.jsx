import { makeAxis } from './axis'
import { monoAxis, parse } from '../lib/format'

/* Every tap, against the medicine.
 *
 * This single graphic is the app's whole argument: one hollow dot before the
 * medicine started, a run of filled dots after it, and a bar marking the days
 * she has been taking it. It has to survive the port intact, so the marks are
 * placed from real tap dates on the same kind of linear day scale the desktop
 * pair uses — the gap between the marker and the first filled dot is a real
 * number of days, not a drawn one.
 */
export default function TapChart({ flag, medication, todayIso }) {
  const taps = flag.taps || []
  if (!taps.length || !medication) return null

  const earliest = taps.reduce((a, b) => (parse(a) < parse(b) ? a : b))
  const from = shift(
    parse(earliest) < parse(medication.started) ? earliest : medication.started,
    -3,
  )
  const axis = makeAxis({ from, to: todayIso, x0: 14, x1: 316 })

  const startX = axis.x(medication.started)
  const before = taps.filter((t) => parse(t) < parse(medication.started))
  const after = taps.filter((t) => parse(t) >= parse(medication.started))
  const drug = medication.name.toLowerCase()

  return (
    <svg
      viewBox="0 0 330 128"
      style={{ width: '100%', display: 'block' }}
      role="img"
      aria-label={
        `${after.length} taps of ${flag.tile_label.toLowerCase()} after ${drug} ` +
        `started, and ${before.length || 'no'} before it.`
      }
    >
      {/* baseline */}
      <path
        d="M14 96h302"
        stroke="var(--ink)"
        strokeWidth="2"
        strokeLinecap="round"
      />

      {/* the day the medicine started */}
      <path
        d={`M${startX} 22v74`}
        stroke="var(--ink)"
        strokeWidth="1.6"
        strokeDasharray="5 6"
      />
      <text
        x={startX - 6}
        y="18"
        textAnchor="end"
        fontFamily="Caveat, cursive"
        fontSize="18"
        fill="var(--ink)"
      >
        {drug}
      </text>

      {/* the days she has been taking it */}
      <rect
        x={startX}
        y="100"
        width={Math.max(0, axis.x1 - startX)}
        height="8"
        rx="4"
        fill="var(--ink)"
      />

      {before.map((t) => (
        <circle
          key={t}
          cx={axis.x(t)}
          cy="76"
          r="6"
          fill="none"
          stroke="var(--rule-strong)"
          strokeWidth="2"
        />
      ))}
      {/* Counting the dots is the whole point of this chart, so the radius is
          derived from how close together the taps actually are rather than
          fixed at the reference's 7. Four taps across five days sit about eight
          viewBox units apart; 7-unit radii would merge them into two blobs and
          the reader would undercount. The dots stay on their real dates and the
          radius gives way instead. */}
      {after.map((t) => (
        <circle
          key={t}
          cx={axis.x(t)}
          cy="76"
          r={dotRadius(after, axis)}
          fill="var(--ink)"
          stroke="var(--card)"
          strokeWidth="1.5"
        />
      ))}

      <text
        x="14"
        y="122"
        fontFamily="IBM Plex Mono, monospace"
        fontSize="10"
        fill="var(--ink-mute)"
      >
        {monoAxis(axis.from)}
      </text>
      <text
        x="316"
        y="122"
        textAnchor="end"
        fontFamily="IBM Plex Mono, monospace"
        fontSize="10"
        fill="var(--ink-mute)"
      >
        {monoAxis(axis.to)}
      </text>
    </svg>
  )
}

/** Largest radius up to the reference's 7 that still leaves daylight between
 * the two closest taps. */
function dotRadius(taps, axis) {
  const xs = taps.map((t) => axis.x(t)).sort((a, b) => a - b)
  let gap = Infinity
  for (let i = 1; i < xs.length; i += 1) gap = Math.min(gap, xs[i] - xs[i - 1])
  if (!Number.isFinite(gap)) return 7
  return Math.max(3.5, Math.min(7, gap / 2 - 0.75))
}

function shift(date, days) {
  const d = new Date(date)
  d.setDate(d.getDate() + days)
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}
