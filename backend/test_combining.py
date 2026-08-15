"""Run representative cases through the combining logic and print the outcomes."""

import datetime as dt

from combining import (
    Assessment, CheckIn, FaersStatus, Medication, Outcome, Person, assess,
    expected_score,
)

TODAY = dt.date(2026, 8, 15)


def wk(n: int) -> dt.date:
    """n weeks before TODAY."""
    return TODAY - dt.timedelta(weeks=n)


def show(title: str, a: Assessment) -> None:
    print("=" * 78)
    print(title)
    print("=" * 78)
    print(f"  symptom     {a.symptom}")
    print(f"  person      {a.person.age}yo {a.person.sex}")
    print(f"  recent meds {', '.join(f'{m.name} ({m.change_note}, '
                                     f'{m.days_since(TODAY)}d ago)'
                                     for m in a.recent_meds) or '(none in window)'}")
    for f in a.drug_findings:
        prr = f"PRR {f.prr:.2f}" if f.prr is not None else "n/a"
        print(f"  FAERS       {f.drug}: {f.status.value}  ({prr})")
        print(f"              {f.detail}")
    if not a.drug_findings:
        print(f"  FAERS       {FaersStatus.NOT_CHECKED.value} (no recent medication change)")
    print(f"  frailty     {a.frailty.status.value}")
    print(f"              {a.frailty.trigger}")
    print(f"\n  OUTCOME >>  {a.outcome.value.upper()}")
    print(f"\n  {a.reasoning}")
    for c in a.caveats:
        print(f"\n  [caveat] {c}")
    print()


if __name__ == "__main__":
    marge = Person(age=74, sex="female")
    walt = Person(age=68, sex="male")
    print(f"expected app frailty score: 74yo woman {expected_score(marge):.3f}, "
          f"68yo man {expected_score(walt):.3f}\n")

    # 1. The canonical cascade: new CCB, then swollen ankles.
    show("CASE 1  recent amlodipine + swollen ankles  -> expect MEDICATION_LINKED",
         assess("swollen_ankles", marge,
                [Medication("amlodipine", TODAY - dt.timedelta(days=12))],
                [CheckIn(wk(2), 1.0), CheckIn(wk(1), 1.0)], TODAY))

    # 2. Recent med, but the symptom does not clear Evans, and frailty is normal.
    #    The negative must NOT read as reassurance.
    show("CASE 2  recent amlodipine + dizzy, frailty normal -> expect WITHIN_EXPECTED",
         assess("dizzy", marge,
                [Medication("amlodipine", TODAY - dt.timedelta(days=9))],
                [CheckIn(wk(2), 1.0), CheckIn(wk(1), 1.0)], TODAY))

    # 3. No recent medication change at all, frailty clearly above the band.
    #    FAERS must be skipped entirely.
    show("CASE 3  no recent med + frailty above band -> expect UNEXPLAINED_DEVIATION",
         assess("weak", marge,
                [Medication("levothyroxine", TODAY - dt.timedelta(days=400))],
                [CheckIn(wk(3), 3.0), CheckIn(wk(2), 3.0), CheckIn(wk(1), 3.0)], TODAY))

    # 4. Nothing recent, frailty inside the band.
    show("CASE 4  no recent med + frailty in band -> expect WITHIN_EXPECTED",
         assess("tired", walt,
                [Medication("atorvastatin", TODAY - dt.timedelta(days=900))],
                [CheckIn(wk(2), 1.0), CheckIn(wk(1), 1.0)], TODAY))

    # 5. Anticholinergic started recently, confusion logged.
    show("CASE 5  recent oxybutynin + foggy -> expect MEDICATION_LINKED",
         assess("foggy", marge,
                [Medication("oxybutynin", TODAY - dt.timedelta(days=21))],
                [CheckIn(wk(2), 1.0), CheckIn(wk(1), 1.0)], TODAY))

    # 6. Recent med with no strong signal, BUT frailty is rising fast from a low
    #    base -- the rate trigger should fire even though the level stays low.
    show("CASE 6  recent med, no signal, rising trend -> expect UNEXPLAINED_DEVIATION",
         assess("dizzy", walt,
                [Medication("amlodipine", TODAY - dt.timedelta(days=5))],
                [CheckIn(wk(3), 0.0), CheckIn(wk(2), 2.0), CheckIn(wk(1), 2.0)], TODAY))

    # 6b. Isolates the RATE trigger. Scores 0 -> 1 -> 1 for a 74yo woman whose
    #     expected is 0.857: the level trigger cannot fire (gap is only +0.14),
    #     so if this deviates it is the rise, not the level, that did it.
    show("CASE 6b rising but inside band -> rate trigger must fire alone",
         assess("weak", marge, [],
                [CheckIn(wk(3), 0.0), CheckIn(wk(2), 1.0), CheckIn(wk(1), 1.0)], TODAY))

    # 6c. Control for 6b: same low scores, flat. Must NOT deviate.
    show("CASE 6c flat and inside band -> must stay WITHIN_EXPECTED",
         assess("weak", marge, [],
                [CheckIn(wk(3), 1.0), CheckIn(wk(2), 1.0), CheckIn(wk(1), 1.0)], TODAY))

    # 7. Brand new user -- one check-in only. Must not be reported as "in band".
    show("CASE 7  single check-in -> insufficient history must be surfaced",
         assess("nauseous", walt, [], [CheckIn(wk(1), 0.0)], TODAY))

    # 8. Medication changed 45 days ago -- outside the 30-day window, so FAERS
    #    is skipped even though the drug/symptom pair would signal.
    show("CASE 8  amlodipine started 45d ago + swollen ankles -> outside window",
         assess("swollen_ankles", marge,
                [Medication("amlodipine", TODAY - dt.timedelta(days=45))],
                [CheckIn(wk(2), 1.0), CheckIn(wk(1), 1.0)], TODAY))

    print("=" * 78)
    print("LANGUAGE CHECK -- no forbidden reassurance words in any emitted text")
    print("=" * 78)
    banned = ["cleared", "safe", "no risk", "ruled out", "nothing to worry"]
    cases = [
        assess("dizzy", marge, [Medication("amlodipine", TODAY - dt.timedelta(days=9))],
               [CheckIn(wk(2), 1.0), CheckIn(wk(1), 1.0)], TODAY),
        assess("tired", walt, [], [CheckIn(wk(2), 0.0), CheckIn(wk(1), 0.0)], TODAY),
    ]
    bad = []
    for a in cases:
        text = (a.reasoning + " " + " ".join(a.caveats)).lower()
        bad += [w for w in banned if w in text]
    print(f"   forbidden terms found: {bad if bad else 'none'}")
