import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { weekday } from '../lib/format'
import DailyLog from './DailyLog'
import Confirmation from './Confirmation'
import WeeklyCheckIn from './WeeklyCheckIn'

/* The elder view has no navigation of any kind — no menu, no settings, no back
 * stack. Which of the two screens she sees is decided here, once, and never by
 * her: the weekly check-in on her check-in day, the daily log otherwise.
 *
 * The route is honoured when it is given explicitly so the check-in can be
 * opened directly, but nothing inside either screen ever links to the other.
 */
export default function ElderApp({ route }) {
  const [person, setPerson] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.person().then(setPerson).catch((e) => setError(e.message))
  }, [])

  if (error) {
    return (
      <main className="co-phone co-elder">
        <div className="co-log">
          <div className="co-log__header">
            <h1 className="co-log__title">We can&rsquo;t reach Check On.</h1>
            <p className="co-log__intro">
              Nothing has been sent. Please try again in a little while, or give
              your daughter a ring.
            </p>
          </div>
        </div>
      </main>
    )
  }

  if (!person) return <main className="co-phone co-elder" aria-busy="true" />

  if (route === 'checkin') {
    return <WeeklyCheckIn person={person} />
  }
  return <ElderDaily person={person} />
}

function ElderDaily({ person }) {
  const [logged, setLogged] = useState(null)
  const [failed, setFailed] = useState(false)

  async function tap(symptom) {
    // Show the confirmation immediately: she has done her part the moment she
    // taps, and making her wait on a network round trip would be a worse lie
    // than a retry behind the scenes.
    setLogged(symptom)
    setFailed(false)
    try {
      await api.logTap(symptom.id)
    } catch {
      setFailed(true)
    }
  }

  async function undo() {
    if (logged && !failed) {
      try {
        await api.undoTap(logged.id)
      } catch {
        /* the tap stays; Emily sees it either way */
      }
    }
    setLogged(null)
    setFailed(false)
  }

  return (
    <main className="co-phone co-elder">
      <DailyLog person={person} onTap={tap} />
      {logged && (
        <Confirmation person={person} sendFailed={failed} onDone={undo} onUndo={undo} />
      )}
    </main>
  )
}

export function greeting(todayIso, now = new Date()) {
  const hour = now.getHours()
  const part = hour < 12 ? 'morning' : hour < 18 ? 'afternoon' : 'evening'
  return { part, eyebrow: `${longWeekday(todayIso)} ${part}` }
}

const LONG_DAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday',
  'Friday', 'Saturday']

function longWeekday(iso) {
  const short = weekday(iso)
  return LONG_DAYS.find((d) => d.startsWith(short)) || short
}
