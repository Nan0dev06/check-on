"""HTTP surface for the Check On frontend.

`backend/` is a library with no transport layer, so this module is the only new
code between it and the browser. It adds no logic of its own: every outcome
comes from `combining.assess()`, every notification from `notifications`, every
PRR from a live openFDA query, and the expected frailty band from the trained
baseline. Where a response reads like a judgement, it was made in backend/.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

import faers_prr  # noqa: E402
from faers_prr import OpenFDAError, resolve_drug  # noqa: E402

from . import seed  # noqa: E402
from .scoring import score_answers  # noqa: E402
from .store import STORE, SYMPTOM_TILES, _iso, expected_score, today  # noqa: E402

app = FastAPI(title="Check On", version="1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- people ---------------------------------------------------------------
@app.get("/api/person")
def get_person():
    last = max((c.date for c in STORE.checkins), default=None)
    return {
        **{k: STORE.person[k] for k in
           ("name", "full_name", "called", "initials", "age", "sex", "phone")},
        "caregiver": STORE.caregiver,
        "last_checkin": _iso(last),
        "last_checkin_time": "8:12am",
        "today": _iso(today()),
    }


@app.get("/api/symptoms")
def get_symptoms():
    return SYMPTOM_TILES


# --- medications ----------------------------------------------------------
def _med_payload(m) -> dict:
    now = today()
    return {
        "id": m.id,
        "name": m.name,
        "dose_value": m.dose_value,
        "dose_unit": m.dose_unit,
        "frequency": m.frequency,
        "started": _iso(m.started),
        "stopped": _iso(m.stopped),
        "prescriber": m.prescriber,
        "days_since_start": (now - m.started).days,
    }


@app.get("/api/medications")
def get_medications():
    ordered = sorted(STORE.medications, key=lambda m: m.started, reverse=True)
    return {
        "active": [_med_payload(m) for m in ordered if m.stopped is None],
        "stopped": [_med_payload(m) for m in ordered if m.stopped is not None],
    }


@app.get("/api/drugs/match")
def match_drug(q: str = Query(min_length=2)):
    """Resolve a typed name against openFDA's harmonised drug index.

    A bare `resolve_drug` is not enough on its own here. openFDA's drug fields
    are tokenised, so a partial word answers with a nonzero count -- "amlo"
    returns 1,415 reports -- and accepting that would let Save unlock on a
    fragment and run a PRR query against a name no one prescribes. The check
    below requires the typed text to BE a term in the index, not merely to
    match inside one.

    `matched: false` means openFDA has no drug under exactly that name. It does
    not mean the drug is unknown to medicine.
    """
    name = q.strip().lower()

    # Both fields are checked as exact terms. `resolve_drug` alone is not usable
    # as the gate here: every one of its strategies is a phrase search over a
    # tokenised field, so "amlo" scores 1,415 on medicinalproduct and "furosem"
    # scores 15. Those are fragments appearing inside reported product strings,
    # not drugs. Brand names live in medicinalproduct, which is why it is still
    # consulted -- just as an index, not as a substring search.
    for field in ("openfda.generic_name", "medicinalproduct"):
        exact = next(
            (t for t in _prefix_terms(name, field) if t["name"].lower() == name),
            None,
        )
        if exact:
            return {
                "query": q,
                "matched": True,
                "canonical": name,
                "field": field,
                "report_count": exact["reports"],
            }

    return {
        "query": q,
        "matched": False,
        "detail": f"{q!r} is not a drug name in the interaction data",
    }


def _prefix_terms(prefix: str, field: str = "openfda.generic_name") -> list[dict]:
    """Drug names in one openFDA index that start with `prefix`.

    A wildcard search matches whole *reports*, so counting names over the hits
    returns every co-medication in them too -- aspirin comes back for "amlo".
    The prefix filter below is doing real work, not tidying.
    """
    params = urllib.parse.urlencode({
        "search": f"patient.drug.{field}:{prefix}*",
        "count": f"patient.drug.{field}.exact",
        "limit": "40",
    })
    url = f"{faers_prr.ENDPOINT}?{params}"
    if faers_prr.API_KEY:
        url += f"&api_key={faers_prr.API_KEY}"

    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            results = json.load(resp).get("results", [])
    except (urllib.error.URLError, TimeoutError, ValueError):
        # An empty list is not "no such drug" -- it is "we could not ask". The
        # caller decides what to do with that; nothing here reports a result.
        return []

    seen: list[dict] = []
    for r in results:
        term = r.get("term", "")
        if term.lower().startswith(prefix) and not any(
            s["name"].lower() == term.lower() for s in seen
        ):
            seen.append({"name": term.title(), "reports": r.get("count", 0)})
    return seen


@app.get("/api/drugs/suggest")
def suggest_drugs(q: str = Query(min_length=2)):
    """Prefix suggestions, so the caregiver can pick the canonical name."""
    return {"query": q, "suggestions": _prefix_terms(q.strip().lower())[:4]}


@app.post("/api/medications")
def add_medication(payload: dict = Body(...)):
    name = (payload.get("name") or "").strip()
    started = payload.get("started")
    if not name or not started:
        raise HTTPException(422, "a name and a start date are both required")
    try:
        start = dt.date.fromisoformat(started)
    except ValueError:
        raise HTTPException(422, f"unparseable start date {started!r}")

    med = seed.SeedMedication(
        id=f"med_{name.lower().replace(' ', '_')}_{start.isoformat()}",
        name=name,
        dose_value=str(payload.get("dose_value") or ""),
        dose_unit=payload.get("dose_unit") or "mg",
        frequency=payload.get("frequency") or "Mornings",
        started=start,
        prescriber=(payload.get("prescriber") or None),
    )
    with STORE.lock:
        STORE.medications.append(med)
    # A new medicine can retrospectively explain a symptom already in the feed,
    # so every stored assessment is dropped and recomputed on next read.
    STORE.invalidate()
    return {"medication": _med_payload(med), "rechecked": True}


# --- elder: taps and the weekly check-in ---------------------------------
@app.post("/api/taps")
def log_tap(payload: dict = Body(...)):
    symptom = payload.get("symptom")
    if symptom not in {t["id"] for t in SYMPTOM_TILES}:
        raise HTTPException(422, f"unknown symptom {symptom!r}")
    when = today()
    with STORE.lock:
        STORE.taps.append(seed.SeedTap(symptom=symptom, date=when))
    STORE.invalidate()
    return {"symptom": symptom, "date": _iso(when)}


@app.delete("/api/taps/latest")
def undo_tap(symptom: str = Query(...)):
    """Backs out the tap just logged -- 'I tapped that by mistake'."""
    with STORE.lock:
        for i in range(len(STORE.taps) - 1, -1, -1):
            if STORE.taps[i].symptom == symptom and STORE.taps[i].date == today():
                STORE.taps.pop(i)
                STORE.invalidate()
                return {"removed": True}
    return {"removed": False}


@app.get("/api/checkin/questions")
def checkin_questions():
    """The four weekly questions. Copy is plain speech; the clinical criterion
    each one maps to stays on the server and is never sent to the elder view."""
    return [
        {
            "key": "weight",
            "eyebrow": f"{STORE.caregiver['name']}’s weekly check-in",
            "question": "Have your clothes felt looser or tighter lately?",
            "answers": [
                {"value": "same", "label": "About the same"},
                {"value": "looser", "label": "A bit looser"},
                {"value": "tighter", "label": "A bit tighter"},
                {"value": "declined", "label": "I’d rather not say",
                 "declined": True},
            ],
        },
        {
            "key": "energy",
            "eyebrow": "Question 2 of 4",
            "question": "How much energy have you had this week?",
            "answers": [
                {"value": "plenty", "label": "Plenty, same as usual"},
                {"value": "less", "label": "Less than usual"},
                {"value": "not_much", "label": "Not much at all"},
            ],
        },
        {
            "key": "activity",
            "eyebrow": "Question 3 of 4",
            "question": "Have you been getting out and about?",
            "answers": [
                {"value": "most_days", "label": "Most days"},
                {"value": "now_and_then", "label": "Now and then"},
                {"value": "stayed_in", "label": "Mostly stayed in"},
            ],
        },
        {
            "key": "walking",
            "eyebrow": "Last one",
            "question": "How has walking felt this week?",
            "answers": [
                {"value": "steady", "label": "Steady, no trouble"},
                {"value": "harder", "label": "A bit harder than usual"},
                {"value": "holding_on", "label": "I hold on to things now"},
            ],
        },
    ]


@app.post("/api/checkin")
def submit_checkin(payload: dict = Body(...)):
    answers = payload.get("answers") or {}
    when = today()
    with STORE.lock:
        STORE.checkins = [c for c in STORE.checkins if c.date != when]
        STORE.checkins.append(seed.SeedCheckIn(date=when, answers=answers))
    STORE.invalidate()
    return {"date": _iso(when), "scored": score_answers(answers) is not None}


# --- caregiver: flags, trend, notifications ------------------------------
@app.get("/api/flags")
def get_flags():
    """One assessment per logged symptom, newest tap first.

    Each is a real `assess()` run as of the day that symptom was last tapped,
    against the check-ins that existed then. A flag is a snapshot of a check,
    not a live re-derivation, which is why the date it was taken travels with it.
    """
    out = []
    for symptom in STORE.logged_symptoms():
        out.append(STORE.assessment(symptom))
    out.sort(key=lambda f: f["as_of"], reverse=True)
    return out


@app.get("/api/flags/{symptom}")
def get_flag(symptom: str):
    try:
        return STORE.assessment(symptom)
    except KeyError:
        raise HTTPException(404, f"nothing logged for {symptom!r}")


@app.post("/api/flags/{symptom}/recheck")
def recheck_flag(symptom: str):
    """Re-run this one check live. May fail again; that is a valid answer."""
    try:
        return STORE.assessment(symptom, force=True)
    except KeyError:
        raise HTTPException(404, f"nothing logged for {symptom!r}")
    except OpenFDAError as exc:
        raise HTTPException(503, str(exc))


@app.get("/api/trend")
def get_trend():
    """Her weekly answers as a series, against the population band.

    The band is the trained baseline's expectation for her age and sex. It is
    cross-sectional -- a range to compare against, not a forecast for her -- so
    the caveat travels with the data rather than being left to the UI.
    """
    person = STORE.person_obj()
    expected = expected_score(person)
    series = [
        {"date": _iso(c.date), "score": score_answers(c.answers)}
        for c in sorted(STORE.checkins, key=lambda c: c.date)
    ]
    series = [p for p in series if p["score"] is not None]
    return {
        "series": series,
        "expected": expected,
        "band": {"low": max(0.0, expected - 1.0), "high": expected + 1.0},
        "provenance": (
            "This line comes from her weekly answers about energy, walking, "
            "getting out, and weight — not from a clinical assessment."
        ),
        "caveat": (
            "The expected range is a population average for her age and sex, "
            "not a prediction about her."
        ),
    }


@app.get("/api/notifications")
def get_notifications():
    """Everything the caregiver could be shown, tiered by the backend.

    High and low are the two tiers `notifications.py` pushes. Feed-only items
    stay out of this list -- they are flags, and they live in /api/flags.
    """
    high, low = [], []
    for symptom in STORE.logged_symptoms():
        f = STORE.assessment(symptom)
        n = f["notification"]
        if n["urgency"] == "high":
            high.append({"id": f"flag_{symptom}", "symptom": symptom,
                         "outcome": f["outcome"], **n})
        elif n["urgency"] == "low":
            low.append({"id": f"flag_{symptom}", "symptom": symptom, **n})

    missed = STORE.missed_checkin()
    if missed and missed["id"] not in STORE.dismissed_nudges:
        low.append(missed)
    for r in seed.REMINDERS:
        low.append({**r, "urgency": "low", "type": "reminder", "push": False})

    high.sort(key=lambda n: n.get("symptom", ""))
    return {"high": high, "low": low}


@app.post("/api/_reset")
def reset_demo():
    """Restore the seed. For the screenshot harness, which logs taps and
    submits check-ins as it drives the UI."""
    STORE.reset()
    return {"reset": True}


@app.get("/api/doctor-list")
def get_doctor_list():
    return {"items": STORE.doctor_list}


# --- serving the built frontend ------------------------------------------
# One service serves both the API and the app, so there is no cross-origin
# request in production and no second URL to keep in sync. In development the
# Vite dev server proxies /api here instead and this block does nothing.
DIST = ROOT / "frontend" / "dist"

if DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        """Serve index.html for any non-API path.

        Routing is client-side, so /elder and /flag/swollen_ankles are real
        entry points a caregiver can be sent to directly. Without this they
        would 404 on reload -- the API only knows about /api/*.
        """
        if path.startswith("api/"):
            raise HTTPException(404, "no such endpoint")
        candidate = DIST / path
        if path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(DIST / "index.html")


@app.post("/api/doctor-list")
def add_to_doctor_list(payload: dict = Body(...)):
    item = (payload.get("item") or "").strip()
    if not item:
        raise HTTPException(422, "nothing to add")
    with STORE.lock:
        if item not in STORE.doctor_list:
            STORE.doctor_list.append(item)
    return {"items": STORE.doctor_list}
