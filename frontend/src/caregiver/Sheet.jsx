import { useEffect, useRef } from 'react'

/* One container for both destination screens.
 *
 * On the phone it is the screen. At browser width it is a centred modal over
 * the dashboard at ~440px, reusing the phone layout rather than a second
 * design — which is why C5 and C6 don't know which one they are in.
 *
 * The modal is a real <dialog>, so the browser gives us the focus trap, the
 * inert background and Escape for free instead of three hand-rolled effects.
 */
export default function Sheet({ asModal, onClose, label, children }) {
  const dialog = useRef(null)

  useEffect(() => {
    if (!asModal) return undefined
    const el = dialog.current
    el?.showModal()
    const onCancel = (e) => {
      e.preventDefault()
      onClose()
    }
    el?.addEventListener('cancel', onCancel)
    return () => {
      el?.removeEventListener('cancel', onCancel)
      el?.close()
    }
  }, [asModal, onClose])

  if (!asModal) {
    return <main className="co-phone">{children}</main>
  }

  return (
    <dialog className="co-modal" ref={dialog} aria-label={label}>
      <div className="co-modal__panel">{children}</div>
    </dialog>
  )
}
