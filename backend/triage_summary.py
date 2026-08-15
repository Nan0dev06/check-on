"""The one place in this app where an LLM does generative work.

Everything upstream is deterministic: the frailty baseline is a fitted linear
model, the FAERS disproportionality is a live arithmetic computation, and the
combining logic is plain conditionals. None of them call a model. This module
takes the finished Assessment object and writes ONE plain-language sentence for
a busy, non-technical caregiver. It decides nothing.

That separation is the safety property. Because the outcome is already fixed
before the model is called, a refusal, an API outage, or a sentence that trips
the language checker can all fall back to a deterministic template without
changing what the app concluded. The LLM is a presentation layer, and it is
never load-bearing.

LANGUAGE RULE, enforced by code and not just by prompt:
Every generated sentence is scanned for false-reassurance vocabulary before it
is returned. A sentence that trips the checker is regenerated with the offending
words named, up to MAX_ATTEMPTS, and then replaced by the template. This matters
because detection power for nonspecific symptoms in this pipeline is genuinely
weak -- amlodipine + dizziness is a real, labelled effect that scores PRR 1.86
and falls under threshold -- so "no signal" must never be phrased as "safe".
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

from openai import OpenAI, OpenAIError

from combining import Assessment, FaersStatus, Outcome

# --- provider -------------------------------------------------------------
# Groq, via its OpenAI-compatible endpoint. The `openai` package is only the
# HTTP client for that wire format here -- no request goes to OpenAI.
GROQ_BASE_URL = "https://api.groq.com/openai/v1"

# MODEL CHOICE -- read this before changing it.
# There is no longer a Llama model on Groq that can serve this. Both Llama
# production models (llama-3.1-8b-instant, llama-3.3-70b-versatile) were
# deprecated 2026-06-17 with a shutdown date of 2026-08-16, and Groq's own
# migration guidance points at openai/gpt-oss-20b and openai/gpt-oss-120b.
# `openai/gpt-oss-120b` is an OpenAI OPEN-WEIGHT model running on Groq hardware
# -- the name is confusing, but this is still a Groq API call. Production tier,
# free-tier eligible.
#
# Chosen over gpt-oss-20b on a head-to-head across all 11 cases: 20b fabricated
# a medication on case 6b (which has NO medications at all), got a timeline
# wrong on case 6, drifted into clinical third person, and leaked the internal
# term "medication cascade". Throughput is irrelevant here -- this is one short
# sentence per check-in, so instruction-following wins over speed.
MODEL = "openai/gpt-oss-120b"

# gpt-oss is a reasoning model. On Groq its reasoning goes to a separate
# `message.reasoning` field rather than into `message.content`, so it cannot
# pollute the sentence -- but we strip <think> blocks defensively anyway.
REASONING_EFFORT = "low"

MAX_ATTEMPTS = 3
# Reasoning tokens are generated (and counted) even though they land in a
# separate field, so this budget covers reasoning + the sentence. Too low and
# every call comes back finish_reason='length' and falls through to a template.
MAX_TOKENS = 512

# --- the language checker -------------------------------------------------
# Extends the hand-written-string list from the combining module to cover what
# a generative model might reach for. Matched with word boundaries so that
# "abnormal" does not trip "normal" and "define" does not trip "fine".
BANNED_PATTERNS: list[str] = [
    r"cleared", r"all clear", r"in the clear",
    # Phrases, not the bare word: banning "safe"/"safety" outright also killed
    # legitimate wording like "medication safety review". Covers copular verbs
    # generally -- an adversarial run produced "but she remains safe", which an
    # is/are/was-only list scored as clean.
    r"(?:is|are|was|were|be|been|being|remains?|stays?|seems?|appears?|"
    r"looks?|feels?)\s+safe",
    r"(?:he|she|it|they)'?s\s+safe",
    r"considered safe", r"perfectly safe", r"completely safe", r"totally safe",
    r"safe to (continue|take|keep|use|stay)",
    r"no risk", r"risk[- ]free", r"not a risk", r"low risk",
    r"ruled? out", r"rules out",
    r"nothing to worry", r"no need to worry", r"don'?t worry",
    r"no cause for concern", r"no concern", r"nothing concerning",
    r"harmless", r"benign", r"healthy",
    r"reassur\w*",
    r"nothing wrong", r"no problem", r"nothing serious",
    r"fine", r"okay", r"ok",
]
_BANNED_RE = [(p, re.compile(rf"\b{p}\b", re.IGNORECASE)) for p in BANNED_PATTERNS]

# The models emit typographic Unicode -- U+2019 curly apostrophe and U+2011
# non-breaking hyphen both appear in real output ("it's", "74-year-old",
# "check-ins"). The patterns are written with ASCII ' and -, so without this
# normalisation "risk-free" and "can't help" slip through when the model spells
# them with the Unicode forms. Verified: the ASCII spellings were caught and
# the Unicode spellings were not.
_PUNCT = str.maketrans({
    "‘": "'", "’": "'", "ʼ": "'",          # curly apostrophes
    "“": '"', "”": '"',                          # curly quotes
    "‐": "-", "‑": "-", "‒": "-",           # hyphen variants
    "–": "-", "—": "-", "−": "-",           # dashes, minus
    " ": " ", " ": " ", " ": " ",           # non-breaking spaces
})


def normalize(text: str) -> str:
    """Fold typographic punctuation to ASCII so the patterns can match."""
    return text.translate(_PUNCT)


def check_language(text: str) -> list[str]:
    """Return the offending SUBSTRINGS found in `text`, if any.

    Returns what the model actually wrote ("remains safe"), not the pattern
    that matched it -- this list is fed straight back to the model as the
    reason for rejection, and a raw regex is not actionable feedback.
    """
    t = normalize(text)
    hits = []
    for _pattern, rx in _BANNED_RE:
        m = rx.search(t)
        if m:
            hits.append(m.group(0))
    return hits


# --- prompt ---------------------------------------------------------------
SYSTEM = """\
You write a single sentence for the caregiver of an older adult, inside an app \
that watches for prescribing cascades (a medication's side effect being \
mistaken for a new condition and treated with another medication).

You are given the finished result of a deterministic analysis. Your only job is \
to say it in plain language. Do not re-analyse, do not add medical advice, do \
not add facts that are not in the input, and do not diagnose.

Rules:
- Exactly ONE sentence. No preamble, no greeting, no sign-off, no quotation \
marks. Output only the sentence.
- Plain language for a busy non-expert. No jargon: never write PRR, \
disproportionality, FAERS, MedDRA, percentile, frailty score, or a statistic.
- Name the medication and the symptom when they are given to you.
- NEVER imply the person has been checked and found well. Specifically, never \
use the words: cleared, safe, safety, no risk, ruled out, fine, okay, healthy, \
benign, harmless, reassuring, nothing to worry about, no cause for concern.
- A negative or missing result means "we did not detect anything", never "there \
is nothing there". Absence of a signal is not evidence of absence.
- Be calm. This is a nudge to a caregiver, not an alarm."""

# Per-outcome tone. These are the distinct registers the caregiver needs to be
# able to tell apart at a glance.
TONE: dict[Outcome, str] = {
    Outcome.MEDICATION_LINKED: (
        "ACTIONABLE. There is a plausible link between a recently started "
        "medication and this symptom. Tell the caregiver it is worth raising "
        "with the doctor -- specifically before any new medication is added to "
        "treat the symptom. Do not tell them to stop the medication."
    ),
    Outcome.WITHIN_EXPECTED: (
        "CALM, NOT DISMISSIVE. Nothing stood out this time. Say that the symptom "
        "was noted and is being tracked, and that watching continues. Do not "
        "suggest the person is well or that the symptom does not matter."
    ),
    Outcome.UNEXPLAINED_DEVIATION: (
        "ATTENTIVE BUT NOT ALARMING. This does not match a recent medication "
        "change, and the check-ins have moved outside the usual range for this "
        "person's age. Suggest mentioning it at the next appointment. Do not "
        "use urgent or frightening language, and do not speculate about causes."
    ),
    Outcome.INSUFFICIENT_HISTORY: (
        "WE DON'T KNOW YET. There are too few check-ins to compare against "
        "anything. Say plainly that there is not enough information yet and that "
        "a few more daily check-ins will make the comparison possible. This is "
        "NOT good news and must not sound like it."
    ),
    Outcome.QUERY_FAILED: (
        "WE DON'T KNOW YET. The medication database could not be reached, so the "
        "check did not run. Say plainly that the check could not be completed "
        "and will be retried. This is a technical failure, NOT a result -- it "
        "must not sound like anything was checked and found acceptable."
    ),
}

# Deterministic fallbacks. Used when the model refuses, the API is unreachable,
# or MAX_ATTEMPTS generations all trip the language checker. Deliberately dull.
FALLBACK: dict[Outcome, str] = {
    Outcome.MEDICATION_LINKED: (
        "{symptom} started after {drug} was begun {days} days ago, and this "
        "symptom is often reported with that medication, so it is worth asking "
        "the doctor about before anything new is prescribed for it."
    ),
    Outcome.WITHIN_EXPECTED: (
        "{symptom} was noted and did not stand out against the recent check-ins, "
        "so it will keep being tracked."
    ),
    Outcome.UNEXPLAINED_DEVIATION: (
        "{symptom} was noted and the recent check-ins have moved outside the "
        "usual range for this age, which does not line up with a recent "
        "medication change, so it is worth mentioning at the next appointment."
    ),
    Outcome.INSUFFICIENT_HISTORY: (
        "{symptom} was noted, but there are not enough check-ins yet to compare "
        "it against anything, so a few more daily check-ins are needed."
    ),
    Outcome.QUERY_FAILED: (
        "{symptom} was noted after a recent medication change, but the "
        "medication database could not be reached, so that check still needs to "
        "be run."
    ),
}


# The icon keys are adjectives ("dizzy", "weak"), which read badly in a
# sentence -- "Weak was noted". The model would fix this on its own, but the
# fallback templates are what ship when it can't, so they need real nouns.
SYMPTOM_LABEL: dict[str, str] = {
    "dizzy": "dizziness",
    "tired": "tiredness",
    "foggy": "confusion or brain fog",
    "weak": "weakness",
    "nauseous": "nausea",
    "swollen_ankles": "swollen ankles",
}


def label_for(symptom: str) -> str:
    return SYMPTOM_LABEL.get(symptom, symptom.replace("_", " "))


@dataclass
class TriageSummary:
    sentence: str
    outcome: Outcome
    source: str          # "model" | "fallback"
    attempts: int
    rejected: list[str]  # sentences rejected by the language checker
    note: str = ""


def build_prompt(a: Assessment) -> str:
    """Serialise only the fields the sentence is allowed to mention."""
    lines = [
        f"OUTCOME: {a.outcome.value}",
        f"TONE REQUIRED: {TONE[a.outcome]}",
        "",
        f"Symptom the person tapped: {label_for(a.symptom)}",
        f"Person: {a.person.age}-year-old {a.person.sex}",
    ]

    if not a.recent_meds:
        lines.append("No medication was started or changed in the last 30 days.")

    # drug_findings is built one-per-recent-med, so it carries both the name and
    # how long ago the change was.
    for f in a.drug_findings:
        lines.append(f"Medication {f.drug} was started or changed "
                     f"{f.days_since_change} days ago.")
        if f.status is FaersStatus.SIGNAL:
            lines.append(
                f"FDA reports: this symptom IS reported disproportionately often "
                f"for {f.drug}."
            )
        elif f.status is FaersStatus.NO_STRONG_SIGNAL:
            lines.append(
                f"FDA reports: no strong association was detected between "
                f"{f.drug} and this symptom. This does NOT mean there is none."
            )
        else:
            lines.append(f"FDA reports: the lookup for {f.drug} failed to run.")

    lines.append(f"Frailty check-in comparison: {a.frailty.trigger}")
    lines.append("")
    lines.append("Write the one sentence now.")
    return "\n".join(lines)


def _fallback_sentence(a: Assessment) -> str:
    signal = next((f for f in a.drug_findings
                   if f.status is FaersStatus.SIGNAL), None)
    ref = signal or (a.drug_findings[0] if a.drug_findings else None)
    return FALLBACK[a.outcome].format(
        symptom=label_for(a.symptom).capitalize(),
        drug=ref.drug if ref else "the medication",
        days=ref.days_since_change if ref else 0,
    )


# --- detecting a blocked or incomplete generation on Groq -----------------
# This does NOT mirror Anthropic's shape and could not be ported directly.
#
# Anthropic signals a policy decline in-band: HTTP 200 with
# stop_reason == "refusal" and a stop_details category. Groq has no equivalent.
# Its finish_reason enum, taken from the generated SDK types (groq 1.4.0,
# groq.types.chat.chat_completion.Choice), is exactly:
#
#     Literal["stop", "length", "tool_calls", "function_call"]
#
# Note what is missing: OpenAI's enum for the same field includes
# "content_filter"; Groq's does not. That is consistent with Groq's content
# moderation docs, which state that moderation is NOT automatic on the chat
# endpoint -- developers must call a separate safeguard model (Llama Prompt
# Guard, GPT-OSS-Safeguard) themselves. So there is no provider-side refusal
# signal to check at all.
#
# What that leaves us detecting, in order:
#   1. Transport/API failure     -> exception
#   2. finish_reason "length"    -> truncated mid-sentence; unusable
#   3. finish_reason tool_calls/function_call -> no text (we declare no tools)
#   4. empty or whitespace content
#   5. a SOFT refusal in the prose ("I'm sorry, I can't...") -- with no API
#      flag, the only place a refusal can show up is the text itself
FINISH_TRUNCATED = "length"
FINISH_NO_TEXT = {"tool_calls", "function_call"}

# A refusal is identified by its OBJECT (help / assist / provide / comply),
# never by a bare modal. "cannot", "can't", and "unable to" on their own are
# exactly the hedging this app WANTS -- "cannot rule out a medication effect"
# is the ideal MEDICATION_LINKED sentence, and matching the bare modal would
# throw it away and substitute the blander template, defeating the point of
# calling a live model.
SOFT_REFUSAL_PATTERNS: list[str] = [
    r"as an ai",
    r"i (?:cannot|can'?t|won'?t|will not) (?:help|assist|provide|comply|answer)",
    r"i(?:'m| am) (?:not able|unable) to (?:help|assist|provide|comply|answer)",
    r"i(?:'m| am) sorry,? but i",
    r"i must decline",
    r"i don'?t feel comfortable",
    r"i'?m not going to (?:help|provide|write)",
    r"(?:unable to|can'?t|cannot) (?:help|assist) with (?:that|this)",
]
_SOFT_REFUSAL = [(p, re.compile(p, re.IGNORECASE)) for p in SOFT_REFUSAL_PATTERNS]


def check_refusal(text: str) -> list[str]:
    """Return the matched refusal substrings. Empty means it is not a refusal."""
    t = normalize(text)
    hits = []
    for _pattern, rx in _SOFT_REFUSAL:
        m = rx.search(t)
        if m:
            hits.append(m.group(0))
    return hits


# --- factual grounding ----------------------------------------------------
# Separate from the reassurance checker, and catching a different class of
# error. The language checker polices TONE; this one polices TRUTH. A sentence
# can be perfectly non-reassuring and still be entirely invented -- gpt-oss-20b
# produced exactly that on case 6b, which has no medications at all:
#
#   "...suggest a possible medication side-effect to discuss at her next
#    appointment."
#
# Note what that sentence does NOT contain: a drug name. So name-extraction
# alone would have missed it, which is why this check has two arms --
# (1) named drugs must be grounded in the assessment's data, and
# (2) when no medication is involved, the sentence may not ATTRIBUTE the
#     symptom to medication at all.
#
# Lexicon covers the drugs this project exercises plus common geriatric
# prescriptions, so a fabricated-but-plausible name is still caught. A
# fabricated name outside the lexicon would slip arm (1) -- arm (2) is the
# backstop for the case that actually matters (no medication involved).
KNOWN_DRUGS: set[str] = {
    "amlodipine", "norvasc", "oxybutynin", "ditropan", "levothyroxine",
    "synthroid", "atorvastatin", "lipitor", "simvastatin", "zocor",
    "digoxin", "lanoxin", "furosemide", "lasix", "zolpidem", "ambien",
    "amitriptyline", "lisinopril", "metformin", "omeprazole", "pantoprazole",
    "aspirin", "warfarin", "apixaban", "metoprolol", "atenolol", "losartan",
    "hydrochlorothiazide", "gabapentin", "sertraline", "citalopram",
    "donepezil", "memantine", "prednisone", "tramadol", "oxycodone",
    "diazepam", "lorazepam", "ibuprofen", "ranitidine", "famotidine",
    "spironolactone", "allopurinol", "tamsulosin", "finasteride",
}

# Generic attribution: blaming the symptom on medication without naming one.
_ATTRIBUTION = re.compile(
    r"(?:side[-\s]?effects?\s+of|linked to|caused by|due to|related to|"
    r"because of|reaction to|result of|from)\s+(?:\w+\s+){0,3}?"
    r"(?:medication|medicine|drug|prescription|pill)s?"
    r"|(?:medication|medicine|drug)[-\s]?(?:side[-\s]?effects?|related|induced)",
    re.IGNORECASE,
)
# A correct sentence may legitimately SAY there is no medication link ("isn't
# linked to any recent medication change"). Look back a short window for a
# negator before treating an attribution as a claim. Heuristic, not a parser.
_NEGATOR = re.compile(
    r"\b(?:not|no|never|without|nor|unlikely|unrelated|"
    r"isn'?t|aren'?t|wasn'?t|weren'?t|hasn'?t|haven'?t|hadn'?t|"
    r"doesn'?t|don'?t|didn'?t|cannot|can'?t|couldn'?t|won'?t|wouldn'?t|"
    r"shouldn'?t|rules? out|ruled out)\b",
    re.IGNORECASE,
)
_NEGATION_WINDOW = 60


def find_drugs(text: str, extra: set[str] = frozenset()) -> set[str]:
    """Drug names mentioned in `text`, from the lexicon plus `extra`."""
    t = normalize(text).lower()
    return {d for d in (KNOWN_DRUGS | {e.lower() for e in extra})
            if re.search(rf"\b{re.escape(d)}\b", t)}


def check_grounding(text: str, a: Assessment) -> list[str]:
    """Return grounding violations. Empty means the sentence is supported."""
    actual = {m.name.lower() for m in a.recent_meds}
    named = find_drugs(text, extra=actual)
    problems: list[str] = []

    if not actual:
        if named:
            problems.append(
                f"names the medication {sorted(named)} but no medication was "
                f"started or changed for this person")
        t = normalize(text)
        for m in _ATTRIBUTION.finditer(t):
            window = t[max(0, m.start() - _NEGATION_WINDOW):m.start()]
            if not _NEGATOR.search(window):
                problems.append(
                    f"blames the symptom on medication ({m.group(0)!r}) when no "
                    f"medication was started or changed for this person")
                break
    else:
        ungrounded = named - actual
        if ungrounded:
            problems.append(
                f"names the medication {sorted(ungrounded)}, which is not in "
                f"this person's data (only {sorted(actual)} was changed)")
    return problems
_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL)


def make_client(api_key: str | None = None) -> OpenAI:
    """OpenAI-protocol client pointed at Groq."""
    key = api_key or os.environ.get("GROQ_API_KEY")
    if not key:
        raise RuntimeError("GROQ_API_KEY is not set")
    # Groq's free tier is 30 req/min and 6,000 tokens/min. The token limit is
    # the binding one here, so let the SDK back off and retry a 429 rather than
    # letting it surface as an error and silently degrade to a template.
    return OpenAI(base_url=GROQ_BASE_URL, api_key=key, max_retries=5)


def summarize(a: Assessment, client: OpenAI | None = None,
              model: str = MODEL) -> TriageSummary:
    """Turn a finished Assessment into one caregiver-facing sentence."""
    if client is None:
        client = make_client()

    prompt = build_prompt(a)
    rejected: list[tuple[str, str]] = []  # (sentence, why it was rejected)

    def bail(note: str, attempt: int) -> TriageSummary:
        return TriageSummary(
            sentence=_fallback_sentence(a), outcome=a.outcome, source="fallback",
            attempts=attempt, rejected=rejected, note=note,
        )

    for attempt in range(1, MAX_ATTEMPTS + 1):
        user = prompt
        if rejected:
            last_text, why = rejected[-1]
            user += (
                f"\n\nYour previous attempt was REJECTED. {why}\n"
                f"Rejected sentence: {last_text!r}\n"
                f"Write the sentence again, fixing that problem and keeping "
                f"every other rule."
            )

        try:
            resp = client.chat.completions.create(
                model=model,
                max_tokens=MAX_TOKENS,
                reasoning_effort=REASONING_EFFORT,
                messages=[
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": user},
                ],
            )
        except OpenAIError as exc:
            return bail(f"Groq call failed ({type(exc).__name__}: {exc}); "
                        f"used template.", attempt)

        choice = resp.choices[0]
        finish = choice.finish_reason

        if finish == FINISH_TRUNCATED:
            return bail(
                f"Generation hit the {MAX_TOKENS}-token cap (finish_reason="
                f"'length') and was cut off mid-sentence; used template.", attempt)
        if finish in FINISH_NO_TEXT:
            return bail(f"Unexpected finish_reason='{finish}' with no text "
                        f"(no tools are declared); used template.", attempt)

        text = (choice.message.content or "")
        text = _THINK_BLOCK.sub("", text).strip().strip('"').strip()

        if not text:
            return bail(f"Model returned empty content (finish_reason="
                        f"'{finish}'); used template.", attempt)
        refusal = check_refusal(text)
        if refusal:
            # Groq gives no refusal flag, so a decline can only be caught here.
            return bail(f"Model declined in prose {refusal} ({text[:60]!r}); "
                        f"used template.", attempt)

        # Two independent gates. Language polices tone, grounding polices truth;
        # a sentence has to clear both, and either one sends it back with the
        # specific reason attached.
        banned = check_language(text)
        if banned:
            rejected.append((text, (
                "It used language implying the person has been checked and "
                f"found well, which is not permitted. Offending wording: "
                f"{', '.join(banned)}. Do not use those words.")))
            continue

        unsupported = check_grounding(text, a)
        if unsupported:
            rejected.append((text, (
                "It stated something the data does not support: "
                f"{'; '.join(unsupported)}. Only mention medications that "
                "appear in the input above, and do not attribute the symptom "
                "to a medication unless the input says one was changed.")))
            continue

        return TriageSummary(
            sentence=text, outcome=a.outcome, source="model",
            attempts=attempt, rejected=rejected,
        )

    return bail(f"All {MAX_ATTEMPTS} generations were rejected "
                f"({rejected[-1][1][:80]}...); used template.", MAX_ATTEMPTS)
