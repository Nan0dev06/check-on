"""The ten acceptance scenarios, run against the real backend.

Every case below constructs inputs and calls `combining.assess()` -- the same
function the API calls -- so a pass here means the shipped path produces the
listed outcome, not that a fixture agrees with itself.

Rows 1, 2, 5 and 8 hit live openFDA. Row 7 forces a failure. Nothing is mocked
except that failure, which is the point of the row.

    python api/test_scenarios.py            all ten
    python api/test_scenarios.py --offline  skip the four live-FAERS rows

Exit code is nonzero if any row does not produce its expected outcome.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

import combining  # noqa: E402
import faers_prr  # noqa: E402
from combining import (  # noqa: E402
    CheckIn,
    Medication,
    Outcome,
    Person,
    assess,
    expected_score,
)

TODAY = dt.date(2026, 8, 16)
RUTH = Person(age=78, sex="female")
EXPECTED = expected_score(RUTH)          # 0.955 for a 78-year-old woman
BAND_TOP = EXPECTED + combining.DEVIATION_POINTS


def days_ago(n: int) -> dt.date:
    return TODAY - dt.timedelta(days=n)


def weekly(scores: list[float], end: dt.date = TODAY) -> list[CheckIn]:
    """Weekly check-ins ending on `end`, oldest first."""
    return [
        CheckIn(date=end - dt.timedelta(weeks=len(scores) - 1 - i),
                frailty_score=s)
        for i, s in enumerate(scores)
    ]


# Two check-in histories, named for what `compare_frailty` calls them rather
# than for how they look, so a change in the threshold shows up here as a
# failing precondition instead of a silently wrong scenario.
STEADY = weekly([1, 1, 1, 1, 1])                 # WITHIN_BAND
WORSENING = weekly([1, 1, 1, 2, 3])              # DEVIATING: 2 consecutive over
ONE_CHECKIN = weekly([1])                        # INSUFFICIENT_HISTORY


CASES = [
    {
        "n": 1,
        "name": 'Amlodipine started 12 days ago, taps "puffy ankles"',
        "expect": Outcome.MEDICATION_LINKED,
        "why": "Real signal, PRR 3.5, clears Evans",
        "live": True,
        "symptom": "swollen_ankles",
        "meds": [Medication("amlodipine", days_ago(12))],
        "checkins": STEADY,
    },
    {
        "n": 2,
        "name": 'Amlodipine started 9 days ago, taps "dizzy"',
        "expect": Outcome.WITHIN_EXPECTED,
        "why": "PRR 1.86 -- real effect, under the bar. Must NOT fire.",
        "live": True,
        "symptom": "dizzy",
        "meds": [Medication("amlodipine", days_ago(9))],
        "checkins": STEADY,
    },
    {
        "n": 3,
        "name": "No recent medication change, check-ins trending worse",
        "expect": Outcome.UNEXPLAINED_DEVIATION,
        "why": "Sustained deviation, no medication explanation",
        "live": False,
        "symptom": "tired",
        "meds": [Medication("levothyroxine", days_ago(900))],
        "checkins": WORSENING,
    },
    {
        "n": 4,
        "name": "No recent medication change, check-ins within range",
        "expect": Outcome.WITHIN_EXPECTED,
        "why": "Nothing unusual",
        "live": False,
        "symptom": "tired",
        "meds": [Medication("levothyroxine", days_ago(900))],
        "checkins": STEADY,
    },
    {
        "n": 5,
        "name": 'Oxybutynin started 21 days ago, taps "foggy"',
        "expect": Outcome.MEDICATION_LINKED,
        "why": "Real signal (PRR ~2.19) -- anticholinergic confusion",
        "live": True,
        "symptom": "foggy",
        "meds": [Medication("oxybutynin", days_ago(21))],
        "checkins": STEADY,
    },
    {
        "n": 6,
        "name": "Only one check-in exists, any symptom logged",
        "expect": Outcome.INSUFFICIENT_HISTORY,
        "why": "Nothing to compare against -- its own distinct state",
        "live": False,
        "symptom": "tired",
        "meds": [Medication("levothyroxine", days_ago(900))],
        "checkins": ONE_CHECKIN,
    },
    {
        "n": 7,
        "name": "FAERS query fails / times out",
        "expect": Outcome.QUERY_FAILED,
        "why": "A failed check is not 'no signal found'",
        "live": False,
        "fail_faers": True,
        "symptom": "swollen_ankles",
        "meds": [Medication("amlodipine", days_ago(12))],
        "checkins": STEADY,
    },
    {
        "n": 8,
        "name": 'Amlodipine started 45 days ago, taps "puffy ankles"',
        "expect": Outcome.WITHIN_EXPECTED,
        "why": "Outside the 30-day window on purpose -- documented miss",
        "live": False,
        "symptom": "swollen_ankles",
        "meds": [Medication("amlodipine", days_ago(45))],
        "checkins": STEADY,
    },
]

# Row 9 and row 10 are properties of every sentence the app emits, not separate
# inputs, so they are checked against the output of every row above.
BANNED = [
    "safe", "safely", "safer", "cleared", "clear", "no risk", "ruled out",
    "rule out", "all clear", "normal", "fine", "healthy", "nothing to worry",
    "remains safe", "no concern", "not a concern", "unremarkable", "reassuring",
]


def run_case(case: dict) -> tuple[bool, str, object]:
    """Returns (passed, detail, assessment)."""
    if case.get("fail_faers"):
        # Force the failure rather than waiting for one: point the module's
        # endpoint at a host that cannot resolve. `assess` has to surface this
        # as QUERY_FAILED, not swallow it into a quiet outcome.
        original = faers_prr.ENDPOINT
        faers_prr.ENDPOINT = "https://openfda.invalid./drug/event.json"
        try:
            a = assess(case["symptom"], RUTH, case["meds"], case["checkins"],
                       today=TODAY)
        finally:
            faers_prr.ENDPOINT = original
    else:
        a = assess(case["symptom"], RUTH, case["meds"], case["checkins"],
                   today=TODAY)

    ok = a.outcome is case["expect"]
    return ok, f"got {a.outcome.value}", a


# Negated forms of the banned phrases are not merely allowed, they are the
# wording the product wants. "This does not rule out a mild or underreported
# effect" is the opposite of a reassurance -- it is the sentence that stops a
# reader treating no-signal as no-risk, and it is what backend/combining.py
# actually emits for WITHIN_EXPECTED. Flagging it would push the copy toward
# saying less about uncertainty, which inverts the rule it enforces.
#
# Worth knowing: triage_summary.BANNED_PATTERNS bans `ruled? out`
# unconditionally, so the LLM path would reject the very phrasing the
# deterministic path produces. That inconsistency is in backend/ and is left
# alone here; it only bites if a generated sentence reaches for the same words.
NEGATORS = (
    "does not", "doesn't", "do not", "don't", "cannot", "can't", "could not",
    "couldn't", "not", "never", "no ",
)


def check_language(a) -> list[str]:
    """Row 9 -- no reassurance language anywhere in the emitted text."""
    hits = []
    text = " ".join([a.reasoning, *a.caveats]).lower()
    padded = f" {text} ".replace(",", " ").replace(".", " ")

    for term in BANNED:
        # Word-boundary-ish: avoid "safety"/"finely" tripping "safe"/"fine".
        idx = padded.find(f" {term} ")
        if idx == -1:
            continue
        # Look back a short window for a negation attached to this phrase.
        window = padded[max(0, idx - 24):idx + 1]
        if any(neg in window for neg in NEGATORS):
            continue
        hits.append(term)
    return hits


def check_grounding(a, meds: list[Medication]) -> list[str]:
    """Row 10 -- a medication-linked sentence names the right medicine, and a
    sentence with no medication behind it names none at all."""
    problems = []
    text = a.reasoning.lower()
    recent = {m.name.lower() for m in meds
              if m.is_recent(TODAY)}
    signalled = {f.drug.lower() for f in a.drug_findings
                 if f.status.value == "signal"}

    if a.outcome is Outcome.MEDICATION_LINKED:
        if not signalled:
            problems.append("medication_linked with no signalled drug")
        for drug in signalled:
            if drug not in text:
                problems.append(f"does not name the implicated drug {drug!r}")
        for m in meds:
            name = m.name.lower()
            if name not in signalled and name in text:
                problems.append(f"names a non-implicated drug {name!r}")
    else:
        # No medication link: the sentence may mention that a medicine was
        # started recently, but must not attribute the symptom to one.
        for m in meds:
            if m.name.lower() in text and m.name.lower() not in recent:
                problems.append(
                    f"names {m.name!r}, which is not a recent change")
    return problems


def check_retry_stays_failed() -> list[str]:
    """Row 7, through the HTTP layer the UI actually talks to.

    The rule the design states is that a failed check must never decay into a
    quiet or clear-looking state. A retry that fails again is where that would
    happen, so this drives /api/flags/{symptom}/recheck with openFDA
    unreachable and asserts the endpoint still reports QUERY_FAILED rather than
    falling through to WITHIN_EXPECTED.
    """
    from fastapi.testclient import TestClient

    # Imported by package path so this file runs either as `python
    # api/test_scenarios.py` or as `python -m api.test_scenarios`.
    sys.path.insert(0, str(ROOT))
    from api.main import app
    from api.store import STORE

    problems = []
    original = faers_prr.ENDPOINT
    STORE.reset()
    client = TestClient(app)

    faers_prr.ENDPOINT = "https://openfda.invalid./drug/event.json"
    try:
        res = client.post("/api/flags/weak/recheck")
        if res.status_code == 503:
            # Surfacing the failure as an error is acceptable: the UI keeps the
            # card exactly as it was, which is the required behaviour.
            pass
        elif res.status_code == 200:
            outcome = res.json()["outcome"]
            if outcome != "query_failed":
                problems.append(
                    f"retry under failure returned {outcome!r}, "
                    f"expected query_failed"
                )
        else:
            problems.append(f"retry returned unexpected status {res.status_code}")

        feed = client.get("/api/flags").json()
        weak = next((f for f in feed if f["symptom"] == "weak"), None)
        if weak is None:
            problems.append("the failed check vanished from the feed")
        elif weak["outcome"] != "query_failed":
            problems.append(
                f"after a failed retry the feed shows {weak['outcome']!r}, "
                f"expected query_failed"
            )
        elif weak["notification"]["push"]:
            problems.append("a failed check must not push")
    finally:
        faers_prr.ENDPOINT = original
        STORE.reset()

    return problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true",
                    help="skip the rows that query openFDA")
    args = ap.parse_args()

    print(f"expected score for a {RUTH.age}-year-old {RUTH.sex}: "
          f"{EXPECTED:.3f}   deviation threshold: {BAND_TOP:.3f}")
    print(f"recent-change window: {combining.RECENT_CHANGE_DAYS} days   "
          f"today: {TODAY}\n")

    failures = []
    skipped = 0

    for case in CASES:
        if args.offline and case["live"]:
            print(f"  SKIP{case['n']:>2}. {case['name']}  (skipped, needs openFDA)")
            skipped += 1
            continue

        ok, detail, a = run_case(case)
        lang = check_language(a)
        ground = check_grounding(a, case["meds"])

        mark = "OK " if ok and not lang and not ground else "FAIL"
        print(f"  {mark} {case['n']:>2}. {case['name']}")
        print(f"        expected {case['expect'].value}, {detail}")

        if not ok:
            failures.append(f"row {case['n']}: expected {case['expect'].value}, {detail}")
        if lang:
            failures.append(f"row 9 (via row {case['n']}): banned language {lang}")
            print(f"        FAIL banned language: {lang}")
        if ground:
            failures.append(f"row 10 (via row {case['n']}): {ground}")
            print(f"        FAIL grounding: {ground}")

        for f in a.drug_findings:
            bits = f"PRR {f.prr:.2f}" if f.prr is not None else f.detail
            print(f"        - {f.drug}: {f.status.value} ({bits}), "
                  f"{f.days_since_change}d since change")
        print(f"        - frailty: {a.frailty.status.value}"
              f"{f' ({a.frailty.trigger})' if a.frailty.trigger else ''}")
        print(f"        - \"{a.reasoning}\"")
        print()

    retry_problems = check_retry_stays_failed()
    mark = "FAIL" if retry_problems else "OK "
    print(f"  {mark}  7b. Retry that fails again stays QUERY_FAILED (via HTTP)")
    for p in retry_problems:
        print(f"        FAIL {p}")
        failures.append(f"row 7b: {p}")
    print()

    print("-" * 72)
    if failures:
        print(f"FAIL {len(failures)} failure(s):\n")
        for f in failures:
            print(f"   {f}")
        return 1
    print(f"PASS all {len(CASES) - skipped} checked rows produced the expected outcome")
    print("PASS rows 9 and 10 hold for every sentence emitted above")
    if skipped:
        print(f"  ({skipped} rows skipped -- rerun without --offline to include them)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
