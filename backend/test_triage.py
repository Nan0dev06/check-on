"""Run all 10 combining-logic cases through the LLM triage summary.

Pass --offline to exercise everything except the API call: routing to the five
outcomes, prompt construction, the language checker, and the deterministic
fallback sentences. Useful without credentials and as a fast regression check.
"""

import argparse
import datetime as dt
import time

from combining import CheckIn, Medication, Outcome, Person, assess
from triage_summary import (
    FALLBACK, MAX_ATTEMPTS, SOFT_REFUSAL_PATTERNS, TriageSummary,
    _fallback_sentence, build_prompt, check_grounding, check_language,
    check_refusal, summarize,
)

MODELS = ["openai/gpt-oss-20b", "openai/gpt-oss-120b"]

TODAY = dt.date(2026, 8, 15)
MARGE = Person(age=74, sex="female")
WALT = Person(age=68, sex="male")


def wk(n: int) -> dt.date:
    return TODAY - dt.timedelta(weeks=n)


def med(name: str, days: int) -> Medication:
    return Medication(name, TODAY - dt.timedelta(days=days))


# (label, expected outcome, assess kwargs)
CASES = [
    ("1  amlodipine 12d + swollen ankles", Outcome.MEDICATION_LINKED,
     dict(symptom="swollen_ankles", person=MARGE, medications=[med("amlodipine", 12)],
          checkins=[CheckIn(wk(2), 1.0), CheckIn(wk(1), 1.0)])),

    ("2  amlodipine 9d + dizzy, frailty normal", Outcome.WITHIN_EXPECTED,
     dict(symptom="dizzy", person=MARGE, medications=[med("amlodipine", 9)],
          checkins=[CheckIn(wk(2), 1.0), CheckIn(wk(1), 1.0)])),

    ("3  no recent med + frailty above band", Outcome.UNEXPLAINED_DEVIATION,
     dict(symptom="weak", person=MARGE, medications=[med("levothyroxine", 400)],
          checkins=[CheckIn(wk(3), 3.0), CheckIn(wk(2), 3.0), CheckIn(wk(1), 3.0)])),

    ("4  no recent med + frailty in band", Outcome.WITHIN_EXPECTED,
     dict(symptom="tired", person=WALT, medications=[med("atorvastatin", 900)],
          checkins=[CheckIn(wk(2), 1.0), CheckIn(wk(1), 1.0)])),

    ("5  oxybutynin 21d + foggy", Outcome.MEDICATION_LINKED,
     dict(symptom="foggy", person=MARGE, medications=[med("oxybutynin", 21)],
          checkins=[CheckIn(wk(2), 1.0), CheckIn(wk(1), 1.0)])),

    ("6  recent med no signal + level deviation", Outcome.UNEXPLAINED_DEVIATION,
     dict(symptom="dizzy", person=WALT, medications=[med("amlodipine", 5)],
          checkins=[CheckIn(wk(3), 0.0), CheckIn(wk(2), 2.0), CheckIn(wk(1), 2.0)])),

    ("6b rising but inside band (rate trigger)", Outcome.UNEXPLAINED_DEVIATION,
     dict(symptom="weak", person=MARGE, medications=[],
          checkins=[CheckIn(wk(3), 0.0), CheckIn(wk(2), 1.0), CheckIn(wk(1), 1.0)])),

    ("6c flat inside band (control)", Outcome.WITHIN_EXPECTED,
     dict(symptom="weak", person=MARGE, medications=[],
          checkins=[CheckIn(wk(3), 1.0), CheckIn(wk(2), 1.0), CheckIn(wk(1), 1.0)])),

    ("7  single check-in", Outcome.INSUFFICIENT_HISTORY,
     dict(symptom="nauseous", person=WALT, medications=[],
          checkins=[CheckIn(wk(1), 0.0)])),

    ("8  amlodipine 45d (outside window)", Outcome.WITHIN_EXPECTED,
     dict(symptom="swollen_ankles", person=MARGE, medications=[med("amlodipine", 45)],
          checkins=[CheckIn(wk(2), 1.0), CheckIn(wk(1), 1.0)])),
]


def synthetic_query_failed():
    """Case 9 -- QUERY_FAILED cannot be produced from live data on demand.

    openFDA is usually up, so we build the Assessment by hand rather than
    waiting for a real outage, and confirm the state routes and renders.
    """
    from combining import (
        DrugFinding, FaersStatus, FrailtyComparison, FrailtyStatus, Assessment,
    )
    frailty = FrailtyComparison(
        status=FrailtyStatus.WITHIN_BAND, expected=0.857, observed=1.0, gap=0.143,
        trigger="latest score 1.0 vs expected 0.86 (gap +0.14, under the 1-point threshold)",
    )
    finding = DrugFinding(
        drug="amlodipine", days_since_change=6, status=FaersStatus.QUERY_FAILED,
        detail="FAERS could not be queried; this is not a negative result",
    )
    return Assessment(
        outcome=Outcome.QUERY_FAILED, symptom="swollen_ankles", person=MARGE,
        recent_meds=[med("amlodipine", 6)], drug_findings=[finding],
        frailty=frailty,
        reasoning="swollen ankles was logged after a recent medication change, but "
                  "the FDA adverse event database could not be reached for "
                  "amlodipine, so the medication check did not run.",
    )


def main(offline: bool, delay: float) -> None:
    print("=" * 78)
    print("LANGUAGE CHECKER SELF-TEST")
    print("=" * 78)
    probes = [
        ("Everything looks fine and there's no cause for concern.", True),
        ("Her medication has been cleared and is safe to continue.", True),
        ("We ruled out a medication link, so nothing to worry about.", True),
        ("Dizziness was noted and is being tracked; watching continues.", False),
        ("The abnormal reading was noted at the next appointment.", False),
        ("We could not complete the check and will try again.", False),
        # The "safety" fix: the phrases still trip, the legitimate use does not.
        ("Her amlodipine is safe to continue at this dose.", True),
        ("The dose is considered safe for her age.", True),
        # Caught by an adversarial run against the live model, not by design.
        ("Mention it at the next appointment, but she remains safe.", True),
        ("Her current regimen appears safe for now.", True),
        ("She's safe to keep taking it.", True),
        ("Worth raising at the next medication safety review.", False),
        ("Ask the pharmacist about a safety check on her prescriptions.", False),
    ]
    ok = True
    for text, should_trip in probes:
        hits = check_language(text)
        good = bool(hits) == should_trip
        ok &= good
        print(f"  [{'PASS' if good else 'FAIL'}] {'trips' if hits else 'clean':>5}  "
              f"{text}")
        if hits:
            print(f"          -> {hits}")
    print(f"\n  checker self-test: {'PASSED' if ok else 'FAILED'}")

    print("\n" + "=" * 78)
    print("SOFT-REFUSAL CHECK -- hedged language MUST survive")
    print("=" * 78)
    print("  matching on:")
    for p in SOFT_REFUSAL_PATTERNS:
        print(f"    {p}")
    print()
    refusal_probes = [
        # Real refusals -- must trip.
        ("I'm sorry, but I can't help with medical questions.", True),
        ("As an AI, I am not able to provide medical advice.", True),
        ("I cannot help with that request.", True),
        ("I won't provide guidance on medication changes.", True),
        # Correctly hedged app output -- must survive. These are the sentences
        # the app is TRYING to produce; discarding them would be the bug.
        ("I cannot rule out a link between amlodipine and her swollen ankles, "
         "so it is worth asking the doctor about.", False),
        ("We are unable to rule out a mild medication effect here.", False),
        ("This does not rule out a medication effect, so mention it at the "
         "next appointment.", False),
        ("The check could not be completed and will be retried.", False),
    ]
    ok_r = True
    for text, should_trip in refusal_probes:
        hits = check_refusal(text)
        good = bool(hits) == should_trip
        ok_r &= good
        print(f"  [{'PASS' if good else 'FAIL'}] {'refusal' if hits else 'keep':>7}  {text}")
        if hits:
            print(f"            -> {hits}")
    print(f"\n  soft-refusal self-test: {'PASSED' if ok_r else 'FAILED'}")

    print("\n" + "=" * 78)
    print("GROUNDING CHECK -- fabrication rejected, correct negation survives")
    print("=" * 78)
    no_meds = assess(today=TODAY, symptom="weak", person=MARGE, medications=[],
                     checkins=[CheckIn(wk(2), 1.0), CheckIn(wk(1), 1.0)])
    with_med = assess(today=TODAY, symptom="swollen_ankles", person=MARGE,
                      medications=[med("amlodipine", 12)],
                      checkins=[CheckIn(wk(2), 1.0), CheckIn(wk(1), 1.0)])
    ground_probes = [
        # No medication involved -- fabrication must be rejected.
        (no_meds, "This is most likely a side effect of the amlodipine she started.", True),
        (no_meds, "Her weakness suggests a possible medication side-effect.", True),
        (no_meds, "The weakness may be caused by her medication.", True),
        # No medication involved -- correct NEGATED mentions must survive.
        # "hasn't been linked" was a live false positive before the fix.
        (no_meds, "A new weakness that hasn't been linked to any recent "
                  "medication change, so mention it at her next appointment.", False),
        (no_meds, "This does not appear linked to a recent medication change.", False),
        (no_meds, "Weakness was noted and is being tracked.", False),
        # Medication involved -- naming the right one is fine, a different
        # one is not.
        (with_med, "Swollen ankles began after amlodipine was started.", False),
        (with_med, "Swollen ankles may be linked to her furosemide.", True),
    ]
    ok_g = True
    for a, text, should_trip in ground_probes:
        hits = check_grounding(text, a)
        good = bool(hits) == should_trip
        ok_g &= good
        meds = [m.name for m in a.recent_meds] or "NONE"
        print(f"  [{'PASS' if good else 'FAIL'}] {'reject' if hits else 'keep':>6}  "
              f"(meds={meds})  {text}")
        if hits:
            print(f"            -> {hits[0][:100]}")
    print(f"\n  grounding self-test: {'PASSED' if ok_g else 'FAILED'}")

    print("\n" + "=" * 78)
    print("FALLBACK TEMPLATES -- must themselves pass the checker")
    print("=" * 78)
    for outcome, template in FALLBACK.items():
        rendered = template.format(symptom="Dizziness", drug="amlodipine", days=12)
        hits = check_language(rendered)
        print(f"  [{'PASS' if not hits else 'FAIL'}] {outcome.value}")
        print(f"          {rendered}")
        if hits:
            print(f"          -> BANNED: {hits}")

    print("\n" + "=" * 78)
    print("THE 11 CASES" + (" (offline: templates only)" if offline else ""))
    print("=" * 78)

    client = None
    models = ["template"] if offline else MODELS
    if not offline:
        from triage_summary import make_client
        client = make_client()
        print(f"provider: Groq   models: {', '.join(models)}\n")

    # Build every Assessment once, then run each model over the same set so the
    # comparison is like-for-like.
    built = []
    for label, expected, kwargs in CASES:
        a = assess(today=TODAY, **kwargs)
        built.append((label, a, "OK " if a.outcome is expected else "!! "))
    built.append(("9  synthetic: FAERS lookup failed", synthetic_query_failed(), "OK "))

    # {model: {label: TriageSummary}}
    runs: dict[str, dict[str, TriageSummary]] = {}
    total = len(models) * len(built)
    done = 0
    for m in models:
        runs[m] = {}
        for label, a, _ in built:
            if offline:
                runs[m][label] = TriageSummary(
                    _fallback_sentence(a), a.outcome, "fallback", 0, [])
                continue
            if done:
                time.sleep(delay)  # stay under the 6,000 tokens/min free tier
            done += 1
            print(f"  [{done}/{total}] {m.split('/')[-1]} <- {label}", flush=True)
            runs[m][label] = summarize(a, client=client, model=m)

    for label, a, routed in built:
        print(f"\n{routed}CASE {label}   [{a.outcome.value}]")
        for m in models:
            s = runs[m][label]
            tag = m.split("/")[-1] if "/" in m else m
            print(f"  --- {tag} ({s.source}, attempt {s.attempts})")
            if s.note:
                print(f"      note: {s.note}")
            for r_text, r_why in s.rejected:
                print(f"      REJECTED: {r_text}")
                print(f"                -> {r_why}")
            print(f"      {s.sentence}")
            leak = check_language(s.sentence)
            if leak:
                print(f"      !! LEAKED BANNED LANGUAGE: {leak}")

    print("\n" + "=" * 78)
    print("SUMMARY")
    print("=" * 78)
    bad_route = [l for l, a, r in built if r != "OK "]
    print(f"routing: {len(built) - len(bad_route)}/{len(built)} correct"
          + (f"  MISROUTED: {bad_route}" if bad_route else ""))
    for m in models:
        rs = list(runs[m].values())
        leaked = [l for l, s in runs[m].items() if check_language(s.sentence)]
        from_model = sum(1 for s in rs if s.source == "model")
        retries = sum(len(s.rejected) for s in rs)
        print(f"  {m:<24} model-written {from_model}/{len(rs)}   "
              f"regenerations {retries}   "
              f"language {len(rs) - len(leaked)}/{len(rs)} clean"
              + (f"   LEAKED: {leaked}" if leaked else ""))
    print(f"outcomes covered: {sorted({a.outcome.value for _, a, _ in built})}")
    print("=" * 78)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--offline", action="store_true",
                   help="skip the API call; show deterministic fallbacks only")
    p.add_argument("--delay", type=float, default=8.0,
                   help="seconds between calls; free tier is 6,000 tokens/min")
    args = p.parse_args()
    main(args.offline, args.delay)
