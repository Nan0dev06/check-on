/* Copy-rule check on rendered text — DESIGN_SYSTEM.md §8, row 9.
 *
 * `lint:copy` reads source, which catches strings this app authors. It cannot
 * catch what the backend sends: `flag.reasoning` and `notification.message` are
 * composed in Python and rendered verbatim in a few places, so a banned phrase
 * could reach the screen without appearing in any frontend file.
 *
 * This visits every screen, including each of the five flag states, and reads
 * the text actually painted. That is what "check every sentence you see, not
 * just a sample" means in a harness.
 *
 *   npm run lint:copy:runtime
 */
import { chromium } from 'playwright'

const BASE = process.env.BASE || 'http://localhost:5173'

const SCREENS = [
  { path: '/elder', name: 'E1 daily log' },
  { path: '/elder', name: 'E2 confirmation', click: 'Puffy ankles' },
  { path: '/elder/checkin', name: 'E3 weekly check-in' },
  { path: '/', name: 'C1 today' },
  { path: '/', name: 'C2 medicines', tab: 'Medicines' },
  { path: '/', name: 'C3 trend', tab: 'Trend' },
  { path: '/', name: 'C4 alerts', tab: 'Alerts' },
  { path: '/medicines/add', name: 'C5 add a medicine' },
  { path: '/flag/swollen_ankles', name: 'C6 medication-linked' },
  { path: '/flag/tired', name: 'C6 unexplained deviation' },
  { path: '/flag/dizzy', name: 'C6 within expected' },
  { path: '/flag/foggy', name: 'C6 insufficient history' },
  { path: '/flag/weak', name: 'C6 query failed' },
  { path: '/', name: 'D1 dashboard', viewport: { width: 1440, height: 940 } },
]

const BANNED = [
  /\bcleared\b/i,
  /\ball[- ]clear\b/i,
  /\bin the clear\b/i,
  /\b(?:is|are|was|were|be|been|being|remains?|stays?|seems?|appears?|looks?|feels?)\s+safe\b/i,
  /\b(?:he|she|it|they)'?s\s+safe\b/i,
  /\b(?:considered|perfectly|completely|totally)\s+safe\b/i,
  /\bsafe to (?:continue|take|keep|use|stay)\b/i,
  /\bno risk\b/i,
  /\brisk[- ]free\b/i,
  /\blow risk\b/i,
  /\bruled? out\b/i,
  /\brules out\b/i,
  /\bnothing to worry\b/i,
  /\bno (?:need to worry|cause for concern|concern)\b/i,
  /\bnothing concerning\b/i,
  /\b(?:harmless|benign|healthy|reassur\w*)\b/i,
  /\bnothing (?:wrong|serious)\b/i,
  /\bno problem\b/i,
  /\bnormal\b/i,
  /\bfine\b/i,
]

/* Negated forms are the wording the product wants, not a violation. "This does
 * not rule out a mild or underreported effect" is precisely the sentence that
 * stops a reader treating no-signal as no-risk. */
const NEGATED = /\b(?:does not|doesn't|do not|don't|cannot|can't|could not|couldn't|not|never|no)\s+(?:\w+\s+){0,2}$/i

const browser = await chromium.launch()
const problems = []
let sentences = 0

for (const screen of SCREENS) {
  await fetch(`${BASE}/api/_reset`, { method: 'POST' }).catch(() => {})
  const page = await browser.newPage({
    viewport: screen.viewport || { width: 402, height: 874 },
  })
  await page.goto(BASE + screen.path, { waitUntil: 'networkidle' })
  if (screen.tab) {
    await page.getByRole('tab', { name: screen.tab }).click()
    await page.waitForTimeout(250)
  }
  if (screen.click) {
    await page.getByRole('button', { name: screen.click }).click()
    await page.waitForTimeout(300)
  }

  // Everything painted, including inside scroll regions below the fold.
  const text = await page.evaluate(() => {
    const seen = new Set()
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT)
    let n
    while ((n = walker.nextNode())) {
      const t = n.textContent.trim()
      if (t.length > 2) seen.add(t)
    }
    return [...seen]
  })

  for (const run of text) {
    sentences += 1
    for (const re of BANNED) {
      const m = re.exec(run)
      if (!m) continue
      const before = run.slice(Math.max(0, m.index - 30), m.index)
      if (NEGATED.test(before)) continue
      problems.push(`${screen.name}: "${m[0]}" in — ${run.slice(0, 120)}`)
    }
  }

  console.log(`scanned ${screen.name.padEnd(26)} ${text.length} text runs`)
  await page.close()
}

await browser.close()

console.log('')
if (!problems.length) {
  console.log(`PASS ${sentences} rendered text runs, no banned reassurance language`)
  process.exit(0)
}
console.log(`FAIL ${problems.length} issue(s):\n`)
for (const p of [...new Set(problems)]) console.log('  ' + p)
process.exit(1)
