import { makeAxis, makeValueScale, monthStart, wobblyPath } from '../../charts/axis'
import { monoDate, shortDate, ageLabel } from '../../lib/format'

/* The shared timeline — the reason the desktop layout exists.
 *
 * Two stacked SVGs, one axis object. Every x coordinate in both charts comes
 * from `axis.x(date)`; neither chart computes a position any other way and
 * neither is passed a pixel value. That is what makes "2 August" on the
 * medication bar sit exactly under the point on the curve where the line starts
 * to climb — not a shared constant that two components each remember to use,
 * but a single function they are both handed.
 *
 * Both viewBoxes are 900 wide and both are rendered at width:100%, so a
 * viewBox unit is the same on-screen distance in each. Changing one chart's
 * viewBox width without the other would break the alignment silently, which is
 * why the width lives here as one constant.
 */
const VB_WIDTH = 900
const X0 = 60
const X1 = 878

export default function SharedTimeline({ trend, medications, person }) {
  const series = trend.series
  if (series.length < 2) return null

  const axis = makeAxis({
    from: monthStart(series[0].date),
    to: person.today,
    x0: X0,
    x1: X1,
  })

  // Newest first, but everything she is still taking comes before everything
  // she has stopped. Interleaving them by start date buries a current medicine
  // under a discontinued one, and the current list is what a prescriber needs.
  const byNewest = (a, b) => b.started.localeCompare(a.started)
  const meds = [
    ...[...medications.active].sort(byNewest),
    ...[...medications.stopped].sort(byNewest),
  ]
  const recent = medications.active.find((m) => m.days_since_start <= 30) || null
  const older = medications.active.find(
    (m) => m !== recent && axis.covers(m.started),
  )

  const markers = [
    recent && { iso: recent.started, tone: 'ink', label: `${recent.name.toLowerCase()} starts here` },
    older && { iso: older.started, tone: 'soft' },
  ].filter(Boolean)

  return (
    <>
      <FrailtyChart trend={trend} axis={axis} markers={markers} />
      <MedicationTimeline
        axis={axis}
        meds={meds}
        recent={recent}
        markers={markers}
        today={person.today}
      />
    </>
  )
}

/* --- top: how she's been ------------------------------------------------- */

function FrailtyChart({ trend, axis, markers }) {
  const series = trend.series
  const scale = makeValueScale({
    series,
    band: trend.band,
    yTop: 40,
    yBottom: 200,
  })
  const points = series.map((p) => ({ x: axis.x(p.date), y: scale.y(p.score) }))
  const last = points.at(-1)
  const bandTop = scale.y(trend.band.high)
  const bandBottom = scale.y(trend.band.low)

  return (
    <svg
      viewBox={`0 0 ${VB_WIDTH} 240`}
      style={{ width: '100%', display: 'block' }}
      role="img"
      aria-label={
        `Her weekly answers from ${series[0].date} to ${series.at(-1).date}, ` +
        `against the range expected for her age. The line leaves that range at ` +
        `the right-hand end.`
      }
    >
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

      {markers.map((m) => (
        <line
          key={m.iso}
          x1={axis.x(m.iso)}
          y1="26"
          x2={axis.x(m.iso)}
          y2="216"
          stroke={m.tone === 'ink' ? 'var(--ink)' : 'var(--rule-soft)'}
          strokeWidth="1.6"
          strokeDasharray="5 6"
        />
      ))}

      {markers
        .filter((m) => m.label)
        .map((m) => (
          <text
            key={m.iso}
            x={axis.x(m.iso) - 6}
            y="20"
            textAnchor="end"
            fontFamily="Caveat, cursive"
            fontWeight="600"
            fontSize="19"
            fill="var(--ink)"
          >
            {m.label}
          </text>
        ))}

      <path
        d={wobblyPath(points, 0.1)}
        fill="none"
        stroke="var(--ink)"
        strokeWidth="3.2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx={last.x} cy={last.y} r="6.5" fill="var(--ink)" />

      <path
        d={`M${axis.x0} 216h${axis.x1 - axis.x0}`}
        stroke="var(--ink)"
        strokeWidth="2"
        strokeLinecap="round"
      />
      {axis.monthTicks().map((t) => (
        <text
          key={t.iso}
          x={t.x}
          y="236"
          fontFamily="IBM Plex Mono, monospace"
          fontSize="12"
          fill="var(--ink-mute)"
        >
          {t.label}
        </text>
      ))}
    </svg>
  )
}

/* --- bottom: what she's been taking -------------------------------------- */

/* Row pitch has to clear the flagged medicine's two-line label, which sits
 * beside its bar rather than inside it — the bar is only a fortnight wide, so
 * there is nowhere to put the text within it. */
const ROW_H = 44

function MedicationTimeline({ axis, meds, recent, markers, today }) {
  const height = 34 + meds.length * ROW_H + 8

  return (
    <svg
      viewBox={`0 0 ${VB_WIDTH} ${height}`}
      style={{ width: '100%', display: 'block' }}
      role="img"
      aria-label={
        `Each medicine as a bar starting on the day she started it: ` +
        meds
          .map((m) => `${m.name} from ${shortDate(m.started, today)}`)
          .join('; ') + '.'
      }
    >
      <text
        x={axis.x0}
        y="14"
        fontFamily="IBM Plex Mono, monospace"
        fontSize="11"
        letterSpacing="1.6"
        fill="var(--ink-mute)"
      >
        MEDICINES · BAR STARTS ON THE DAY SHE STARTED IT
      </text>

      {/* The same two verticals as the chart above, continuing down. Same
          axis, so they line up by construction rather than by measurement. */}
      {markers.map((m) => (
        <line
          key={m.iso}
          x1={axis.x(m.iso)}
          y1="30"
          x2={axis.x(m.iso)}
          y2={height - 6}
          stroke={m.tone === 'ink' ? 'var(--ink)' : 'var(--rule-soft)'}
          strokeWidth="1.6"
          strokeDasharray="5 6"
        />
      ))}

      {meds.map((med, i) => (
        <MedicationBar
          key={med.id}
          med={med}
          axis={axis}
          y={30 + i * ROW_H}
          today={today}
          flagged={med.id === recent?.id}
        />
      ))}
    </svg>
  )
}

function MedicationBar({ med, axis, y, today, flagged }) {
  const stopped = !!med.stopped
  const startsBefore = !axis.covers(med.started)
  const x = startsBefore ? axis.x0 : axis.x(med.started)
  const end = stopped ? axis.x(med.stopped) : axis.x1
  const h = flagged ? 30 : 26
  const label = `${med.name}${med.dose_value ? ` ${med.dose_value} ${med.dose_unit}` : ''}`

  return (
    <g>
      {/* Predates the window: a small triangle at the left edge means the bar
          continues off-chart, rather than implying it started in March. */}
      {startsBefore && !stopped && (
        <path d={`M${axis.x0 - 14} ${y + h / 2}l14-10v20Z`} fill="var(--ink)" />
      )}

      <rect
        x={x}
        y={y}
        width={Math.max(4, end - x)}
        height={h}
        rx={h / 2}
        fill={flagged ? 'var(--ink)' : 'none'}
        stroke={stopped ? 'var(--rule-strong)' : flagged ? 'none' : 'var(--ink)'}
        strokeWidth={stopped ? '1.8' : '2'}
        strokeDasharray={stopped ? '6 5' : undefined}
      />

      {/* The flagged medicine's bar is short — it only just started — so its
          name sits to the left of the marker rather than inside the bar. */}
      {flagged ? (
        <>
          <text
            x={x - 6}
            y={y + 20}
            textAnchor="end"
            fontFamily="Archivo, sans-serif"
            fontWeight="600"
            fontSize="16"
            fill="var(--text)"
          >
            {label}
          </text>
          <text
            x={x - 6}
            y={y + 36}
            textAnchor="end"
            fontFamily="IBM Plex Mono, monospace"
            fontSize="12"
            fill="var(--ink)"
          >
            {monoDate(med.started).replace(/ \d{4}$/, '')} ·{' '}
            {ageLabel(med.started, today).toUpperCase()}
          </text>
        </>
      ) : (
        <>
          <text
            x={x + 12}
            y={y + h / 2 + 5}
            fontFamily="Archivo, sans-serif"
            fontWeight="500"
            fontSize="15"
            fill={stopped ? 'var(--ink-mute)' : 'var(--text)'}
            textDecoration={stopped ? 'line-through' : undefined}
          >
            {label}
          </text>
          <text
            x={end - 10}
            y={y + h / 2 + 5}
            textAnchor="end"
            fontFamily="IBM Plex Mono, monospace"
            fontSize={stopped ? '11' : '12'}
            fill="var(--ink-mute)"
          >
            {stopped
              ? `STOPPED ${monoDate(med.stopped).replace(/ \d{4}$/, '')}`
              : startsBefore
                ? `SINCE ${new Date(med.started).getFullYear()}`
                : monoDate(med.started).replace(/ \d{4}$/, '')}
          </text>
        </>
      )}
    </g>
  )
}
