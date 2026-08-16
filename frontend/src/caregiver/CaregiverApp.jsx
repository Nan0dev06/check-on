import { useCallback, useEffect, useState } from 'react'
import { api } from '../lib/api'
import Today from './Today'
import Medicines from './Medicines'
import Trend from './Trend'
import Alerts from './Alerts'
import AddMedicine from './AddMedicine'
import FlagDetail from './FlagDetail'
import Dashboard from './desktop/Dashboard'

const TABS = [
  { id: 'today', label: 'Today' },
  { id: 'medicines', label: 'Medicines' },
  { id: 'trend', label: 'Trend' },
  { id: 'alerts', label: 'Alerts' },
]

/* Caregiver navigation: four tabs, and no stack deeper than one level.
 *
 * Three separate buttons — "See timeline" on Today, "Open the flag" on Alerts,
 * and "See the taps" on the dashboard — all push the same flag detail screen.
 * There is one of it, not three variants.
 *
 * At 1100px and above the dashboard fully replaces the tabs: Medicines and
 * Alerts get no desktop screen of their own, because the dashboard already
 * contains both. The two destinations open as centred modals over it.
 */
export default function CaregiverApp() {
  // ?view=mobile|desktop forces a layout regardless of the actual window
  // width — the demo picker's two caregiver options. Anyone who lands here
  // without it gets the real width-based switch from DESIGN_SYSTEM.md §5.
  const forcedView = new URLSearchParams(window.location.search).get('view')
  const [wide, setWide] = useState(() =>
    forcedView ? forcedView === 'desktop'
      : window.matchMedia('(min-width: 1100px)').matches,
  )
  const [tab, setTab] = useState('today')
  const [stack, setStack] = useState(readStack())
  const data = useCareData()

  useEffect(() => {
    if (forcedView) return undefined
    const mq = window.matchMedia('(min-width: 1100px)')
    const on = (e) => setWide(e.matches)
    mq.addEventListener('change', on)
    return () => mq.removeEventListener('change', on)
  }, [forcedView])

  useEffect(() => {
    const onPop = () => setStack(readStack())
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [])

  const openFlag = useCallback((flag) => {
    push(`/flag/${flag.symptom}`)
    setStack({ kind: 'flag', symptom: flag.symptom })
  }, [])

  const openAdd = useCallback(() => {
    push('/medicines/add')
    setStack({ kind: 'add' })
  }, [])

  const closeStack = useCallback(() => {
    push('/')
    setStack(null)
  }, [])

  if (data.error) return <LoadFailed message={data.error} />
  if (!data.ready) return <Loading />

  const overlay =
    stack?.kind === 'flag' ? (
      <FlagDetail
        symptom={stack.symptom}
        data={data}
        onBack={closeStack}
        asModal={wide}
      />
    ) : stack?.kind === 'add' ? (
      <AddMedicine data={data} onClose={closeStack} asModal={wide} />
    ) : null

  if (wide) {
    return (
      <>
        <Dashboard data={data} onOpenFlag={openFlag} onAddMedicine={openAdd} />
        {overlay}
      </>
    )
  }

  if (overlay) return overlay

  return (
    <main className="co-phone">
      {tab === 'today' && (
        <Today data={data} onOpenFlag={openFlag} />
      )}
      {tab === 'medicines' && (
        <Medicines data={data} onAdd={openAdd} />
      )}
      {tab === 'trend' && <Trend data={data} />}
      {tab === 'alerts' && <Alerts data={data} onOpenFlag={openFlag} />}

      <nav className="co-tabs" role="tablist" aria-label="Sections">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={tab === t.id}
            className={`co-tabs__tab${tab === t.id ? ' co-tabs__tab--on' : ''}`}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </nav>
    </main>
  )
}

/* --- data ---------------------------------------------------------------- */

function useCareData() {
  const [state, setState] = useState({ ready: false, error: null })

  const load = useCallback(async () => {
    try {
      const [person, flags, medications, trend, notifications, doctorList] =
        await Promise.all([
          api.person(),
          api.flags(),
          api.medications(),
          api.trend(),
          api.notifications(),
          api.doctorList(),
        ])
      setState({
        ready: true,
        error: null,
        person,
        flags,
        medications,
        trend,
        notifications,
        doctorList,
      })
    } catch (e) {
      setState({ ready: false, error: e.message })
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const recheck = useCallback(async (flag) => {
    // Re-runs that one check live. It may fail again, and if it does the card
    // is left exactly as it was — never optimistically rendered as settled.
    try {
      await api.recheck(flag.symptom)
    } catch {
      /* keep the failed state */
    }
    await load()
  }, [load])

  // The count in the masthead is the server's, not a local tally. A tally that
  // only ever increments would keep counting on a failed write and survive a
  // reload it should not have.
  const addToDoctorList = useCallback(async (flag) => {
    try {
      const res = await api.addToDoctorList(flag.tile_label)
      setState((s) => ({ ...s, doctorList: res }))
      return true
    } catch {
      return false
    }
  }, [])

  return { ...state, reload: load, recheck, addToDoctorList }
}

/* The first load after a deploy or a cold start recomputes every assessment
 * against openFDA, which takes tens of seconds. An empty frame for that long
 * reads as a broken app, and — worse for this product — an empty frame is
 * indistinguishable from a calm result. It says what is happening instead. */
function Loading() {
  return (
    <main className="co-phone" aria-busy="true">
      <div className="co-cg__header">
        <h1 className="co-cg__title">Running the checks…</h1>
        <p className="co-cg__sub">
          Nothing has been checked yet. This takes a moment the first time.
        </p>
      </div>
    </main>
  )
}

function LoadFailed({ message }) {
  return (
    <main className="co-phone">
      <div className="co-cg__header">
        <h1 className="co-cg__title">The checks didn’t load.</h1>
        <p className="co-cg__sub">
          Nothing has been checked yet — this is not a result.
        </p>
      </div>
      <div className="co-cg__scroll">
        <p className="co-help">{message}</p>
      </div>
    </main>
  )
}

/* --- routing helpers ----------------------------------------------------- */

function readStack() {
  const p = window.location.pathname
  if (p.startsWith('/flag/')) return { kind: 'flag', symptom: p.slice(6) }
  if (p === '/medicines/add') return { kind: 'add' }
  return null
}

function push(to) {
  window.history.pushState({}, '', to)
}
