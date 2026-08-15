"""Live FAERS disproportionality signal via the openFDA drug/event API.

WHAT THIS IS: a live statistical computation over the FDA Adverse Event
Reporting System, run at query time against openFDA. It is NOT a trained model
and nothing here is fitted or learned. Given a drug and a symptom, it asks a
single question -- is this symptom reported disproportionately often for this
drug, compared to how often it is reported for all other drugs? -- and answers
it with a Proportional Reporting Ratio computed from four counts.

WHAT A PRR IS NOT: evidence of causation. FAERS is a spontaneous, voluntary
reporting system. Reports are unverified, duplicated, biased by media attention
and litigation, confounded by the underlying illness, and carry no denominator
of how many people actually took the drug. openFDA's own documentation states
"a causal relationship cannot be established between product and reactions
listed in a report." A PRR is a hypothesis generator, nothing more.

Method and thresholds:
  PRR = [a / (a+b)] / [c / (c+d)]  over the 2x2 table

                        symptom Y     other symptoms    total
      drug X                a              b            a+b
      all other drugs       c              d            c+d

  Signal criteria (Evans SJW, Waller PC, Davis S. "Use of proportional
  reporting ratios (PRRs) for signal generation from spontaneous adverse drug
  reaction reports." Pharmacoepidemiol Drug Saf. 2001;10(6):483-486):
      a >= 3   AND   PRR >= 2   AND   chi-squared >= 4 (Yates-corrected)
  All three must hold; they are conjunctive. A pair can have thousands of cases
  and a huge chi-squared and still be noise if the PRR is near 1.

API facts verified against openFDA docs on 2026-08-15:
  endpoint     https://api.fda.gov/drug/event.json
  rate limit   240 req/min and 1,000 req/day per IP without an API key;
               240 req/min and 120,000 req/day with a key (api_key= param)
  count field  meta.results.total gives the number of matching REPORTS
"""

from __future__ import annotations

import json
import math
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

ENDPOINT = "https://api.fda.gov/drug/event.json"
API_KEY = os.environ.get("OPENFDA_API_KEY")

# Evans et al. 2001 signal criteria.
MIN_CASES = 3
MIN_PRR = 2.0
MIN_CHI2 = 4.0


# --- symptom icon -> MedDRA Preferred Terms ------------------------------
# Every term below was verified to exist in live FAERS data with a nonzero
# report count; the counts in comments are reports as of the 2026-07-30 data
# release. Two things make this mapping non-obvious and worth being explicit
# about, rather than trusting that our casual word matches FAERS's term:
#   1. MedDRA uses British spellings -- DIARRHOEA, OEDEMA, DYSPNOEA.
#   2. Our everyday words do not map 1:1 onto MedDRA PTs. "Tired" and "weak"
#      both partly cover ASTHENIA, which MedDRA defines as generalised weakness
#      / lack of energy. It is assigned to "weak" only, so the two icons stay
#      disjoint and a single report cannot inflate both.
# Terms deliberately excluded and why:
#   FEELING ABNORMAL (237k) -- too vague to attribute to any one icon.
#   SYNCOPE (99k)           -- actual loss of consciousness, a different and
#                              more severe event than "dizzy".
#   GAIT DISTURBANCE (189k) -- unsteadiness rather than weakness; belongs to a
#                              future "unsteady/falls" icon, not "weak".
#   HYPOTONIA (10k)         -- overwhelmingly a paediatric finding.
SYMPTOM_TO_MEDDRA: dict[str, list[str]] = {
    "dizzy": [
        "DIZZINESS",           # 491,281
        "VERTIGO",             #  60,181
        "BALANCE DISORDER",    #  85,436
        "PRESYNCOPE",          #  23,880
        "DIZZINESS POSTURAL",  #   9,477
    ],
    "tired": [
        "FATIGUE",             # 766,572
        "MALAISE",             # 433,770
        "SOMNOLENCE",          # 198,395
        "LETHARGY",            #  56,759
    ],
    "foggy": [
        "CONFUSIONAL STATE",        # 159,771
        "MEMORY IMPAIRMENT",        # 135,738
        "DISTURBANCE IN ATTENTION", #  53,370
        "COGNITIVE DISORDER",       #  45,910
        "DELIRIUM",                 #  34,124
        "MENTAL IMPAIRMENT",        #  23,950
        "BRAIN FOG",                #  14,398
    ],
    "weak": [
        "ASTHENIA",           # 371,064
        "MUSCULAR WEAKNESS",  # 112,152
        "MOBILITY DECREASED", #  70,680
        "MUSCLE FATIGUE",     #   4,173
    ],
    "nauseous": [
        "NAUSEA",    # 778,541
        "VOMITING",  # 462,654
        "RETCHING",  #  20,987
    ],
    # Single-term on purpose. OEDEMA PERIPHERAL is the trigger symptom of the
    # canonical prescribing cascade (dihydropyridine CCB -> ankle oedema ->
    # misread as fluid overload -> loop diuretic added), and it is the one icon
    # here with strong detection power: PRR 3.5 for amlodipine. Broadening it
    # with vaguer oedema terms would raise the background rate and dilute that.
    "swollen_ankles": [
        "OEDEMA PERIPHERAL",  # 120,713
    ],
}

# --- drug name resolution -------------------------------------------------
# FAERS records whatever the reporter typed, so the same drug appears as a
# generic, a brand, a salt form, and with stray punctuation ("AMLODIPINE",
# "AMLODIPINE BESYLATE", "AMLODIPINE BESYLATE.", "NORVASC"). openFDA layers a
# harmonised `openfda` block on top, mapping the reported product to a
# normalised SPL entry; 18,380,981 of 20,692,690 reports (88.8%) carry one.
#
# Measured on amlodipine, the strategies differ by a lot:
#     openfda.generic_name:"amlodipine"          439,001
#     medicinalproduct:"amlodipine"  (tokenised) 372,677
#     medicinalproduct.exact:"AMLODIPINE"        267,877
# and on the brand name the gap is decisive -- of 80,472 NORVASC reports,
# generic_name catches 78,982 (98.1%) while medicinalproduct catches 4,921
# (6.1%). So harmonised fields are tried first and the raw free-text field is
# only a fallback for drugs with no SPL match. The strategy that actually
# matched is always returned on the result, never chosen silently.
DRUG_STRATEGIES: list[tuple[str, str]] = [
    ("openfda.generic_name", 'patient.drug.openfda.generic_name:"{drug}"'),
    ("openfda.substance_name", 'patient.drug.openfda.substance_name:"{drug}"'),
    ("medicinalproduct", 'patient.drug.medicinalproduct:"{drug}"'),
]


class OpenFDAError(RuntimeError):
    """Raised when openFDA cannot be queried reliably."""


def _request_total(search: str | None, tries: int = 5) -> int:
    """Number of REPORTS matching `search`, from meta.results.total.

    openFDA intermittently answers HTTP 200 with a silently truncated total
    when its backend is under load -- observed returning 8,275,576 for a query
    whose stable answer is 20,692,690. There is no flag on the response saying
    so, which is why callers must check the containment invariants in
    Counts.validate() rather than trusting any single number.
    """
    params: dict[str, str | int] = {"limit": 1}
    if search:
        params["search"] = search
    if API_KEY:
        params["api_key"] = API_KEY
    url = ENDPOINT + "?" + urllib.parse.urlencode(params, quote_via=urllib.parse.quote)

    last = ""
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=90) as resp:
                payload = json.load(resp)
            return int(payload["meta"]["results"]["total"])
        except urllib.error.HTTPError as exc:
            # openFDA returns 404 for a valid query with zero matches.
            if exc.code == 404:
                return 0
            last = f"HTTP {exc.code}"
        except Exception as exc:  # noqa: BLE001 - network/JSON, all retryable
            last = type(exc).__name__
        if attempt < tries - 1:
            time.sleep(2 ** attempt)
    raise OpenFDAError(f"openFDA failed after {tries} tries ({last}): {url}")


def _reaction_clause(terms: list[str]) -> str:
    """OR the MedDRA terms into one clause; matches a report with ANY of them."""
    joined = " OR ".join(f'"{t}"' for t in terms)
    return f"patient.reaction.reactionmeddrapt.exact:({joined})"


@dataclass
class Counts:
    """The 2x2 table, plus the queries that produced it."""

    a: int  # drug AND reaction
    b: int  # drug, other reactions
    c: int  # reaction, other drugs
    d: int  # everything else
    n_total: int
    queries: dict[str, str] = field(default_factory=dict)

    def validate(self) -> None:
        """Containment invariants -- these catch truncated openFDA responses."""
        if min(self.a, self.b, self.c, self.d) < 0:
            raise OpenFDAError(f"negative cell in 2x2 table: {self}")
        if self.a > self.a + self.b or self.a > self.a + self.c:
            raise OpenFDAError(f"a exceeds its margin: {self}")
        if (self.a + self.b) > self.n_total or (self.a + self.c) > self.n_total:
            raise OpenFDAError(
                f"margin exceeds database total -- likely a truncated "
                f"openFDA response: drug={self.a + self.b:,}, "
                f"reaction={self.a + self.c:,}, total={self.n_total:,}"
            )


@dataclass
class PRRResult:
    drug: str
    symptom: str
    meddra_terms: list[str]
    drug_field: str
    counts: Counts
    prr: float
    chi2: float
    ci_low: float
    ci_high: float

    @property
    def is_signal(self) -> bool:
        """All three Evans criteria, conjunctively."""
        return (
            self.counts.a >= MIN_CASES
            and self.prr >= MIN_PRR
            and self.chi2 >= MIN_CHI2
        )

    def failed_criteria(self) -> list[str]:
        out = []
        if self.counts.a < MIN_CASES:
            out.append(f"cases {self.counts.a} < {MIN_CASES}")
        if self.prr < MIN_PRR:
            out.append(f"PRR {self.prr:.2f} < {MIN_PRR}")
        if self.chi2 < MIN_CHI2:
            out.append(f"chi2 {self.chi2:.2f} < {MIN_CHI2}")
        return out


def _chi2_yates(a: int, b: int, c: int, d: int) -> float:
    """Pearson chi-squared with Yates's continuity correction.

    chi2 = N(|ad - bc| - N/2)^2 / [(a+b)(c+d)(a+c)(b+d)]
    Yates correction is the convention Evans et al. applied.
    """
    n = a + b + c + d
    denom = (a + b) * (c + d) * (a + c) * (b + d)
    if denom == 0:
        return 0.0
    return n * (abs(a * d - b * c) - n / 2) ** 2 / denom


def _prr_ci(a: int, b: int, c: int, d: int, prr: float) -> tuple[float, float]:
    """95% CI on the PRR, via the standard delta-method SE on log(PRR)."""
    if a == 0 or c == 0:
        return (float("nan"), float("nan"))
    se = math.sqrt(1 / a - 1 / (a + b) + 1 / c - 1 / (c + d))
    return (prr * math.exp(-1.96 * se), prr * math.exp(1.96 * se))


def resolve_drug(drug: str) -> tuple[str, str, int]:
    """Find which openFDA field matches this drug name.

    Returns (field_label, search_clause, report_count) for the first strategy
    with a nonzero count. Raises if no strategy matches at all.
    """
    for label, template in DRUG_STRATEGIES:
        clause = template.format(drug=drug.lower())
        count = _request_total(clause)
        if count > 0:
            return label, clause, count
    raise OpenFDAError(f"no openFDA field matched drug name {drug!r}")


def compute_prr(drug: str, symptom: str, terms: list[str] | None = None) -> PRRResult:
    """PRR for one drug + one symptom icon, from four live openFDA counts.

    `symptom` is one of SYMPTOM_TO_MEDDRA's keys; pass `terms` to override the
    mapping with explicit MedDRA Preferred Terms.
    """
    if terms is None:
        if symptom not in SYMPTOM_TO_MEDDRA:
            raise KeyError(
                f"unknown symptom {symptom!r}; known: {sorted(SYMPTOM_TO_MEDDRA)}"
            )
        terms = SYMPTOM_TO_MEDDRA[symptom]

    drug_field, drug_clause, n_drug = resolve_drug(drug)
    rx_clause = _reaction_clause(terms)

    a = _request_total(f"{drug_clause} AND {rx_clause}")
    n_reaction = _request_total(rx_clause)
    n_total = _request_total(None)

    counts = Counts(
        a=a,
        b=n_drug - a,
        c=n_reaction - a,
        d=n_total - n_drug - (n_reaction - a),
        n_total=n_total,
        queries={
            "a  (drug AND reaction)": f"{drug_clause} AND {rx_clause}",
            "a+b (drug, any reaction)": drug_clause,
            "a+c (reaction, any drug)": rx_clause,
            "N  (all reports)": "<no search parameter>",
        },
    )
    counts.validate()

    a_, b_, c_, d_ = counts.a, counts.b, counts.c, counts.d
    exposed = a_ / (a_ + b_) if (a_ + b_) else 0.0
    background = c_ / (c_ + d_) if (c_ + d_) else 0.0
    prr = exposed / background if background else float("inf")
    lo, hi = _prr_ci(a_, b_, c_, d_, prr)

    return PRRResult(
        drug=drug,
        symptom=symptom,
        meddra_terms=terms,
        drug_field=drug_field,
        counts=counts,
        prr=prr,
        chi2=_chi2_yates(a_, b_, c_, d_),
        ci_low=lo,
        ci_high=hi,
    )
