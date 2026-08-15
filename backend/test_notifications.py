"""Notification tiering over realistic sequences.

Fully offline and deterministic: Assessments are constructed directly rather
than through assess(), so this suite does not touch openFDA or Groq. The
combining logic that produces those Assessments is covered by test_triage.py.
"""

import datetime as dt

from combining import (
    Assessment, DrugFinding, FaersStatus, FrailtyComparison, FrailtyStatus,
    Medication, Outcome, Person,
)
from notifications import (
    MISSED_STREAK_THRESHOLD, CheckInPrompt, NotificationType, Urgency,
    consecutive_missed, evaluate, missed_checkin_notification,
    notification_for,
)
from triage_summary import check_language

TODAY = dt.date(2026, 8, 15)
MARGE = Person(age=74, sex="female")


def day(n: int) -> dt.date:
    """n days before TODAY."""
    return TODAY - dt.timedelta(days=n)


def prompts(*responded: bool) -> list[CheckInPrompt]:
    """Oldest-first sequence of daily prompts; True = answered."""
    n = len(responded)
    return [CheckInPrompt(day(n - 1 - i), r) for i, r in enumerate(responded)]


def fake_assessment(outcome: Outcome, symptom: str = "swollen_ankles",
                    drug: str | None = None, days_ago: int = 12,
                    faers: FaersStatus = FaersStatus.SIGNAL) -> Assessment:
    meds = [Medication(drug, TODAY - dt.timedelta(days=days_ago))] if drug else []
    findings = ([DrugFinding(drug=drug, days_since_change=days_ago, status=faers,
                             detail="test fixture")] if drug else [])
    frailty = FrailtyComparison(
        status=FrailtyStatus.WITHIN_BAND, expected=0.857, observed=1.0,
        gap=0.143, trigger="test fixture",
    )
    return Assessment(
        outcome=outcome, symptom=symptom, person=MARGE, recent_meds=meds,
        drug_findings=findings, frailty=frailty, reasoning="test fixture",
    )


def show(n) -> str:
    return (f"{n.type.value:<18} urgency={n.urgency.value:<5} "
            f"push={str(n.push):<5}")


def main() -> None:
    results = []

    def check(label: str, condition: bool, extra: str = "") -> None:
        results.append(condition)
        print(f"  [{'PASS' if condition else 'FAIL'}] {label}"
              + (f"\n         {extra}" if extra else ""))

    print("=" * 78)
    print("MISSED CHECK-INS -- streak must reach "
          f"{MISSED_STREAK_THRESHOLD} consecutive")
    print("=" * 78)

    sequences = [
        ("no prompts at all",                 prompts(),                    0, False),
        ("all answered",                      prompts(True, True, True),    0, False),
        ("1 miss, most recent",               prompts(True, True, False),   1, False),
        ("1 miss then a response",            prompts(True, False, True),   0, False),
        ("2 consecutive misses",              prompts(True, False, False),  2, True),
        ("3 consecutive misses",              prompts(False, False, False), 3, True),
        ("2 misses then a response (reset)",  prompts(False, False, True),  0, False),
        ("misses split by a response",        prompts(False, True, False),  1, False),
        ("long gap then back on track",       prompts(False, False, False, True), 0, False),
    ]
    for label, seq, expect_streak, expect_fire in sequences:
        streak = consecutive_missed(seq)
        note = missed_checkin_notification(seq)
        fired = note is not None
        ok = streak == expect_streak and fired == expect_fire
        detail = f"streak={streak} (expected {expect_streak}), " \
                 f"fired={fired} (expected {expect_fire})"
        if note:
            detail += f"\n         -> {show(note)} {note.message}"
        check(f"{label:<34}", ok, detail)

    print("\n" + "=" * 78)
    print("OUTCOME TIERING")
    print("=" * 78)

    expectations = [
        (Outcome.MEDICATION_LINKED,     "amlodipine", NotificationType.CASCADE_FLAG,      Urgency.HIGH, True),
        (Outcome.UNEXPLAINED_DEVIATION, None,         NotificationType.CASCADE_FLAG,      Urgency.HIGH, True),
        (Outcome.INSUFFICIENT_HISTORY,  None,         NotificationType.NEEDS_MORE_DATA,   Urgency.NONE, False),
        (Outcome.QUERY_FAILED,          "amlodipine", NotificationType.CHECK_UNAVAILABLE, Urgency.NONE, False),
        (Outcome.WITHIN_EXPECTED,       None,         NotificationType.ROUTINE,           Urgency.NONE, False),
    ]
    for outcome, drug, want_type, want_urg, want_push in expectations:
        faers = (FaersStatus.SIGNAL if outcome is Outcome.MEDICATION_LINKED
                 else FaersStatus.QUERY_FAILED)
        a = fake_assessment(outcome, drug=drug, faers=faers)
        n = notification_for(a)
        ok = (n.type is want_type and n.urgency is want_urg and n.push is want_push)
        check(f"{outcome.value:<24} -> {want_type.value}/{want_urg.value}", ok,
              f"{show(n)}\n         {n.message}")

    print("\n" + "=" * 78)
    print("REALISTIC SEQUENCES")
    print("=" * 78)

    print("\n  1. One missed check-in, then she responds -- expect NOTHING")
    got = evaluate(prompts=prompts(True, False, True))
    check("no notification emitted", got == [], f"emitted {len(got)}")

    print("\n  2. Two consecutive misses -- expect ONE low-urgency push")
    got = evaluate(prompts=prompts(True, False, False))
    ok = (len(got) == 1 and got[0].urgency is Urgency.LOW and got[0].push
          and got[0].type is NotificationType.MISSED_CHECKINS)
    check("single LOW push", ok,
          "\n         ".join(f"{show(n)} {n.message}" for n in got))

    print("\n  3. MEDICATION_LINKED with a perfect check-in record --")
    print("     expect HIGH push regardless of check-in history")
    a = fake_assessment(Outcome.MEDICATION_LINKED, drug="amlodipine")
    got = evaluate(assessment=a, prompts=prompts(True, True, True))
    ok = (len(got) == 1 and got[0].urgency is Urgency.HIGH and got[0].push
          and got[0].type is NotificationType.CASCADE_FLAG)
    check("single HIGH push", ok,
          "\n         ".join(f"{show(n)} {n.message}" for n in got))
    check("detail names the implicated drug",
          got[0].detail.get("implicated_drug") == "amlodipine",
          str(got[0].detail))

    print("\n  4. MEDICATION_LINKED *and* a 2-miss streak -- expect BOTH,")
    print("     HIGH ordered before LOW")
    got = evaluate(assessment=a, prompts=prompts(True, False, False))
    ok = (len(got) == 2 and got[0].urgency is Urgency.HIGH
          and got[1].urgency is Urgency.LOW)
    check("HIGH then LOW", ok,
          "\n         ".join(f"{show(n)} {n.message}" for n in got))

    print("\n  5. QUERY_FAILED with a 2-miss streak -- the failed check must")
    print("     stay feed-only; only the nudge pushes")
    a_qf = fake_assessment(Outcome.QUERY_FAILED, drug="amlodipine",
                           faers=FaersStatus.QUERY_FAILED)
    got = evaluate(assessment=a_qf, prompts=prompts(True, False, False))
    pushed = [n for n in got if n.push]
    ok = (len(got) == 2 and len(pushed) == 1
          and pushed[0].type is NotificationType.MISSED_CHECKINS)
    check("exactly one push, and it is the nudge", ok,
          "\n         ".join(f"{show(n)} {n.message}" for n in got))

    print("\n  6. LLM triage sentence overrides the deterministic message")
    sentence = ("Amlodipine, started 12 days ago, may be linked to the swollen "
                "ankles, so it's worth discussing with the doctor.")
    n = notification_for(a, summary_sentence=sentence)
    check("message is the supplied sentence", n.message == sentence, n.message)

    print("\n" + "=" * 78)
    print("EVERY EMITTED MESSAGE MUST PASS THE LANGUAGE CHECKER")
    print("=" * 78)
    all_msgs = []
    for outcome, drug, *_ in expectations:
        all_msgs.append(notification_for(
            fake_assessment(outcome, drug=drug)).message)
    for seq in (prompts(True, False, False), prompts(False, False, False, False)):
        nn = missed_checkin_notification(seq)
        if nn:
            all_msgs.append(nn.message)
    for msg in all_msgs:
        hits = check_language(msg)
        check(f"clean: {msg[:64]}...", not hits, str(hits) if hits else "")

    print("\n" + "=" * 78)
    print(f"{sum(results)}/{len(results)} checks passed")
    print("=" * 78)
    raise SystemExit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
