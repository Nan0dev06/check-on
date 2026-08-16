import { useEffect, useState } from 'react'
import ElderApp from './elder/ElderApp'
import CaregiverApp from './caregiver/CaregiverApp'
import Launcher from './Launcher'

/* Two products, not one UI behind a role flag.
 *
 * They are separate entry points that share tokens and copy rules and nothing
 * else — no shared shell, no shared navigation, no component that renders
 * differently depending on who is holding the phone. The router here exists
 * only to pick which of the two applications is mounted.
 *
 * The root path is a picker rather than a direct entry, for the demo/judging
 * context only. Any real caregiver would be sent a direct link
 * (checkon.app/mum), never the picker.
 */
export default function App() {
  const [path, setPath] = useState(window.location.pathname)

  useEffect(() => {
    const onPop = () => setPath(window.location.pathname)
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [])

  if (path.startsWith('/elder')) {
    return <ElderApp route={path.endsWith('/checkin') ? 'checkin' : 'log'} />
  }
  if (path === '/') {
    return <Launcher />
  }
  return <CaregiverApp />
}

/** Push a path without a router dependency. */
export function navigate(to) {
  window.history.pushState({}, '', to)
  window.dispatchEvent(new PopStateEvent('popstate'))
}
