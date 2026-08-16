"""Demo state for Ruth Achebe and her daughter Emily.

Seeded data, not fabricated results. Every outcome the API reports is computed
by running the real `combining.assess()` over what is below -- live openFDA,
the trained frailty baseline, the real thresholds. Nothing here asserts an
outcome; the dates and answers are the inputs that produce them.

The dates are anchored to the design's reference day, Sunday 16 August 2026.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

D = dt.date

# --- the two people -------------------------------------------------------
PERSON = {
    "name": "Ruth",
    "full_name": "Ruth Achebe",
    "called": "Mum",          # what the caregiver calls her, used in her UI
    "initials": "RA",
    "age": 78,
    "sex": "female",
    "phone": "+44 7700 900412",
}
CAREGIVER = {"name": "Emily", "relationship": "daughter"}

# Ruth's own weekly check-in ritual, and the day the elder view greets her on.
CHECKIN_WEEKDAY = 4  # Friday


@dataclass
class SeedMedication:
    id: str
    name: str
    dose_value: str
    dose_unit: str
    frequency: str
    started: D
    stopped: D | None = None
    prescriber: str | None = None


@dataclass
class SeedTap:
    """One symptom the elder tapped, with the day she tapped it."""

    symptom: str
    date: D


@dataclass
class SeedCheckIn:
    date: D
    answers: dict[str, str]


MEDICATIONS: list[SeedMedication] = [
    SeedMedication("med_amlodipine", "Amlodipine", "5", "mg", "Mornings",
                   D(2026, 8, 2), prescriber="Dr Achebe"),
    SeedMedication("med_furosemide", "Furosemide", "20", "mg", "Mornings",
                   D(2026, 3, 14)),
    SeedMedication("med_levothyroxine", "Levothyroxine", "75", "mcg", "Waking",
                   D(2019, 1, 14)),
    SeedMedication("med_zopiclone", "Zopiclone", "3.75", "mg", "Evenings",
                   D(2026, 2, 12), stopped=D(2026, 7, 28)),
]

# --- what Ruth has tapped -------------------------------------------------
# Puffy ankles: once in mid-July, then four times in five days starting the
# Tuesday nine days after amlodipine. That gap is the whole argument, so the
# dates are the load-bearing part of this file.
TAPS: list[SeedTap] = [
    SeedTap("swollen_ankles", D(2026, 7, 15)),
    SeedTap("swollen_ankles", D(2026, 8, 11)),
    SeedTap("swollen_ankles", D(2026, 8, 12)),
    SeedTap("swollen_ankles", D(2026, 8, 14)),
    SeedTap("swollen_ankles", D(2026, 8, 15)),
    SeedTap("dizzy", D(2026, 8, 11)),
    SeedTap("tired", D(2026, 8, 15)),
    SeedTap("weak", D(2026, 8, 10)),
    SeedTap("foggy", D(2026, 3, 16)),
]

# --- her weekly answers ---------------------------------------------------
# Fridays from 13 March. The four answers are what she tapped; the 0-4 score
# they produce is derived by api/scoring.py, not stored here.
# The score these produce is a count of criteria, 0-4, so the resolution is
# coarse by construction -- "less than usual" energy and "now and then" activity
# both sit under their thresholds and score nothing. The names below say what
# they score, because two answer sets that read differently can score the same.
_STEADY = {"weight": "same", "energy": "plenty",           # 0
           "activity": "most_days", "walking": "steady"}
_SLOWER = {"weight": "same", "energy": "less",             # 1 -- walking
           "activity": "now_and_then", "walking": "harder"}
_TIRED = {"weight": "same", "energy": "not_much",          # 2 -- + exhaustion
          "activity": "now_and_then", "walking": "harder"}
_HOUSEBOUND = {"weight": "same", "energy": "not_much",     # 3 -- + activity
               "activity": "stayed_in", "walking": "harder"}

_WEEKLY: list[tuple[D, dict[str, str]]] = [
    (D(2026, 3, 13), _STEADY),
    (D(2026, 3, 20), _STEADY),
    (D(2026, 3, 27), _SLOWER),
    (D(2026, 4, 3), _SLOWER),
    (D(2026, 4, 10), _SLOWER),
    (D(2026, 4, 17), _SLOWER),
    (D(2026, 4, 24), _SLOWER),
    (D(2026, 5, 1), _SLOWER),
    (D(2026, 5, 8), _SLOWER),
    (D(2026, 5, 15), _SLOWER),
    (D(2026, 5, 22), _SLOWER),
    (D(2026, 5, 29), _SLOWER),
    (D(2026, 6, 5), _SLOWER),
    (D(2026, 6, 12), _SLOWER),
    (D(2026, 6, 19), _SLOWER),
    (D(2026, 6, 26), _SLOWER),
    (D(2026, 7, 3), _SLOWER),
    (D(2026, 7, 10), _SLOWER),
    (D(2026, 7, 17), _SLOWER),
    (D(2026, 7, 24), _SLOWER),
    (D(2026, 7, 31), _SLOWER),
    # The drift. Two consecutive answers a clear point above the expected 0.96
    # for a 78-year-old woman is what `compare_frailty` calls DEVIATING, and it
    # only becomes true with the 14 August answer -- which is why the dizzy tap
    # on the 11th is still WITHIN_EXPECTED and the worn-out tap on the 15th is
    # not. The two outcomes differ because of when they were checked.
    (D(2026, 8, 7), _TIRED),
    (D(2026, 8, 14), _HOUSEBOUND),
]
CHECKINS: list[SeedCheckIn] = [SeedCheckIn(d, a) for d, a in _WEEKLY]

# --- daily prompts, for the missed-check-in streak ------------------------
# notifications.missed_checkin_notification needs a prompt history. She has
# answered nothing since Friday, which is the two-in-a-row the LOW tier wants.
PROMPT_DAYS = 10


def prompts(today: D) -> list[tuple[D, bool]]:
    out = []
    for i in range(PROMPT_DAYS, -1, -1):
        day = today - dt.timedelta(days=i)
        answered = any(c.date == day for c in CHECKINS)
        out.append((day, answered))
    return out


# --- one recorded check that failed --------------------------------------
# On Monday the openFDA lookup for the weakness tap did not complete. This is a
# stored record of a check that failed, not a result: the UI renders it as
# QUERY_FAILED and its retry button re-runs `assess()` live against openFDA.
RECORDED_FAILURES: dict[str, str] = {
    "weak": "openFDA returned 503 after 5 attempts",
}

# --- non-symptom nudges ---------------------------------------------------
# These are scheduling facts, not check results. They never carry an outcome.
REMINDERS = [
    {
        "id": "nudge_prescription",
        "title": "A gentle reminder",
        "body": "Her repeat prescription is due in five days.",
        "at": "Thursday, 9:00am",
    },
]

DOCTOR_LIST_SEED: list[str] = []
