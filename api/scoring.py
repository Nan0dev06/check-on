"""Turn the elder's four plain-speech answers into the app-comparable frailty score.

The backend's baseline model predicts `frailty_score_app`, the 4-of-5 Fried
adaptation defined in `scripts/score_frailty.py`: weight loss, exhaustion, low
activity, and walking difficulty (slowness). The weekly check-in asks exactly
those four things in plain speech, so this module is the translation layer and
nothing more -- it does not decide anything.

Each mapping below points at the criterion definition it reproduces. Where an
answer sits between two NHANES levels the conservative reading is taken, because
inflating the score would push someone over the deviation threshold on wording
alone.
"""

from __future__ import annotations

# Q1 -> crit_weight_loss. Fried: unintentional loss of >=5% body weight.
# Clothes feeling looser is the plain-speech proxy; tighter and unchanged are
# both negative, and a declined answer is unknown rather than zero.
WEIGHT = {"same": 0, "looser": 1, "tighter": 0, "declined": None}

# Q2 -> crit_exhaustion. NHANES DPQ040 >= 2 means "more than half the days".
# "Less than usual" is a milder statement than that, so it does not meet it.
ENERGY = {"plenty": 0, "less": 0, "not_much": 1}

# Q3 -> crit_low_activity. The criterion is *no* reported moderate activity at
# all, so "now and then" is negative.
ACTIVITY = {"most_days": 0, "now_and_then": 0, "stayed_in": 1}

# Q4 -> crit_slowness. NHANES PFQ061B >= 2 is "some difficulty" or worse.
WALKING = {"steady": 0, "harder": 1, "holding_on": 1}

MAPS = {"weight": WEIGHT, "energy": ENERGY, "activity": ACTIVITY, "walking": WALKING}


def score_answers(answers: dict[str, str]) -> float | None:
    """0-4 app-comparable score, or None if any criterion could not be scored.

    Returning None matches `score_frailty.py`, which leaves the total NaN when a
    criterion is missing rather than treating an unknown as a zero.
    """
    total = 0
    for key, table in MAPS.items():
        value = answers.get(key)
        if value not in table:
            return None
        crit = table[value]
        if crit is None:
            return None
        total += crit
    return float(total)
