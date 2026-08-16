# Check On

Catching **prescribing cascades** before the next prescription is written.

A prescribing cascade is a documented geriatric medicine problem: a medication's
side effect gets mistaken for a new medical condition, so a second medication is
prescribed to treat it — when the first drug only needed adjusting. It is common
and dangerous for older adults on multiple medications, and no consumer app
currently catches it before it happens.

> **Not a medical device.** This is a hackathon prototype. It does not diagnose,
> and nothing it outputs should change a medication without a clinician.

---

## How it decides

Two independent signals, combined by plain conditional rules. **They are
different kinds of thing and the code is careful not to conflate them.**

| Signal | What it is |
|---|---|
| **Frailty trajectory** | A model **trained** on NHANES 2011–2014, predicting the expected frailty score for a given age and sex, so we can tell whether someone sits outside the usual range for their profile. |
| **Medication–symptom link** | A **live statistical query** against the FDA Adverse Event Reporting System via openFDA, computing a Proportional Reporting Ratio. Nothing is trained or fitted — it is arithmetic over live counts. |

When a symptom is logged:

1. Was a medication started or changed in the last ~30 days? If not, skip FAERS
   entirely and use only the frailty comparison.
2. If yes, query FAERS for that drug + the symptom's mapped MedDRA terms.
3. Compare the person's recent check-ins against the population baseline.

Combined into one of five outcomes:

| Outcome | Meaning |
|---|---|
| `MEDICATION_LINKED` | Recent medication change + a FAERS signal — worth mentioning before a new prescription |
| `UNEXPLAINED_DEVIATION` | No medication link, but check-ins are outside the expected band — worth a checkup |
| `WITHIN_EXPECTED` | Consistent with the expected pattern — keep watching |
| `INSUFFICIENT_HISTORY` | Too few check-ins to compare against anything |
| `QUERY_FAILED` | The FAERS lookup could not run — **not** a negative result |

The last two exist so an *unevaluated* case is never reported as a reassuring one.

---

## Where the LLM is used

**Exactly one place:** turning the finished deterministic result into a single
plain-language sentence for the caregiver. There is no chatbot anywhere in this
app.

The frailty model, the FAERS query, the combining rules, and the notification
tiering are all deterministic code. Because the outcome is decided *before* the
model is called, a refusal, an outage, or a rejected sentence degrades to a
deterministic template without changing what the app concluded.

Every generated sentence passes two independent gates before it is returned:

- **Language check** — rejects false reassurance (`cleared`, `is safe`,
  `ruled out`, `nothing to worry about`, …). A no-signal FAERS result is
  *"no strong signal detected"*, never *"safe"*.
- **Grounding check** — rejects fabrication. If no medication was changed, the
  sentence may not name one or blame the symptom on medication at all; if one
  was, it may not name a different one.

A failure on either gate regenerates with the offending text named, up to three
attempts, then falls back to the template.

---

## Notification tiering

Built around alert fatigue — a caregiver who is pinged for everything stops
reading the pings.

| Event | Urgency | Push |
|---|---|---|
| Cascade flag (`MEDICATION_LINKED` / `UNEXPLAINED_DEVIATION`) | **HIGH** | yes |
| 2+ **consecutive** missed check-ins | **LOW** | yes |
| `INSUFFICIENT_HISTORY`, `QUERY_FAILED`, `WITHIN_EXPECTED` | none | feed only |

A single missed check-in is deliberately not a notification. Answering once
resets the streak.

---

## Layout

```
scripts/    data pipeline and model training (run once, in order)
  fetch_nhanes.py           download the NHANES cycles
  build_frailty_dataset.py  merge, clean sentinel codes, derive features
  score_frailty.py          adapted Fried frailty score
  train_baseline.py         fit and save the population baselines

backend/    runtime logic
  faers_prr.py        live openFDA disproportionality
  combining.py        the five-outcome decision rules
  triage_summary.py   the single LLM call + both output gates
  notifications.py    urgency tiering
  test_*.py           test suites
```

## Running it

```bash
pip install -r requirements.txt

python scripts/fetch_nhanes.py           # ~33 MB, not committed
python scripts/build_frailty_dataset.py
python scripts/score_frailty.py
python scripts/train_baseline.py

python backend/validate_faers.py         # positive + negative FAERS controls
python backend/test_combining.py
python backend/test_triage.py --offline  # no API key needed
python backend/test_notifications.py
```

The LLM step uses Groq's OpenAI-compatible endpoint and reads `GROQ_API_KEY`
from the environment:

```bash
GROQ_API_KEY=... python backend/test_triage.py
```

---

## Known limitations

These are stated plainly because they affect how the output should be read.

- **The frailty baseline is cross-sectional.** NHANES observes each participant
  once, so the model predicts the *typical* score for an age and sex. It is a
  band to compare against, not a per-person forecast, and it does not track
  individuals over time.
- **It explains very little individual variance** (R² ≈ 0.03). That is expected
  and fine for setting a band, but it must never be described as predicting a
  person's frailty.
- **Age is topcoded at 80** in NHANES, so the upper end of the curve is
  compressed.
- **The frailty score is an adapted 4-of-5 Fried phenotype**, not the clinical
  instrument — NHANES 2011–2014 has no timed walk, so gait speed is unavailable.
- **FAERS is not causal.** It is spontaneous, unverified, duplicated, and
  confounded, with no denominator of who actually took the drug. A PRR is a
  hypothesis generator.
- **Detection is weak for nonspecific symptoms.** Amlodipine + dizziness is a
  real labelled effect that scores PRR 1.86 and falls under the signal
  threshold. **Absence of a signal is not evidence of absence**, which is why
  the language gate exists.

## Data and methods

- NHANES 2011–2012 and 2013–2014, CDC/NCHS — the only cycles carrying the grip
  strength exam.
- Fried LP, Tangen CM, Walston J, et al. *Frailty in Older Adults: Evidence for
  a Phenotype.* J Gerontol A Biol Sci Med Sci. 2001;56(3):M146–M156.
- Evans SJW, Waller PC, Davis S. *Use of proportional reporting ratios (PRRs)
  for signal generation from spontaneous adverse drug reaction reports.*
  Pharmacoepidemiol Drug Saf. 2001;10(6):483–486.
- openFDA drug/event API (FAERS).
