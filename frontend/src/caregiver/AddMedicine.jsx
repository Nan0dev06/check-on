import { useEffect, useRef, useState } from 'react'
import { api } from '../lib/api'
import { ageLabel, monoDate } from '../lib/format'
import Sheet from './Sheet'

/* C5 — Add a medicine. The one caregiver screen with real text input.
 *
 * Two things gate Save, and they are the two the interaction check cannot run
 * without: a name matched against the drug dictionary, and a start date. Dose
 * is optional. The match is a real openFDA lookup, not a text filter, because
 * the PRR query needs a canonical name — free text alone would silently produce
 * a check that never ran.
 *
 * Saving re-runs the check across every symptom already logged. A medicine
 * added today can retrospectively explain a tap from last week, which is the
 * whole point of the screen.
 */
const UNITS = ['mg', 'mcg', 'ml']
const FREQUENCIES = ['Mornings', 'Evenings', 'Twice a day', 'As needed']

export default function AddMedicine({ data, onClose, asModal }) {
  const [name, setName] = useState('')
  const [match, setMatch] = useState(null)
  const [suggestions, setSuggestions] = useState([])
  const [picked, setPicked] = useState(false)
  const [checking, setChecking] = useState(false)
  const [dose, setDose] = useState('')
  const [unit, setUnit] = useState('mg')
  const [frequency, setFrequency] = useState('Mornings')
  const [started, setStarted] = useState('')
  const [prescriber, setPrescriber] = useState('')
  const [saving, setSaving] = useState(false)
  const dateInput = useRef(null)

  const today = data.person.today

  // Resolving the name is a network call, so it is debounced rather than fired
  // per keystroke. Suggestions and the match run together: the list is how she
  // finds the canonical name, the match is what unlocks Save.
  useEffect(() => {
    const q = name.trim()
    if (q.length < 3 || picked) {
      setMatch(picked ? match : null)
      setSuggestions([])
      return undefined
    }
    setChecking(true)
    const id = setTimeout(async () => {
      try {
        const [m, s] = await Promise.all([api.matchDrug(q), api.suggestDrugs(q)])
        setMatch(m)
        setSuggestions(
          s.suggestions.filter((x) => x.name.toLowerCase() !== q.toLowerCase()),
        )
      } catch {
        setMatch({ matched: false })
        setSuggestions([])
      } finally {
        setChecking(false)
      }
    }, 350)
    return () => clearTimeout(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [name, picked])

  const matched = !!match?.matched
  const canSave = matched && !!started && !saving

  async function save() {
    if (!canSave) return
    setSaving(true)
    try {
      await api.addMedication({
        name: name.trim(),
        dose_value: dose,
        dose_unit: unit,
        frequency,
        started,
        prescriber,
      })
      await data.reload()
      onClose()
    } finally {
      setSaving(false)
    }
  }

  return (
    <Sheet asModal={asModal} onClose={onClose} label="Add a medicine">
      <div className="co-modalbar">
        <button type="button" className="co-modalbar__action" onClick={onClose}>
          Cancel
        </button>
        <h1 className="co-modalbar__title">Add a medicine</h1>
        <button
          type="button"
          className="co-modalbar__action"
          onClick={save}
          disabled={!canSave}
        >
          Save
        </button>
      </div>

      <div className="co-scroll co-stack co-form">
        <div className="co-field">
          <label className="co-eyebrow" htmlFor="med-name">Name</label>
          <div className={`co-input${matched ? ' co-input--active' : ''}`}>
            <input
              id="med-name"
              className="co-bare"
              value={name}
              onChange={(e) => {
                setPicked(false)
                setName(e.target.value)
              }}
              placeholder="Start typing"
              autoComplete="off"
              spellCheck="false"
              aria-describedby="med-name-help"
            />
            <span className="co-input__badge" aria-live="polite">
              {checking ? 'CHECKING' : matched ? 'MATCHED' : ''}
            </span>
          </div>

          {suggestions.length > 0 && (
            <ul className="co-suggest" aria-label="Matching medicines">
              {suggestions.map((s) => (
                <li key={s.name}>
                  <button
                    type="button"
                    className="co-suggest__row"
                    style={{ width: '100%' }}
                    onClick={() => {
                      setName(s.name)
                      setMatch({ matched: true, report_count: s.reports })
                      setSuggestions([])
                      setPicked(true)
                    }}
                  >
                    {s.name}
                  </button>
                </li>
              ))}
            </ul>
          )}

          {match && !match.matched && name.trim().length >= 3 && !checking && (
            <p className="co-help" id="med-name-help">
              No entry under that name in the interaction data. The check needs a
              name it recognises, so try the name printed on the box.
            </p>
          )}
          {matched && (
            <p className="co-help" id="med-name-help">
              Matched against {match.report_count.toLocaleString()} reports in the
              interaction data.
            </p>
          )}
        </div>

        <div className="co-field">
          <span className="co-eyebrow">Dose</span>
          <div className="co-dose">
            <input
              className="co-dose__value"
              value={dose}
              onChange={(e) => setDose(e.target.value)}
              inputMode="decimal"
              aria-label="Dose amount"
              placeholder="5"
            />
            <div className="co-choices" role="group" aria-label="Unit">
              {UNITS.map((u) => (
                <button
                  key={u}
                  type="button"
                  className={`co-choice${u === unit ? ' co-choice--on' : ''}`}
                  aria-pressed={u === unit}
                  onClick={() => setUnit(u)}
                >
                  {u}
                </button>
              ))}
            </div>
          </div>
          <div className="co-choices co-choices--pad" role="group" aria-label="How often">
            {FREQUENCIES.map((f) => (
              <button
                key={f}
                type="button"
                className={`co-choice co-choice--pill${f === frequency ? ' co-choice--on' : ''}`}
                aria-pressed={f === frequency}
                onClick={() => setFrequency(f)}
              >
                {f}
              </button>
            ))}
          </div>
        </div>

        <div className="co-field">
          <div className="co-field__label">
            <span className="co-eyebrow" id="start-date-label">Start date</span>
            <span className="co-hand" style={{ fontSize: 18 }}>
              this is the field that does the work
            </span>
          </div>
          <button
            type="button"
            className="co-startdate"
            onClick={() => dateInput.current?.showPicker?.()}
            aria-labelledby="start-date-label"
          >
            <span
              className={`co-startdate__value${started ? '' : ' co-startdate__value--empty'}`}
            >
              {started ? monoDate(started) : 'NOT SET'}
            </span>
            <span className="co-startdate__age">
              {started ? ageLabel(started, today) : ''}
            </span>
          </button>
          <input
            ref={dateInput}
            type="date"
            className="co-visually-hidden"
            value={started}
            max={today}
            onChange={(e) => setStarted(e.target.value)}
            aria-labelledby="start-date-label"
          />
          <div className="co-choices">
            <button
              type="button"
              className="co-choice co-choice--chip"
              onClick={() => setStarted(today)}
            >
              Today
            </button>
            <button
              type="button"
              className="co-choice co-choice--chip"
              onClick={() => setStarted(shift(today, -1))}
            >
              Yesterday
            </button>
            <button
              type="button"
              className="co-choice co-choice--chip"
              onClick={() => dateInput.current?.showPicker?.()}
            >
              Pick a date
            </button>
          </div>
          <p className="co-help">
            If you’re not sure of the exact day, the week it started is enough for
            the check to work.
          </p>
        </div>

        <div className="co-field">
          <label className="co-eyebrow" htmlFor="med-presc">Prescribed by</label>
          <input
            id="med-presc"
            className="co-input"
            value={prescriber}
            onChange={(e) => setPrescriber(e.target.value)}
            placeholder="Dr Achebe · optional"
          />
        </div>
      </div>

      <div className="co-stickyfoot co-stickyfoot--stacked">
        <button
          type="button"
          className="co-btn co-btn--primary co-btn--full co-btn--lg"
          onClick={save}
          disabled={!canSave}
        >
          {saving ? 'Running the check…' : 'Save medicine'}
        </button>
        <p className="co-stickyfoot__note">
          Saving re-runs the check against everything she’s logged.
        </p>
      </div>
    </Sheet>
  )
}

function shift(iso, days) {
  const [y, m, d] = iso.split('-').map(Number)
  const dt = new Date(y, m - 1, d + days)
  const p = (n) => String(n).padStart(2, '0')
  return `${dt.getFullYear()}-${p(dt.getMonth() + 1)}-${p(dt.getDate())}`
}
