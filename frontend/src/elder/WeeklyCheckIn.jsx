import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import Confirmation from './Confirmation'

/* E3 — weekly check-in.
 *
 * One question per screen, answered by tapping. Tapping any answer advances;
 * "Back" is the only reverse affordance. Answers are not editable after
 * submission — a wrong tap costs less than a confusing edit affordance would.
 *
 * The four questions map to weight change, exhaustion, activity and gait
 * difficulty. None of those words appear on this screen, and the mapping lives
 * on the server (api/scoring.py) so it cannot leak into the copy by accident.
 */
export default function WeeklyCheckIn({ person }) {
  const [questions, setQuestions] = useState([])
  const [step, setStep] = useState(0)
  const [answers, setAnswers] = useState({})
  const [done, setDone] = useState(false)

  useEffect(() => {
    api.checkinQuestions().then(setQuestions).catch(() => setQuestions([]))
  }, [])

  if (!questions.length) return <main className="co-phone co-elder" aria-busy="true" />

  const total = questions.length

  function answer(question, value) {
    const next = { ...answers, [question.key]: value }
    setAnswers(next)
    if (step + 1 < total) {
      setStep(step + 1)
    } else {
      setDone(true)
      api.submitCheckin(next).catch(() => {
        /* the answers stay on screen; nothing is claimed about them */
      })
    }
  }

  function back() {
    if (done) setDone(false)
    else if (step > 0) setStep(step - 1)
  }

  function restart() {
    setAnswers({})
    setStep(0)
    setDone(false)
  }

  const current = questions[step]
  const filled = done ? total : step

  return (
    <main className="co-phone co-elder">
      <div className="co-checkin">
        <div
          className="co-progress"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={total}
          aria-valuenow={filled}
          aria-label={`Question ${Math.min(step + 1, total)} of ${total}`}
        >
          {questions.map((q, i) => (
            <span
              key={q.key}
              className={`co-progress__seg${i < Math.max(filled, step + 1) && (done || i <= step) ? ' co-progress__seg--on' : ''}`}
            />
          ))}
        </div>

        {done ? (
          <Confirmation
            person={person}
            standalone
            title={`That's everything, ${person.name}.`}
            body={`${person.caregiver.name} will check on you again next Friday. Nothing to do until then.`}
            action={
              <button type="button" className="co-thanks__undo" onClick={restart}>
                Start over
              </button>
            }
          />
        ) : (
          <>
            <div className="co-checkin__block">
              <p className="co-checkin__eyebrow">{current.eyebrow}</p>
              <h1 className="co-checkin__question">{current.question}</h1>
            </div>

            <div
              className="co-checkin__answers"
              role="group"
              aria-label={current.question}
            >
              {current.answers.map((a) => (
                <button
                  key={a.value}
                  type="button"
                  className={`co-answer${a.declined ? ' co-answer--declined' : ''}`}
                  onClick={() => answer(current, a.value)}
                >
                  {a.label}
                </button>
              ))}
            </div>
          </>
        )}

        <div className="co-checkin__footer">
          <button
            type="button"
            className="co-checkin__back"
            onClick={back}
            disabled={step === 0 && !done}
            style={step === 0 && !done ? { visibility: 'hidden' } : undefined}
          >
            Back
          </button>
          <span className="co-checkin__note">Four questions, once a week</span>
        </div>
      </div>
    </main>
  )
}
