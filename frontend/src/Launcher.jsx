import { navigate } from './App'

/* Entry picker — not part of the design system, added for demoing and
 * judging: a real caregiver never sees this, they'd only ever use one device
 * as one person. It lets a laptop show any of the three surfaces without
 * resizing the window or hand-typing a URL. "Caregiver — Mobile" and
 * "Caregiver — Desktop" force that layout via a query param regardless of the
 * actual window width; the auto width-based switch (per DESIGN_SYSTEM.md §5)
 * still applies to anyone who lands on /caregiver directly.
 */
export default function Launcher() {
  return (
    <main className="co-launcher">
      <div className="co-launcher__card">
        <p className="co-launcher__eyebrow">Check On — demo picker</p>
        <h1 className="co-launcher__title">Which view?</h1>
        <div className="co-launcher__options">
          <button
            type="button"
            className="co-btn co-btn--primary co-btn--full co-btn--lg"
            onClick={() => navigate('/elder')}
          >
            Elder view
          </button>
          <button
            type="button"
            className="co-btn co-btn--outline co-btn--full co-btn--lg"
            onClick={() => navigate('/caregiver?view=mobile')}
          >
            Caregiver — Mobile
          </button>
          <button
            type="button"
            className="co-btn co-btn--outline co-btn--full co-btn--lg"
            onClick={() => navigate('/caregiver?view=desktop')}
          >
            Caregiver — Desktop
          </button>
        </div>
      </div>
    </main>
  )
}
