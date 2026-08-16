# Check On — context for frontend work

Detects **prescribing cascades**: a drug's side effect mistaken for a new
condition and treated with a second drug. `README.md` covers the detection
method; this file is what you need to build the views.

## Two separate views, not one UI behind a role flag

**Elder view** — tap-only, no typing, large icons. Six symptoms: `dizzy`,
`tired`, `foggy`, `weak`, `nauseous`, `swollen_ankles`. Plus a weekly
plain-language check-in (weight change, exhaustion, activity, walking
difficulty).

**Caregiver dashboard** — medication list **with start dates** (load-bearing,
not optional), frailty trend over time, flagged symptoms with reasoning, and
notifications.

## Five outcome states to render

`MEDICATION_LINKED`, `UNEXPLAINED_DEVIATION`, `WITHIN_EXPECTED`,
`INSUFFICIENT_HISTORY`, `QUERY_FAILED`. The last two mean *we could not
evaluate* — never style them as good news.

## Notifications

`backend/notifications.py` emits `{type, urgency, message, push, detail}`.
`urgency` is `high | low | none`. HIGH (cascade flag) and LOW (2+ consecutive
missed check-ins) must be **visually distinct** — that separation is the whole
anti-alert-fatigue requirement. `urgency: none` is feed-only: no push, no badge.

## Copy rule — non-negotiable

Never write *safe*, *cleared*, *ruled out*, *fine*, *no risk*, *nothing to worry
about*. Absence of a signal is not evidence of absence. The backend enforces
this on generated text; UI-authored strings must follow it too.

Backend is complete — don't modify `backend/` or `scripts/`.
Stack: FastAPI + React.
