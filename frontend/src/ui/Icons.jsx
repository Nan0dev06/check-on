/* Hand-authored line SVGs. No icon library, by design.
 *
 * Rules from DESIGN_SYSTEM.md §4: stroke-width 2.2–2.6, round caps, no fills,
 * paths built from `q` curves so they read as drawn rather than geometric. The
 * six symptom pictograms are deliberately warm rather than clinical — they have
 * to be readable with the label covered.
 *
 * Every icon is decorative here: each one sits next to a visible text label, so
 * they carry aria-hidden and the label does the announcing.
 */

const base = {
  fill: 'none',
  stroke: 'currentColor',
  strokeLinecap: 'round',
  strokeLinejoin: 'round',
  'aria-hidden': true,
  focusable: 'false',
}

/* --- the six elder tiles, in grid order ---------------------------------- */

export function IconDizzy({ size = 52, width = 2.6 }) {
  // An inward spiral: the room going round.
  return (
    <svg {...base} width={size} height={size} viewBox="0 0 48 48" strokeWidth={width}>
      <path d="M24 24a4 4 0 1 0 4 4 8 8 0 1 1-8-8 12 12 0 1 0 12 12 16 16 0 1 1-16-16" />
    </svg>
  )
}

export function IconWornOut({ size = 52, width = 2.6 }) {
  // A crescent moon, slightly lopsided so it reads as drawn.
  return (
    <svg {...base} width={size} height={size} viewBox="0 0 48 48" strokeWidth={width}>
      <path d="M29 9a15 15 0 1 0 11 27A18 18 0 0 1 29 9Z" />
    </svg>
  )
}

export function IconFoggy({ size = 52, width = 2.6 }) {
  // Three stacked wavy lines — mist, not a brain.
  return (
    <svg {...base} width={size} height={size} viewBox="0 0 48 48" strokeWidth={width}>
      <path d="M9 17q6-7 12 0t12 0 6-1" />
      <path d="M9 25q6-7 12 0t12 0 6-1" />
      <path d="M9 33q6-7 12 0t12 0 6-1" />
    </svg>
  )
}

export function IconWeak({ size = 52, width = 2.6 }) {
  // A flexed arm reduced to its silhouette: forearm up, fist at the top.
  // The reference drawing, kept verbatim — redraws that added a shoulder and a
  // drooped forearm read worse at 52px, not better.
  return (
    <svg {...base} width={size} height={size} viewBox="0 0 48 48" strokeWidth={width}>
      <path d="M20 40V22c0-7 6-10 12-8" />
      <circle cx="35" cy="12" r="4.5" />
    </svg>
  )
}

export function IconQueasy({ size = 52, width = 2.6 }) {
  // A face with a wavy mouth. No eyes — it stays a pictogram, not a character.
  return (
    <svg {...base} width={size} height={size} viewBox="0 0 48 48" strokeWidth={width}>
      <circle cx="24" cy="24" r="15" />
      <path d="M15 27q4.5-7 9 0t9 0" />
    </svg>
  )
}

export function IconPuffyAnkles({ size = 52, width = 2.6 }) {
  // A leg tapering into a swollen ellipse. The reference drawing, kept
  // verbatim: adding shin lines and a foot turned it into clutter at 52px.
  return (
    <svg {...base} width={size} height={size} viewBox="0 0 48 48" strokeWidth={width}>
      <path d="M24 9v15" />
      <ellipse cx="24" cy="33" rx="12" ry="7.5" />
    </svg>
  )
}

export const SYMPTOM_ICONS = {
  dizzy: IconDizzy,
  tired: IconWornOut,
  foggy: IconFoggy,
  weak: IconWeak,
  nauseous: IconQueasy,
  swollen_ankles: IconPuffyAnkles,
}

/* --- interface icons ------------------------------------------------------ */

export function IconCheck({ size = 44, width = 3.4 }) {
  return (
    <svg {...base} width={size} height={size} viewBox="0 0 44 44" strokeWidth={width}>
      <path d="M11 23l8 8 15-18" />
    </svg>
  )
}

export function IconChevronLeft({ size = 20, width = 2.4 }) {
  return (
    <svg {...base} width={size} height={size} viewBox="0 0 20 20" strokeWidth={width}>
      <path d="M12 4l-7 6 7 6" />
    </svg>
  )
}

/* MEDICATION_LINKED — an up arrow. Something has risen. */
export function IconRise({ size = 20, width = 2.2 }) {
  return (
    <svg {...base} width={size} height={size} viewBox="0 0 20 20" strokeWidth={width}>
      <path d="M10 3v9" />
      <path d="M4 8l6-5 6 5" />
    </svg>
  )
}

/* UNEXPLAINED_DEVIATION — a plain circle. Attentive, not alarmed. */
export function IconWatch({ size = 20, width = 2.2 }) {
  return (
    <svg {...base} width={size} height={size} viewBox="0 0 20 20" strokeWidth={width}>
      <circle cx="10" cy="10" r="7" />
      <path d="M10 7v6" />
    </svg>
  )
}

/* INSUFFICIENT_HISTORY — an unfinished wave. Neither good nor bad. */
export function IconLearning({ size = 20, width = 2.2 }) {
  return (
    <svg {...base} width={size} height={size} viewBox="0 0 20 20" strokeWidth={width}>
      <path d="M3 14q4-9 7 0t7-4" />
    </svg>
  )
}

/* QUERY_FAILED — a cross, in the one amber the palette allows. */
export function IconFailed({ size = 20, width = 2.2 }) {
  return (
    <svg {...base} width={size} height={size} viewBox="0 0 20 20" strokeWidth={width}>
      <path d="M4 4l12 12" />
      <path d="M16 4L4 16" />
    </svg>
  )
}

/* Desktop hero — a speech bubble with an exclamation: something to raise. */
export function IconRaise({ size = 54, width = 2.6 }) {
  return (
    <svg {...base} width={size} height={size} viewBox="0 0 54 54" strokeWidth={width}>
      <path d="M27 6C15 6 6 15 6 26c0 5 2 9 5 12l-2 9 9-3q4 2 9 2c12 0 21-9 21-20S39 6 27 6Z" />
      <path d="M27 17v11" />
      <circle cx="27" cy="34" r="1.4" fill="currentColor" stroke="none" />
    </svg>
  )
}

/* The wobbly underline beneath the desktop wordmark. */
export function WordmarkUnderline() {
  return (
    <svg
      {...base}
      width="150"
      height="9"
      viewBox="0 0 150 9"
      strokeWidth="2.4"
      style={{ color: 'var(--ink)' }}
    >
      <path d="M2 6q22-5 40-1t38-3 34 3 34-3" />
    </svg>
  )
}
