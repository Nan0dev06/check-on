import { useEffect, useState } from 'react'
import ElderApp from './elder/ElderApp'
import CaregiverApp from './caregiver/CaregiverApp'

/* Two products, not one UI behind a role flag.
 *
 * They are separate entry points that share tokens and copy rules and nothing
 * else — no shared shell, no shared navigation, no component that renders
 * differently depending on who is holding the phone. The router here exists
 * only to pick which of the two applications is mounted.
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
  return <CaregiverApp />
}

/** Push a path without a router dependency. */
export function navigate(to) {
  window.history.pushState({}, '', to)
  window.dispatchEvent(new PopStateEvent('popstate'))
}
