/* Copy-rule lint — DESIGN_SYSTEM.md §8.
 *
 * The ban is a product-safety constraint, not a tone preference: Check On never
 * claims something is safe when it only means no signal was found. It applies
 * to every string the app can render, including placeholder and seed copy, so
 * this reads the source rather than the running page.
 *
 *   npm run lint:copy
 *
 * It scans user-visible text only — JSX text nodes, string literals, and the
 * copy in the API's Python — and skips comments, because a comment explaining
 * *why* "safe" is banned would otherwise trip the check that enforces it.
 *
 * Exits non-zero on a hit, so it can gate a build.
 */
import { readdir, readFile } from 'node:fs/promises'
import { join, relative } from 'node:path'

const ROOT = new URL('..', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1')
const REPO = join(ROOT, '..')

const SCAN = [
  { dir: join(ROOT, 'src'), exts: ['.jsx', '.js'] },
  { dir: join(REPO, 'api'), exts: ['.py'] },
]

/* Word-boundary matched so "safety" and "finely" don't trip "safe" / "fine",
 * but "is safe", "all clear" and "ruled out" all do. */
const BANNED = [
  { word: 'safe', re: /\bsafe(ly|r|st)?\b/gi },
  { word: 'cleared', re: /\bclear(ed|s)?\b/gi },
  { word: 'no risk', re: /\bno risk\b/gi },
  { word: 'ruled out', re: /\bruled?\s+out\b/gi },
  { word: 'all clear', re: /\ball[- ]clear\b/gi },
  { word: 'normal', re: /\bnormal(ly)?\b/gi },
  { word: 'fine', re: /\bfine\b/gi },
  { word: 'healthy', re: /\bhealthy\b/gi },
]

/* Reduce a file to only the text a user could read: string literals and JSX
 * text nodes, with comments removed first.
 *
 * Scanning raw source instead produces false positives on identifiers —
 * `assessments.clear()` is not a claim about anything — and a lint that cries
 * wolf on a method name is a lint people start ignoring, which would defeat
 * the rule it exists to protect. Line numbers are preserved so a real hit is
 * still reported where it lives.
 */
function extractText(source, ext) {
  const lines = source.split('\n')
  const out = new Array(lines.length).fill('')

  const withoutComments = source
    .replace(ext === '.py' ? /(?:"""[\s\S]*?"""|'''[\s\S]*?''')/g : /\/\*[\s\S]*?\*\//g,
      (m) => m.replace(/[^\n]/g, ' '))
    .replace(ext === '.py' ? /^[ \t]*#.*$/gm : /^[ \t]*\/\/.*$/gm,
      (m) => ' '.repeat(m.length))

  const patterns = ext === '.py'
    ? [/(['"])(?:\\.|(?!\1)[^\\\n])*\1/g]
    : [
        /(['"])(?:\\.|(?!\1)[^\\\n])*\1/g, // quoted strings
        /`(?:\\.|[^\\`])*`/g, // template literals
        />([^<>{}]*[A-Za-z]{3}[^<>{}]*)</g, // JSX text nodes
      ]

  for (const re of patterns) {
    let m
    re.lastIndex = 0
    while ((m = re.exec(withoutComments)) !== null) {
      const line = withoutComments.slice(0, m.index).split('\n').length - 1
      out[line] += ' ' + m[0]
      if (m[0].length === 0) re.lastIndex += 1
    }
  }
  return out.join('\n')
}

/* Test files are skipped. A suite that asserts on the ban has to name the
 * banned words to do it, and flagging its own fixture list would make the lint
 * unusable — the same false-positive class as `assessments.clear()`. Their
 * strings are never rendered; `lint:copy:runtime` covers what actually is. */
const isTest = (name) => /^test_|\.test\.|\.spec\./.test(name)

async function* walk(dir, exts) {
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const p = join(dir, entry.name)
    if (entry.isDirectory()) {
      if (['node_modules', 'shots', '__pycache__', '.git'].includes(entry.name)) continue
      yield* walk(p, exts)
    } else if (exts.some((e) => entry.name.endsWith(e)) && !isTest(entry.name)) {
      yield p
    }
  }
}

const hits = []
let files = 0

for (const { dir, exts } of SCAN) {
  for await (const file of walk(dir, exts)) {
    files += 1
    const raw = await readFile(file, 'utf8')
    const text = extractText(raw, file.slice(file.lastIndexOf('.')))
    const lines = text.split('\n')
    for (const { word, re } of BANNED) {
      lines.forEach((line, i) => {
        re.lastIndex = 0
        const m = re.exec(line)
        if (m) {
          hits.push({
            file: relative(REPO, file),
            line: i + 1,
            word,
            found: m[0],
            text: line.trim().slice(0, 110),
          })
        }
      })
    }
  }
}

console.log(`copy-lint: ${files} files scanned against ${BANNED.length} banned terms`)

if (!hits.length) {
  console.log('✓ no banned reassurance language in renderable copy')
  process.exit(0)
}

console.log(`\n✗ ${hits.length} banned term(s):\n`)
for (const h of hits) {
  console.log(`  ${h.file}:${h.line}  "${h.found}" (${h.word})`)
  console.log(`      ${h.text}\n`)
}
console.log(
  'Use instead: "no strong signal", "worth watching", "within her usual pattern",\n' +
  '"still learning the pattern", "worth asking the doctor", "this is not a result".',
)
process.exit(1)
