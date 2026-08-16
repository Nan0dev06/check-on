/* The shared time axis.
 *
 * This module exists for one reason, stated in DESIGN_SYSTEM.md §5: on the
 * desktop dashboard the frailty chart and the medication timeline must use the
 * same x-axis geometry, so a medication start date lines up vertically with the
 * point on the trend curve. That alignment is the justification for the whole
 * desktop layout — if a start date sits even a few pixels off the curve, the
 * feature does not work.
 *
 * The guarantee is structural rather than a matter of care: both SVGs are
 * handed the same axis object and neither computes an x coordinate any other
 * way. There is exactly one date -> x function in this app.
 *
 * One deliberate difference from the reference drawing: the reference spaces
 * month labels evenly at 147px, which treats February and August as the same
 * width. A start date placed on an evenly-spaced axis lands up to four days
 * off. This uses a true linear day scale, so month ticks sit a few pixels from
 * where the reference drew them and every date is exact. Accuracy is the point
 * of the axis; even spacing was an artefact of drawing it by hand.
 */

const DAY = 86400000
const MONTHS = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN',
  'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']

function toDate(v) {
  if (v instanceof Date) return v
  const [y, m, d] = String(v).split('-').map(Number)
  return new Date(y, m - 1, d)
}

/**
 * @param {object} o
 * @param {string} o.from  first day covered, ISO
 * @param {string} o.to    last day covered, ISO
 * @param {number} o.x0    left edge in viewBox units
 * @param {number} o.x1    right edge in viewBox units
 */
export function makeAxis({ from, to, x0, x1 }) {
  const start = toDate(from)
  const end = toDate(to)
  const days = Math.max(1, Math.round((end - start) / DAY))
  const perDay = (x1 - x0) / days

  /** ISO date (or Date) -> x, clamped to the drawn range. */
  function x(value) {
    const d = toDate(value)
    const offset = Math.round((d - start) / DAY)
    return x0 + Math.min(Math.max(offset, 0), days) * perDay
  }

  /** Whether a date falls inside the drawn window at all. */
  function covers(value) {
    const d = toDate(value)
    return d >= start && d <= end
  }

  /** First-of-month ticks, labelled MAR / APR / …. */
  function monthTicks() {
    const out = []
    const cursor = new Date(start.getFullYear(), start.getMonth(), 1)
    while (cursor <= end) {
      if (cursor >= start) {
        out.push({
          x: x(cursor),
          label: MONTHS[cursor.getMonth()],
          iso: isoOf(cursor),
        })
      }
      cursor.setMonth(cursor.getMonth() + 1)
    }
    return out
  }

  return { x, covers, monthTicks, x0, x1, from: isoOf(start), to: isoOf(end), days, perDay }
}

function isoOf(d) {
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

/** Snap to the first of the month, so the axis starts on a labelled tick. */
export function monthStart(iso) {
  const d = toDate(iso)
  return isoOf(new Date(d.getFullYear(), d.getMonth(), 1))
}

/**
 * Vertical scale for the frailty line.
 *
 * There is never a numeric axis label on this chart — §C3 forbids a bare
 * frailty number — so this scale exists purely to place marks. The top of the
 * domain is derived from whichever is higher, her worst score or the top of the
 * expected band, with a little headroom so a line that leaves the band is
 * visibly outside it rather than clipped to the frame.
 */
export function makeValueScale({ series, band, yTop, yBottom }) {
  const scores = series.map((p) => p.score)
  const hi = Math.max(band.high, ...scores) * 1.1 || 1
  // The band's lower edge is usually pinned at zero, and a band that sits flush
  // on the frame reads as a fill rather than a range. A little room underneath
  // keeps it legible as a band without implying scores below zero exist.
  const lo = -0.15 * hi
  const y = (v) => yBottom - ((v - lo) / (hi - lo)) * (yBottom - yTop)
  return { y, hi, lo }
}

/** A polyline through the points, drawn with a slight hand wobble.
 *
 * The wobble is the design, not decoration: §4 asks for paths built from `q`
 * curves so they read as drawn rather than plotted. Each segment bows by a
 * fixed fraction of its own length, so the deviation is proportional and the
 * line still passes through every real data point. */
export function wobblyPath(points, bow = 0.14) {
  if (points.length < 2) return ''
  let d = `M${round(points[0].x)} ${round(points[0].y)}`
  for (let i = 1; i < points.length; i += 1) {
    const a = points[i - 1]
    const b = points[i]
    const mx = (a.x + b.x) / 2
    const my = (a.y + b.y) / 2
    // Offset the control point perpendicular to the segment, alternating side.
    const dx = b.x - a.x
    const dy = b.y - a.y
    const len = Math.hypot(dx, dy) || 1
    const side = i % 2 === 0 ? 1 : -1
    const cx = mx + (-dy / len) * bow * len * 0.35 * side
    const cy = my + (dx / len) * bow * len * 0.35 * side
    d += ` Q${round(cx)} ${round(cy)} ${round(b.x)} ${round(b.y)}`
  }
  return d
}

const round = (n) => Math.round(n * 10) / 10
