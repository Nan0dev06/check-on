/* Screenshot harness — the self-check loop, not a test suite.
 *
 * Each shot is taken at the exact viewport the design specifies (402 x 874 for
 * both phone products, 1440 x 900 for the dashboard) so a capture can be
 * compared to the reference without any scaling in between.
 *
 *   node scripts/shots.mjs [name ...]
 *
 * Also reports, for the elder log, whether the page scrolls — the fit
 * requirement is a pass/fail, so it is measured rather than eyeballed.
 */
import { chromium } from 'playwright'
import { mkdir } from 'node:fs/promises'

const BASE = process.env.BASE || 'http://localhost:5173'
const OUT = process.env.OUT || 'shots'

const PHONE = { width: 402, height: 874 }
const DESKTOP = { width: 1440, height: 940 }

const SHOTS = {
  'e1-daily-log': { path: '/elder', viewport: PHONE, checkFit: true },
  'e2-confirmation': {
    path: '/elder',
    viewport: PHONE,
    async act(page) {
      await page.getByRole('button', { name: 'Puffy ankles' }).click()
      await page.waitForTimeout(350)
    },
  },
  'e3-checkin-q1': { path: '/elder/checkin', viewport: PHONE, checkFit: true },
  'e3-checkin-q2': {
    path: '/elder/checkin',
    viewport: PHONE,
    async act(page) {
      await page.getByRole('button', { name: 'About the same' }).click()
      await page.waitForTimeout(250)
    },
  },
  'e3-checkin-done': {
    path: '/elder/checkin',
    viewport: PHONE,
    async act(page) {
      for (const label of ['About the same', 'Less than usual', 'Now and then',
        'A bit harder than usual']) {
        await page.getByRole('button', { name: label }).click()
        await page.waitForTimeout(200)
      }
    },
  },
  'c1-today': { path: '/', viewport: PHONE },
  'c2-medicines': { path: '/', viewport: PHONE, tab: 'Medicines' },
  'c3-trend': { path: '/', viewport: PHONE, tab: 'Trend' },
  'c4-alerts': { path: '/', viewport: PHONE, tab: 'Alerts' },
  'c5-add-medicine': { path: '/medicines/add', viewport: PHONE },
  'c5-add-medicine-typing': {
    path: '/medicines/add',
    viewport: PHONE,
    async act(page) {
      await page.getByLabel('Name').fill('Amlo')
      // Real openFDA lookup behind the debounce, so wait for the result.
      await page.locator('.co-suggest__row').first().waitFor({ timeout: 20000 })
    },
  },
  'c5-add-medicine-ready': {
    path: '/medicines/add',
    viewport: PHONE,
    async act(page) {
      await page.getByLabel('Name').fill('Amlodipine')
      await page.locator('.co-input__badge', { hasText: 'MATCHED' }).waitFor({ timeout: 20000 })
      await page.getByRole('button', { name: 'Today' }).click()
      await page.waitForTimeout(250)
    },
  },
  'c6-flag-detail': { path: '/flag/swollen_ankles', viewport: PHONE },
  'd1-dashboard': { path: '/', viewport: DESKTOP, full: true, checkAxis: true },
  'd2-dashboard-modal': {
    path: '/flag/swollen_ankles',
    viewport: DESKTOP,
    full: true,
  },
}

const wanted = process.argv.slice(2)
const names = wanted.length ? wanted : Object.keys(SHOTS)

await mkdir(OUT, { recursive: true })
const browser = await chromium.launch()
const problems = []

for (const name of names) {
  const shot = SHOTS[name]
  if (!shot) {
    console.log(`?  ${name} — no such shot`)
    continue
  }
  // Several shots drive real interactions (tap a tile, answer the check-in),
  // which mutate the demo state. Reset first so each capture starts from the
  // same seed and shots don't depend on the order they were taken in.
  await fetch(`${BASE}/api/_reset`, { method: 'POST' }).catch(() => {})

  const page = await browser.newPage({ viewport: shot.viewport, deviceScaleFactor: 2 })
  const errors = []
  page.on('pageerror', (e) => errors.push(String(e)))
  page.on('console', (m) => m.type() === 'error' && errors.push(m.text()))

  await page.goto(BASE + shot.path, { waitUntil: 'networkidle' })
  await page.evaluate(() => document.fonts.ready)
  if (shot.tab) {
    await page.getByRole('tab', { name: shot.tab }).click()
    await page.waitForTimeout(300)
  }
  if (shot.act) await shot.act(page)
  await page.waitForTimeout(200)

  await page.screenshot({ path: `${OUT}/${name}.png`, fullPage: !!shot.full })

  let note = ''
  if (shot.checkFit) {
    const fit = await page.evaluate(() => ({
      doc: document.documentElement.scrollHeight,
      win: window.innerHeight,
      inner: [...document.querySelectorAll('*')]
        .filter((el) => el.scrollHeight > el.clientHeight + 1)
        .map((el) => el.className || el.tagName),
    }))
    const scrolls = fit.doc > fit.win + 1 || fit.inner.length > 0
    note = scrolls
      ? `  ✗ SCROLLS (doc ${fit.doc} > ${fit.win}${fit.inner.length ? `, inner: ${fit.inner.join(', ')}` : ''})`
      : `  ✓ fits ${fit.doc}/${fit.win}`
    if (scrolls) problems.push(`${name}: scrolls`)
  }
  // The shared-axis guarantee, measured in real screen pixels rather than
  // trusted. Both charts draw a dashed marker on the same date; if those two
  // lines are not at the same x on screen, the desktop layout does not work.
  if (shot.checkAxis) {
    const axis = await page.evaluate(() => {
      const svgs = [...document.querySelectorAll('.co-dash__timeline svg')]
      if (svgs.length < 2) return { error: 'expected two stacked charts' }
      const dashedX = (svg) =>
        [...svg.querySelectorAll('line[stroke-dasharray], path[stroke-dasharray]')]
          .map((el) => el.getBoundingClientRect())
          .filter((r) => r.height > r.width) // verticals only
          .map((r) => Math.round((r.left + r.right) / 2 * 100) / 100)
          .sort((a, b) => a - b)
      return { chart: dashedX(svgs[0]), meds: dashedX(svgs[1]) }
    })

    if (axis.error) {
      note += `  ✗ ${axis.error}`
      problems.push(`${name}: ${axis.error}`)
    } else {
      const pairs = axis.chart.map((x, i) => [x, axis.meds[i]])
      const worst = Math.max(
        ...pairs.map(([a, b]) => (b == null ? Infinity : Math.abs(a - b))),
      )
      const ok = axis.chart.length > 0 && axis.chart.length === axis.meds.length && worst < 0.5
      note += ok
        ? `  ✓ axes aligned (${axis.chart.length} markers, max drift ${worst.toFixed(2)}px)`
        : `  ✗ AXES MISALIGNED chart=[${axis.chart}] meds=[${axis.meds}]`
      if (!ok) problems.push(`${name}: axes misaligned`)
    }
  }

  if (errors.length) {
    note += `  ✗ ${errors.length} console error(s): ${errors[0].slice(0, 120)}`
    problems.push(`${name}: ${errors[0].slice(0, 120)}`)
  }

  console.log(`→  ${OUT}/${name}.png${note}`)
  await page.close()
}

await browser.close()
if (problems.length) {
  console.log('\nproblems:')
  for (const p of problems) console.log('  ' + p)
  process.exitCode = 1
}
