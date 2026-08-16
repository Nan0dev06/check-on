import { useEffect, useRef } from 'react'
import { IconCheck } from '../ui/Icons'

/* E2 — post-tap confirmation.
 *
 * No timer and no auto-dismiss: she ends the interaction herself. Both exits
 * return to E1, and "I tapped that by mistake" genuinely removes the tap rather
 * than just closing the screen.
 */
export default function Confirmation({
  person,
  onDone,
  onUndo,
  sendFailed = false,
  standalone = false,
  title,
  body,
  action,
}) {
  const heading = useRef(null)

  // The overlay replaces the whole screen, so focus has to follow it or a
  // keyboard or screen-reader user is left behind on the tiles underneath.
  useEffect(() => {
    heading.current?.focus()
  }, [])

  return (
    <section
      className={`co-thanks${standalone ? ' co-thanks--static' : ''}`}
      role="status"
      aria-live="polite"
    >
      <div className="co-thanks__mark">
        <IconCheck />
      </div>
      <h1 className="co-thanks__title" tabIndex={-1} ref={heading}>
        {title || `Thank you, ${person.name}.`}
      </h1>
      <p className="co-thanks__body">
        {body ||
          `${person.caregiver.name} will see this when she checks on you later. You don’t need to do anything else.`}
      </p>

      {sendFailed && (
        <p className="co-thanks__body">
          It hasn&rsquo;t reached {person.caregiver.name} yet. Check On will keep
          trying.
        </p>
      )}

      {onUndo && (
        <button type="button" className="co-thanks__undo" onClick={onUndo}>
          I tapped that by mistake
        </button>
      )}

      {action ||
        (onDone && (
          <button type="button" className="co-thanks__done" onClick={onDone}>
            Done
          </button>
        ))}
    </section>
  )
}
