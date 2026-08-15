"""Combine medication timeline + FAERS signal + frailty comparison into one outcome.

This is plain conditional logic. Nothing here is a model, nothing is fitted, and
nothing calls an LLM. The two inputs that ARE statistical each come from
elsewhere and are treated as given:
  - faers_prr.compute_prr    live disproportionality computation (not a model)
  - models/frailty_baseline_app.joblib   the trained population baseline

LANGUAGE RULE, enforced on every string this module emits:
A FAERS result that fails the Evans criteria means "no strong signal detected",
never "cleared", "safe", or "no risk". Detection power for nonspecific symptoms
in this pipeline is genuinely weak -- amlodipine + dizziness is a real, labelled
effect that scores PRR 1.86 and falls under the threshold -- so wording a
negative as reassurance would be actively misleading to a caregiver.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from faers_prr import OpenFDAError, SYMPTOM_TO_MEDDRA, compute_prr

MODEL_PATH = Path(__file__).resolve().parent.parent / "models" / "frailty_baseline_app.joblib"

# A medication counts as "recent" for this many days after it was started or
# changed. 30 days is the window the prescribing-cascade literature uses for
# temporal plausibility; it is deliberately generous because onset of things
# like drug-induced oedema or confusion is often gradual.
RECENT_CHANGE_DAYS = 30

# --- deviation rule -------------------------------------------------------
# Grounded on the NHANES residual distribution for the app-comparable score
# (see train_baseline.py output), not picked by feel.
#
# LEVEL threshold = +1.0 points above the age/sex expectation.
#   The score is an integer count of criteria, so 1.0 is the smallest
#   interpretable step: one whole extra criterion beyond typical for that
#   age and sex. Empirically it sits at the 85th percentile of the population
#   residual (85th = +1.094) and 16.0% of people exceed it at any instant.
#
# PERSISTENCE = 2 consecutive check-ins.
#   Every input is self-reported and noisy -- exhaustion is a recall item that
#   can flip week to week, and self-reported weight was noisy enough in step 1
#   to need winsorizing. A single check-in above the band is not evidence. Real
#   deviation persists; week-to-week noise does not.
#
# RATE trigger, separate from level.
#   The fitted age curve moves only 0.00023 pts/week for men and 0.00047 for
#   women. At weekly resolution the expected trajectory is effectively FLAT, so
#   any sustained rise in a person's own score is already far faster than
#   expected -- roughly 2000x the population rate. This catches someone
#   declining quickly who started low enough to still sit inside the band.
DEVIATION_POINTS = 1.0
CONSECUTIVE_REQUIRED = 2
RISE_POINTS = 1.0
RISE_WINDOW = 3


class Outcome(str, Enum):
    """The five states the caregiver UI can render.

    INSUFFICIENT_HISTORY and QUERY_FAILED are deliberately NOT folded into
    WITHIN_EXPECTED. Both mean "we could not evaluate", and reporting an
    unevaluated case as within-expected is the false-reassurance failure this
    whole module is built to avoid.
    """

    MEDICATION_LINKED = "medication_linked"
    WITHIN_EXPECTED = "within_expected"
    UNEXPLAINED_DEVIATION = "unexplained_deviation"
    INSUFFICIENT_HISTORY = "insufficient_history"
    QUERY_FAILED = "query_failed"


class FaersStatus(str, Enum):
    NOT_CHECKED = "not_checked"          # no recent med change, so never queried
    SIGNAL = "signal"                    # clears Evans criteria
    NO_STRONG_SIGNAL = "no_strong_signal"
    QUERY_FAILED = "query_failed"        # must never be read as "no signal"


class FrailtyStatus(str, Enum):
    DEVIATING = "deviating"
    WITHIN_BAND = "within_band"
    INSUFFICIENT_HISTORY = "insufficient_history"


@dataclass
class Medication:
    name: str
    started: dt.date
    change_note: str = "started"

    def days_since(self, today: dt.date) -> int:
        return (today - self.started).days

    def is_recent(self, today: dt.date) -> bool:
        return 0 <= self.days_since(today) <= RECENT_CHANGE_DAYS


@dataclass
class CheckIn:
    date: dt.date
    frailty_score: float  # 0-4, app-comparable (weight loss, exhaustion,
                          # low activity, walking difficulty)


@dataclass
class Person:
    age: int
    sex: str  # "male" | "female"


@dataclass
class DrugFinding:
    drug: str
    days_since_change: int
    status: FaersStatus
    prr: float | None = None
    cases: int | None = None
    chi2: float | None = None
    detail: str = ""


@dataclass
class FrailtyComparison:
    status: FrailtyStatus
    expected: float | None = None
    observed: float | None = None
    gap: float | None = None
    trigger: str = ""


@dataclass
class Assessment:
    outcome: Outcome
    symptom: str
    person: Person
    recent_meds: list[Medication]
    drug_findings: list[DrugFinding]
    frailty: FrailtyComparison
    reasoning: str
    caveats: list[str] = field(default_factory=list)


def expected_score(person: Person) -> float:
    """Population-expected app-comparable frailty score for this age and sex.

    This is a BASELINE TO COMPARE AGAINST, not a forecast for this individual.
    """
    import joblib

    bundle = joblib.load(MODEL_PATH)
    female = 1 if person.sex.lower().startswith("f") else 0
    # NHANES topcodes age at 80; the curve is not defined past that.
    age = min(person.age, 80)
    import pandas as pd

    x = pd.DataFrame([{"age": age, "female": female, "age_x_female": age * female}])
    return float(bundle["model"].predict(x[bundle["features"]])[0])


def compare_frailty(person: Person, checkins: list[CheckIn]) -> FrailtyComparison:
    """Is this person deviating from the population band for their age/sex?"""
    ordered = sorted(checkins, key=lambda c: c.date)
    if len(ordered) < CONSECUTIVE_REQUIRED:
        return FrailtyComparison(
            status=FrailtyStatus.INSUFFICIENT_HISTORY,
            trigger=f"only {len(ordered)} check-in(s); need at least "
                    f"{CONSECUTIVE_REQUIRED} to tell a trend from a single noisy entry",
        )

    exp = expected_score(person)
    latest = ordered[-1]
    gap = latest.frailty_score - exp

    # Trigger 1 -- sustained level above the band.
    recent = ordered[-CONSECUTIVE_REQUIRED:]
    if all(c.frailty_score - exp >= DEVIATION_POINTS for c in recent):
        return FrailtyComparison(
            status=FrailtyStatus.DEVIATING, expected=exp,
            observed=latest.frailty_score, gap=gap,
            trigger=f"{CONSECUTIVE_REQUIRED} consecutive check-ins at least "
                    f"{DEVIATION_POINTS:g} point above the expected {exp:.2f} "
                    f"for a {person.age}-year-old {person.sex}",
        )

    # Trigger 2 -- rising fast, even if still inside the band.
    if len(ordered) >= RISE_WINDOW:
        window = ordered[-RISE_WINDOW:]
        earliest = window[0].frailty_score
        later = [c.frailty_score for c in window[1:]]
        if min(later) - earliest >= RISE_POINTS:
            return FrailtyComparison(
                status=FrailtyStatus.DEVIATING, expected=exp,
                observed=latest.frailty_score, gap=gap,
                trigger=f"score rose {min(later) - earliest:+.1f} points and stayed "
                        f"up across the last {RISE_WINDOW} check-ins, against an "
                        f"expected drift of about {0.0005 * RISE_WINDOW:.4f}",
            )

    return FrailtyComparison(
        status=FrailtyStatus.WITHIN_BAND, expected=exp,
        observed=latest.frailty_score, gap=gap,
        trigger=f"latest score {latest.frailty_score:.1f} vs expected {exp:.2f} "
                f"(gap {gap:+.2f}, under the {DEVIATION_POINTS:g}-point threshold)",
    )


def check_drug(med: Medication, symptom: str, today: dt.date) -> DrugFinding:
    """Run the live FAERS disproportionality check for one recent medication."""
    try:
        result = compute_prr(med.name, symptom)
    except OpenFDAError as exc:
        return DrugFinding(
            drug=med.name, days_since_change=med.days_since(today),
            status=FaersStatus.QUERY_FAILED,
            detail=f"FAERS could not be queried ({exc}); this is not a negative result",
        )

    status = FaersStatus.SIGNAL if result.is_signal else FaersStatus.NO_STRONG_SIGNAL
    if result.is_signal:
        detail = (f"PRR {result.prr:.2f} across {result.counts.a:,} reports "
                  f"clears the Evans criteria")
    else:
        detail = (f"PRR {result.prr:.2f} across {result.counts.a:,} reports "
                  f"does not clear the Evans criteria "
                  f"({'; '.join(result.failed_criteria())})")
    return DrugFinding(
        drug=med.name, days_since_change=med.days_since(today), status=status,
        prr=result.prr, cases=result.counts.a, chi2=result.chi2, detail=detail,
    )


def assess(
    symptom: str,
    person: Person,
    medications: list[Medication],
    checkins: list[CheckIn],
    today: dt.date | None = None,
) -> Assessment:
    """Combine the medication timeline, FAERS, and the frailty band into one outcome."""
    today = today or dt.date.today()
    if symptom not in SYMPTOM_TO_MEDDRA:
        raise KeyError(f"unknown symptom {symptom!r}; "
                       f"known: {sorted(SYMPTOM_TO_MEDDRA)}")

    # A. Anything started or changed in the last 30 days?
    recent = [m for m in medications if m.is_recent(today)]

    # B. FAERS only runs when there is a recent change to explain the symptom.
    findings = [check_drug(m, symptom, today) for m in recent]

    # C. Frailty comparison always runs, independently of A and B.
    frailty = compare_frailty(person, checkins)

    # D. Combine.
    signals = [f for f in findings if f.status is FaersStatus.SIGNAL]
    failed = [f for f in findings if f.status is FaersStatus.QUERY_FAILED]
    caveats: list[str] = []

    # Precedence. QUERY_FAILED outranks UNEXPLAINED_DEVIATION on purpose: we
    # cannot call a symptom "unexplained" when the medication arm never
    # successfully ran -- the medication may well be the explanation.
    label = symptom.replace("_", " ")
    if signals:
        outcome = Outcome.MEDICATION_LINKED
        names = ", ".join(f"{f.drug} (started {f.days_since_change} days ago)"
                          for f in signals)
        reasoning = (
            f"{label} was logged, and {names} was started or changed within the "
            f"last {RECENT_CHANGE_DAYS} days. In FDA adverse event reports this "
            f"symptom is reported disproportionately often for that medication "
            f"({signals[0].detail}). This is worth mentioning before any new "
            f"prescription is added to treat the symptom."
        )
    elif failed:
        outcome = Outcome.QUERY_FAILED
        reasoning = (
            f"{label} was logged after a recent medication change, but the FDA "
            f"adverse event database could not be reached for "
            f"{', '.join(f.drug for f in failed)}, so the medication check did not "
            f"run. We do not yet know whether the two are connected."
        )
    elif frailty.status is FrailtyStatus.DEVIATING:
        outcome = Outcome.UNEXPLAINED_DEVIATION
        reasoning = (
            f"{label} was logged and does not line up with a recent medication "
            f"change, but the frailty check-ins are outside the usual range for "
            f"this age and sex: {frailty.trigger}. Neither explanation fits, so "
            f"this is worth a checkup."
        )
    elif frailty.status is FrailtyStatus.INSUFFICIENT_HISTORY:
        outcome = Outcome.INSUFFICIENT_HISTORY
        reasoning = (
            f"{label} was logged. {_no_med_phrase(recent, findings)} There are not "
            f"yet enough check-ins to compare against the expected range for this "
            f"age and sex ({frailty.trigger}), so there is nothing to compare "
            f"this against yet."
        )
    else:
        outcome = Outcome.WITHIN_EXPECTED
        reasoning = (
            f"{label} was logged. {_no_med_phrase(recent, findings)} "
            f"The frailty check-ins are {_band_phrase(frailty)} Keep watching."
        )

    # Caveats carry the secondary conditions that did not become the headline.
    if failed and outcome is not Outcome.QUERY_FAILED:
        caveats.append(
            "The FAERS check could not be completed for "
            + ", ".join(f.drug for f in failed)
            + ". That is a failed lookup, not a negative result."
        )
    if any(f.status is FaersStatus.NO_STRONG_SIGNAL for f in findings):
        caveats.append(
            "No strong signal was detected in FDA reports for the recent "
            "medication. This does not rule out a mild or underreported effect -- "
            "nonspecific symptoms like these are detected weakly by this method."
        )
    if (frailty.status is FrailtyStatus.INSUFFICIENT_HISTORY
            and outcome is not Outcome.INSUFFICIENT_HISTORY):
        caveats.append(
            f"The frailty comparison could not be made: {frailty.trigger}."
        )
    if person.age > 80:
        caveats.append(
            "The population baseline is built from data that groups everyone 80 "
            "and older together, so the expected value above 80 is approximate."
        )

    return Assessment(
        outcome=outcome, symptom=symptom, person=person, recent_meds=recent,
        drug_findings=findings, frailty=frailty, reasoning=reasoning,
        caveats=caveats,
    )


def _no_med_phrase(recent: list[Medication], findings: list[DrugFinding]) -> str:
    if not recent:
        return (f"No medication was started or changed in the last "
                f"{RECENT_CHANGE_DAYS} days, so there is no recent medication "
                f"change to link it to.")
    return ("No strong signal was found in FDA adverse event reports for the "
            "recently changed medication, which does not rule out a mild or "
            "underreported effect.")


def _band_phrase(frailty: FrailtyComparison) -> str:
    if frailty.status is FrailtyStatus.INSUFFICIENT_HISTORY:
        return "not yet comparable to the expected range -- there are too few check-ins."
    return (f"within the usual range for this age and sex "
            f"(latest {frailty.observed:.1f} against an expected "
            f"{frailty.expected:.2f}).")
