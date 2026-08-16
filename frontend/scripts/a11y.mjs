/* Accessibility floor — measured in the running app, not asserted in a doc.
 *
 * The brief does not ask for this; it is the floor an app used by a 78-year-old
 * and by a caregiver reading it one-handed has to clear anyway. Four things are
 * checked because four things are easy to get wrong in a one-ink palette:
 *
 *   contrast     one ink on cream means a "quiet" token is a contrast failure
 *                waiting to happen
 *   focus        a visible ring on every focusable control, in a design with no
 *                colour to spare for a focus colour
 *   targets      56px on the elder view, 44px on the caregiver's
 *   names        every control has an accessible name
 *
 * Reduced motion is checked separately, by asserting the media query exists in
 * the built CSS, since it cannot be observed without emulating it.
 */
import { chromium } from 'playwright'

const BASE = process.env.BASE || 'http://localhost:5173'

const PAGES = [
  { path: '/elder', name: 'E1 daily log', minTarget: 56, viewport: { width: 402, height: 874 } },
  { path: '/elder/checkin', name: 'E3 weekly check-in', minTarget: 56, viewport: { width: 402, height: 874 } },
  { path: '/', name: 'C1 today', minTarget: 44, viewport: { width: 402, height: 874 } },
  { path: '/', name: 'C4 alerts', minTarget: 44, viewport: { width: 402, height: 874 }, tab: 'Alerts' },
  { path: '/medicines/add', name: 'C5 add a medicine', minTarget: 44, viewport: { width: 402, height: 874 } },
  { path: '/flag/swollen_ankles', name: 'C6 flag detail', minTarget: 44, viewport: { width: 402, height: 874 } },
  { path: '/', name: 'D1 dashboard', minTarget: 40, viewport: { width: 1440, height: 940 } },
]

const srgb = (c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4)
const luminance = ([r, g, b]) =>
  0.2126 * srgb(r / 255) + 0.7152 * srgb(g / 255) + 0.0722 * srgb(b / 255)
const ratio = (a, b) => {
  const [x, y] = [luminance(a), luminance(b)].sort((p, q) => q - p)
  return (x + 0.05) / (y + 0.05)
}
const parse = (s) => (s.match(/[\d.]+/g) || []).slice(0, 3).map(Number)

const browser = await chromium.launch()
const problems = []

for (const spec of PAGES) {
  await fetch(`${BASE}/api/_reset`, { method: 'POST' }).catch(() => {})
  const page = await browser.newPage({ viewport: spec.viewport })
  await page.goto(BASE + spec.path, { waitUntil: 'networkidle' })
  await page.evaluate(() => document.fonts.ready)
  if (spec.tab) {
    await page.getByRole('tab', { name: spec.tab }).click()
  }
  await page.waitForTimeout(300)

  const found = await page.evaluate(() => {
    // Walk up for the nearest painted background: a transparent element sits on
    // whatever is behind it, and comparing text to `rgba(0,0,0,0)` would pass
    // everything.
    function backdrop(el) {
      let n = el
      while (n && n !== document.documentElement) {
        const cs = getComputedStyle(n)
        // A gradient is a background too. The failed-check card is painted with
        // repeating-linear-gradient and has no backgroundColor at all, so
        // reading only backgroundColor walks past it to the page behind and
        // reports light-on-light for text that is actually light-on-ink.
        if (cs.backgroundImage && cs.backgroundImage !== 'none') {
          const stop = cs.backgroundImage.match(/rgb\([^)]+\)/)
          if (stop) return stop[0]
        }
        const bg = cs.backgroundColor
        if (bg && !/rgba\(0, 0, 0, 0\)|transparent/.test(bg)) return bg
        n = n.parentElement
      }
      return getComputedStyle(document.body).backgroundColor
    }

    const text = []
    for (const el of document.querySelectorAll('p, h1, h2, h3, span, button, a, div, li')) {
      const own = [...el.childNodes]
        .filter((n) => n.nodeType === 3 && n.textContent.trim().length > 1)
        .map((n) => n.textContent.trim())
        .join(' ')
      if (!own) continue
      const cs = getComputedStyle(el)
      if (cs.visibility === 'hidden' || cs.display === 'none') continue
      const r = el.getBoundingClientRect()
      if (r.width === 0 || r.height === 0) continue
      text.push({
        sample: own.slice(0, 48),
        color: cs.color,
        bg: backdrop(el),
        size: parseFloat(cs.fontSize),
        weight: Number(cs.fontWeight) || 400,
      })
    }

    const controls = []
    for (const el of document.querySelectorAll(
      'button, a[href], input, select, [role="tab"], [role="button"]',
    )) {
      const cs = getComputedStyle(el)
      if (cs.visibility === 'hidden' || cs.display === 'none') continue
      const r = el.getBoundingClientRect()
      if (r.width === 0 && r.height === 0) continue
      const label = (
        el.getAttribute('aria-label') ||
        el.textContent.trim() ||
        (el.labels && el.labels[0]?.textContent.trim()) ||
        el.getAttribute('title') ||
        ''
      )
      controls.push({
        tag: el.tagName.toLowerCase(),
        cls: (typeof el.className === 'string' ? el.className : '').slice(0, 40),
        w: Math.round(r.width),
        h: Math.round(r.height),
        label: label.slice(0, 40),
        hidden: el.classList.contains('co-visually-hidden'),
      })
    }
    return { text, controls }
  })

  // --- contrast ---
  for (const t of found.text) {
    const fg = parse(t.color)
    const bg = parse(t.bg)
    if (fg.length < 3 || bg.length < 3) continue
    const large = t.size >= 24 || (t.size >= 18.66 && t.weight >= 700)
    const need = large ? 3 : 4.5
    const got = ratio(fg, bg)
    if (got < need) {
      problems.push(
        `${spec.name}: contrast ${got.toFixed(2)}:1 (needs ${need}) — ` +
        `"${t.sample}" ${t.color} on ${t.bg} @${t.size}px`,
      )
    }
  }

  // --- touch targets & accessible names ---
  for (const c of found.controls) {
    if (c.hidden) continue
    if (!c.label) {
      problems.push(`${spec.name}: control with no accessible name — <${c.tag} class="${c.cls}">`)
    }
    if (c.h < spec.minTarget && c.tag !== 'a') {
      problems.push(
        `${spec.name}: target ${c.w}x${c.h} under ${spec.minTarget}px — "${c.label}" (${c.cls})`,
      )
    }
  }

  // --- focus visibility ---
  // Driven with real Tab presses rather than el.focus(). `:focus-visible` is a
  // heuristic: Chromium stops matching it once the last interaction was a
  // pointer event, so programmatic focus reports "no ring" on any page the
  // check had to click through to reach. Tabbing is also the path the user
  // actually takes, so it exercises the tab order at the same time.
  const noRing = []
  const seen = new Set()
  // Pages reached by clicking a tab leave focus on that tab, and the next Tab
  // press walks straight out of the document. Blurring first restarts the
  // traversal at the top.
  await page.evaluate(() => document.activeElement?.blur())
  for (let i = 0; i < 40; i += 1) {
    await page.keyboard.press('Tab')
    const info = await page.evaluate(() => {
      const el = document.activeElement
      if (!el || el === document.body) return null
      const cs = getComputedStyle(el)
      return {
        key: el.tagName + (el.className || '') + el.textContent?.slice(0, 20),
        label: (el.getAttribute('aria-label') || el.textContent || el.tagName)
          .trim().slice(0, 34),
        style: cs.outlineStyle,
        width: parseFloat(cs.outlineWidth) || 0,
        shadow: cs.boxShadow,
      }
    })
    // Chromium's first Tab after a blur lands on the document body before it
    // reaches any control. Skipping it rather than stopping is the difference
    // between "nothing is focusable" and "the traversal had not started yet".
    if (!info) continue
    if (seen.has(info.key)) break
    seen.add(info.key)
    const ringed =
      (info.style !== 'none' && info.width >= 1) || /inset|rgb/.test(info.shadow)
    if (!ringed) noRing.push(info.label)
  }
  for (const label of noRing) {
    problems.push(`${spec.name}: no visible focus ring on "${label}"`)
  }
  if (seen.size === 0) {
    problems.push(`${spec.name}: nothing reachable by keyboard`)
  }

  console.log(
    `checked ${spec.name.padEnd(20)} ${found.text.length} text runs, ` +
    `${found.controls.length} controls`,
  )
  await page.close()
}

// --- reduced motion ---
const page = await browser.newPage()
await page.goto(BASE + '/', { waitUntil: 'networkidle' })
const honoursReducedMotion = await page.evaluate(() => {
  // The stylesheet is organised in cascade layers, so the media rules are
  // nested inside CSSLayerBlockRules rather than sitting at the top level.
  // A flat scan of cssRules finds nothing and reports a false failure.
  const walk = (rules) =>
    [...rules].some(
      (r) =>
        r.conditionText?.includes('prefers-reduced-motion') ||
        (r.cssRules && walk(r.cssRules)),
    )
  return [...document.styleSheets].some((sheet) => {
    try {
      return walk(sheet.cssRules)
    } catch {
      return false
    }
  })
})
if (!honoursReducedMotion) problems.push('no prefers-reduced-motion rule found in loaded CSS')
await page.close()
await browser.close()

console.log('')
if (!problems.length) {
  console.log('✓ contrast, targets, names, focus and reduced-motion all pass')
  process.exit(0)
}
const unique = [...new Set(problems)]
console.log(`✗ ${unique.length} issue(s):\n`)
for (const p of unique) console.log('  ' + p)
process.exit(1)
