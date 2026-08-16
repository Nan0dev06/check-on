"""In-memory state plus the bridge to backend/.

Everything statistical is delegated. This module owns storage, grouping and
serialisation; it decides nothing. In particular it never invents an outcome --
`combining.assess()` is the only thing that produces one.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from combining import (  # noqa: E402
    CheckIn,
    FaersStatus,
    Medication,
    Outcome,
    Person,
    assess,
    expected_score,
)
from faers_prr import OpenFDAError, SYMPTOM_TO_MEDDRA, resolve_drug  # noqa: E402
from notifications import (  # noqa: E402
    CheckInPrompt,
    Notification,
    Urgency,
    missed_checkin_notification,
    notification_for,
)
from triage_summary import label_for  # noqa: E402

from . import seed  # noqa: E402
from .scoring import score_answers  # noqa: E402

CACHE_PATH = ROOT / "api" / ".assessment_cache.json"

# The elder view's six tiles, in grid order. The ids are the backend's symptom
# keys, so nothing has to be translated at the boundary.
SYMPTOM_TILES = [
    {"id": "dizzy", "label": "Dizzy"},
    {"id": "tired", "label": "Worn out"},
    {"id": "foggy", "label": "Foggy"},
    {"id": "weak", "label": "Weak"},
    {"id": "nauseous", "label": "Queasy"},
    {"id": "swollen_ankles", "label": "Puffy ankles"},
]
TILE_LABEL = {t["id"]: t["label"] for t in SYMPTOM_TILES}

assert {t["id"] for t in SYMPTOM_TILES} == set(SYMPTOM_TO_MEDDRA), (
    "the six tiles must match the backend's symptom keys exactly"
)


def today() -> dt.date:
    return dt.date.today()


def _iso(d: dt.date | None) -> str | None:
    return d.isoformat() if d else None


class Store:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self._assessments: dict[str, dict] = {}
        self.reset()
        self._load_cache()

    def reset(self) -> None:
        """Back to the seed. Used by the screenshot harness, which logs taps
        and submits check-ins and would otherwise leave the demo mutated.

        The assessment cache is keyed on the medications and check-ins that
        produced each entry, so resetting the inputs re-selects the entries that
        already match them — no openFDA traffic, and nothing stale survives.
        """
        self.person = dict(seed.PERSON)
        self.caregiver = dict(seed.CAREGIVER)
        self.medications = list(seed.MEDICATIONS)
        self.taps = list(seed.TAPS)
        self.checkins = list(seed.CHECKINS)
        self.doctor_list: list[str] = list(seed.DOCTOR_LIST_SEED)
        self.dismissed_nudges: set[str] = set()
        self.recorded_failures = dict(seed.RECORDED_FAILURES)

    # --- persistence of computed assessments ------------------------------
    # openFDA is a live dependency and each assessment costs several requests.
    # The cache holds results that were genuinely computed against it; it is
    # keyed on everything that would change the answer, so a stale entry cannot
    # survive a medication or check-in edit.
    def _load_cache(self) -> None:
        if CACHE_PATH.exists():
            try:
                self._assessments = json.loads(CACHE_PATH.read_text("utf-8"))
            except (ValueError, OSError):
                self._assessments = {}

    def _save_cache(self) -> None:
        try:
            CACHE_PATH.write_text(json.dumps(self._assessments), "utf-8")
        except OSError:
            pass

    def invalidate(self) -> None:
        """Called when the medications or check-ins change.

        Deliberately does not empty the cache. Every key already encodes the
        medications and check-ins that produced its entry, so changed inputs
        miss and recompute on their own -- while an entry that still matches its
        inputs stays valid. Emptying it threw away good results and sent the
        next request back to openFDA for answers it already had, which on a live
        API is slow enough to time a page out.
        """
        return

    # --- domain accessors -------------------------------------------------
    def person_obj(self) -> Person:
        return Person(age=self.person["age"], sex=self.person["sex"])

    def active_medications(self, as_of: dt.date | None = None) -> list:
        """Medications she was actually taking on a given day."""
        day = as_of or today()
        return [m for m in self.medications
                if m.started <= day and (m.stopped is None or m.stopped > day)]

    def backend_medications(self, as_of: dt.date | None = None) -> list[Medication]:
        return [Medication(name=m.name, started=m.started)
                for m in self.active_medications(as_of)]

    def backend_checkins(self, upto: dt.date | None = None) -> list[CheckIn]:
        out = []
        for c in self.checkins:
            if upto is not None and c.date > upto:
                continue
            s = score_answers(c.answers)
            if s is not None:
                out.append(CheckIn(date=c.date, frailty_score=s))
        return out

    def taps_for(self, symptom: str) -> list[dt.date]:
        return sorted(t.date for t in self.taps if t.symptom == symptom)

    def logged_symptoms(self) -> list[str]:
        seen: list[str] = []
        for t in sorted(self.taps, key=lambda t: t.date, reverse=True):
            if t.symptom not in seen:
                seen.append(t.symptom)
        return seen

    # --- the one thing that produces an outcome ---------------------------
    def _cache_key(self, symptom: str, as_of: dt.date) -> str:
        meds = ";".join(sorted(f"{m.name}:{m.started}:{m.stopped}"
                               for m in self.medications))
        cis = ";".join(f"{c.date}:{score_answers(c.answers)}"
                       for c in sorted(self.checkins, key=lambda c: c.date)
                       if c.date <= as_of)
        # Not hash(): str hashing is salted per process, so the on-disk cache
        # would miss on every restart and re-query openFDA for nothing.
        digest = hashlib.sha1(f"{meds}|{cis}".encode()).hexdigest()[:12]
        return f"{symptom}|{as_of}|{digest}"

    def assessment(self, symptom: str, *, force: bool = False) -> dict:
        """Real `combining.assess()` for the latest tap of one symptom."""
        taps = self.taps_for(symptom)
        if not taps:
            raise KeyError(symptom)
        as_of = taps[-1]
        key = self._cache_key(symptom, as_of)

        with self.lock:
            if not force and key in self._assessments:
                return self._assessments[key]

        # A recorded failure stands until someone retries it. It is a stored
        # record that the check did not run, never a result.
        if not force and symptom in self.recorded_failures:
            payload = self._recorded_failure_payload(symptom, as_of)
        else:
            payload = self._run_assessment(symptom, as_of)
            if force:
                self.recorded_failures.pop(symptom, None)

        with self.lock:
            self._assessments[key] = payload
            self._save_cache()
        return payload

    def _run_assessment(self, symptom: str, as_of: dt.date) -> dict:
        a = assess(
            symptom=symptom,
            person=self.person_obj(),
            medications=self.backend_medications(as_of),
            checkins=self.backend_checkins(upto=as_of),
            today=as_of,
        )
        note = notification_for(a)
        return self._serialise(a, note, as_of, source="computed")

    def _recorded_failure_payload(self, symptom: str, as_of: dt.date) -> dict:
        """Serialise a check that failed, without pretending it ran."""
        why = self.recorded_failures[symptom]
        return {
            "symptom": symptom,
            "symptom_label": label_for(symptom),
            "tile_label": TILE_LABEL[symptom],
            "outcome": Outcome.QUERY_FAILED.value,
            "as_of": _iso(as_of),
            "taps": [_iso(d) for d in self.taps_for(symptom)],
            "reasoning": (
                f"{label_for(symptom)} was logged after a recent medication "
                f"change, but the FDA adverse event database could not be "
                f"reached ({why}), so the medication check did not run. We do "
                f"not yet know whether the two are connected."
            ),
            "caveats": [],
            "recent_medications": [m.name for m in self.backend_medications(as_of)
                                   if m.is_recent(as_of)],
            "drug_findings": [],
            "frailty": None,
            "notification": {
                "type": "check_unavailable",
                "urgency": Urgency.NONE.value,
                "push": False,
                "message": (
                    f"{label_for(symptom).capitalize()} was logged after a "
                    f"recent medication change, but the medication database "
                    f"could not be reached, so that check still needs to be run."
                ),
                "detail": {},
            },
            "source": "recorded",
        }

    def _serialise(self, a, note: Notification, as_of: dt.date,
                   *, source: str) -> dict:
        return {
            "symptom": a.symptom,
            "symptom_label": label_for(a.symptom),
            "tile_label": TILE_LABEL[a.symptom],
            "outcome": a.outcome.value,
            "as_of": _iso(as_of),
            "taps": [_iso(d) for d in self.taps_for(a.symptom)],
            "reasoning": a.reasoning,
            "caveats": list(a.caveats),
            "recent_medications": [
                {"name": m.name, "started": _iso(m.started),
                 "days_since": m.days_since(as_of)}
                for m in a.recent_meds
            ],
            "drug_findings": [
                {
                    "drug": f.drug,
                    "days_since_change": f.days_since_change,
                    "status": f.status.value,
                    "prr": f.prr,
                    "cases": f.cases,
                    "chi2": f.chi2,
                    "detail": f.detail,
                }
                for f in a.drug_findings
            ],
            "frailty": {
                "status": a.frailty.status.value,
                "expected": a.frailty.expected,
                "observed": a.frailty.observed,
                "gap": a.frailty.gap,
                "trigger": a.frailty.trigger,
            },
            "notification": {
                "type": note.type.value,
                "urgency": note.urgency.value,
                "push": note.push,
                "message": note.message,
                "detail": note.detail,
            },
            "source": source,
        }

    # --- notifications ----------------------------------------------------
    def missed_checkin(self) -> dict | None:
        prompts = [CheckInPrompt(date=d, responded=r)
                   for d, r in seed.prompts(today())]
        n = missed_checkin_notification(prompts)
        if n is None:
            return None
        return {
            "id": "nudge_missed_checkins",
            "type": n.type.value,
            "urgency": n.urgency.value,
            "push": n.push,
            "message": n.message,
            "detail": n.detail,
        }


# Structural alias so the type hint above reads honestly without importing the
# seed dataclass into every consumer.
SeedMedicationLike = seed.SeedMedication

STORE = Store()
