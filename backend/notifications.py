"""Notification tiering: what reaches the caregiver, and how loudly.

The point of this module is alert fatigue. A caregiver who gets pinged for
every logged symptom stops reading the pings, and then the one that matters --
a possible prescribing cascade -- gets swiped away with the rest. So the tiers
are deliberately unequal:

  HIGH  cascade flag        push, visually distinct, "needs attention"
  LOW   missed check-ins    push, gentle, and only after a STREAK of 2+
  NONE  everything else     dashboard feed only, never pushed

Two rules carry most of the weight:

1. A single missed check-in is NOT a notification. Older adults skip a day.
   Only 2+ CONSECUTIVE misses indicate a pattern worth nudging about, and the
   streak resets the moment they respond.

2. INSUFFICIENT_HISTORY and QUERY_FAILED never push. Both mean "we could not
   evaluate", and pushing an alert that carries no finding trains the caregiver
   to ignore the channel. They belong in the feed so the state is visible
   without demanding attention.

This module is pure data. It emits Notification objects with a type, an
urgency, a message and structured detail; every rendering decision -- icon,
colour, sound, grouping, ordering -- belongs to the UI layer.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from enum import Enum

from combining import Assessment, FaersStatus, Outcome
# Single source of truth for symptom wording; duplicating it here would drift.
from triage_summary import label_for

# A single miss is normal. Two in a row is a pattern.
MISSED_STREAK_THRESHOLD = 2


class Urgency(str, Enum):
    HIGH = "high"    # needs attention
    LOW = "low"      # gentle nudge
    NONE = "none"    # feed only, no push


class NotificationType(str, Enum):
    CASCADE_FLAG = "cascade_flag"            # HIGH
    MISSED_CHECKINS = "missed_checkins"      # LOW
    NEEDS_MORE_DATA = "needs_more_data"      # feed  (INSUFFICIENT_HISTORY)
    CHECK_UNAVAILABLE = "check_unavailable"  # feed  (QUERY_FAILED)
    ROUTINE = "routine"                      # feed  (WITHIN_EXPECTED)


@dataclass
class Notification:
    type: NotificationType
    urgency: Urgency
    message: str
    push: bool
    detail: dict = field(default_factory=dict)


def _pushes(urgency: Urgency) -> bool:
    """HIGH and LOW reach the caregiver; NONE sits in the feed."""
    return urgency in (Urgency.HIGH, Urgency.LOW)


# outcome -> (type, urgency). WITHIN_EXPECTED was not specified in the tiering
# brief; it is treated as feed-only for the same reason as the other two
# non-findings -- there is nothing for the caregiver to act on.
_ROUTING: dict[Outcome, tuple[NotificationType, Urgency]] = {
    Outcome.MEDICATION_LINKED: (NotificationType.CASCADE_FLAG, Urgency.HIGH),
    Outcome.UNEXPLAINED_DEVIATION: (NotificationType.CASCADE_FLAG, Urgency.HIGH),
    Outcome.INSUFFICIENT_HISTORY: (NotificationType.NEEDS_MORE_DATA, Urgency.NONE),
    Outcome.QUERY_FAILED: (NotificationType.CHECK_UNAVAILABLE, Urgency.NONE),
    Outcome.WITHIN_EXPECTED: (NotificationType.ROUTINE, Urgency.NONE),
}


@dataclass
class CheckInPrompt:
    """One scheduled daily prompt and whether the person answered it."""

    date: dt.date
    responded: bool


def consecutive_missed(prompts: list[CheckInPrompt]) -> int:
    """How many of the most recent prompts in a row went unanswered.

    Counts backwards from the newest prompt and stops at the first response --
    answering once resets the streak, which is the behaviour we want.
    """
    streak = 0
    for p in sorted(prompts, key=lambda p: p.date, reverse=True):
        if p.responded:
            break
        streak += 1
    return streak


def _default_message(a: Assessment) -> str:
    """Deterministic message when no LLM triage sentence is supplied."""
    symptom = label_for(a.symptom).capitalize()
    signal = next((f for f in a.drug_findings
                   if f.status is FaersStatus.SIGNAL), None)

    if a.outcome is Outcome.MEDICATION_LINKED and signal:
        return (f"{symptom} was logged, and {signal.drug} was started "
                f"{signal.days_since_change} days ago. Worth asking the doctor "
                f"about before anything new is prescribed for it.")
    if a.outcome is Outcome.UNEXPLAINED_DEVIATION:
        return (f"{symptom} was logged, and the recent check-ins have moved "
                f"outside the usual range for this age. Worth mentioning at "
                f"the next appointment.")
    if a.outcome is Outcome.INSUFFICIENT_HISTORY:
        return (f"{symptom} was logged. There are not enough check-ins yet to "
                f"compare it against anything.")
    if a.outcome is Outcome.QUERY_FAILED:
        return (f"{symptom} was logged after a recent medication change, but "
                f"the medication database could not be reached, so that check "
                f"still needs to be run.")
    return (f"{symptom} was logged and did not stand out against the recent "
            f"check-ins.")


def notification_for(a: Assessment,
                     summary_sentence: str | None = None) -> Notification:
    """Build the notification for one logged symptom.

    `summary_sentence` is the LLM triage sentence when one was generated; the
    deterministic message is used otherwise. This module never calls a model.
    """
    ntype, urgency = _ROUTING[a.outcome]
    detail: dict = {
        "outcome": a.outcome.value,
        "symptom": a.symptom,
        "recent_medications": [m.name for m in a.recent_meds],
    }
    signal = next((f for f in a.drug_findings
                   if f.status is FaersStatus.SIGNAL), None)
    if signal:
        detail["implicated_drug"] = signal.drug
        detail["days_since_change"] = signal.days_since_change
    if a.frailty.expected is not None:
        detail["frailty_expected"] = round(a.frailty.expected, 3)
        detail["frailty_observed"] = a.frailty.observed

    return Notification(
        type=ntype,
        urgency=urgency,
        message=summary_sentence or _default_message(a),
        push=_pushes(urgency),
        detail=detail,
    )


def missed_checkin_notification(
    prompts: list[CheckInPrompt],
) -> Notification | None:
    """LOW-urgency nudge, only once 2+ consecutive prompts have gone unanswered.

    Returns None below the threshold -- including for a single miss, which is
    the whole point of the rule. Re-notification across days (whether a streak
    of 4 should ping again after the streak of 3 already did) is a delivery
    concern; `detail["consecutive_missed"]` is provided so the caller can
    de-duplicate.
    """
    streak = consecutive_missed(prompts)
    if streak < MISSED_STREAK_THRESHOLD:
        return None

    ordered = sorted(prompts, key=lambda p: p.date)
    missed = [p.date for p in ordered[-streak:]]
    return Notification(
        type=NotificationType.MISSED_CHECKINS,
        urgency=Urgency.LOW,
        message=(f"There have been {streak} daily check-ins in a row without a "
                 f"response. A gentle nudge may help."),
        push=True,
        detail={
            "consecutive_missed": streak,
            "threshold": MISSED_STREAK_THRESHOLD,
            "missed_dates": [d.isoformat() for d in missed],
        },
    )


def evaluate(
    assessment: Assessment | None = None,
    prompts: list[CheckInPrompt] | None = None,
    summary_sentence: str | None = None,
) -> list[Notification]:
    """All notifications arising from the current state, highest urgency first.

    A cascade flag and a missed-check-in streak are independent and can both be
    present; a cascade flag fires regardless of check-in history.
    """
    out: list[Notification] = []
    if assessment is not None:
        out.append(notification_for(assessment, summary_sentence))
    if prompts:
        nudge = missed_checkin_notification(prompts)
        if nudge is not None:
            out.append(nudge)

    order = {Urgency.HIGH: 0, Urgency.LOW: 1, Urgency.NONE: 2}
    return sorted(out, key=lambda n: order[n.urgency])
