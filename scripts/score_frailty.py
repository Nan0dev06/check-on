"""Adapted Fried Frailty Phenotype score (0-4) for NHANES 2011-2014, age 60+.

IMPORTANT -- this is a 4-of-5-criteria ADAPTATION, not the full clinical
instrument. The fifth Fried criterion, slowness (gait speed over 15 ft / 4 m),
has no timed-walk measurement in NHANES 2011-2014, so it cannot be scored. A
score here therefore runs 0-4 rather than 0-5, and Fried's clinical thresholds
(>=3 of 5 = frail, 1-2 = pre-frail) do NOT carry over unchanged. We use the
score as a continuous severity target for the baseline model, not as a clinical
frailty diagnosis.

Cutoffs are from the original source, not re-derived:
  Fried LP, Tangen CM, Walston J, et al. "Frailty in Older Adults: Evidence for
  a Phenotype." J Gerontol A Biol Sci Med Sci. 2001;56(3):M146-M156. Appendix,
  "Criteria Used to Define Frailty".

Two criteria need an instrument adaptation because NHANES does not field the
questionnaires CHS used; both are documented at their definitions below.
"""

import numpy as np
import pandas as pd

# --- Weakness -----------------------------------------------------------
# Fried 2001 Appendix, grip strength stratified by sex and BMI quartile.
# Criterion is met at or below the listed value (<=). Values are kg.
# Fried specifies max of 3 trials with the DOMINANT hand; NHANES randomizes
# test order and never records handedness, so grip_max_kg (max across both
# hands) is substituted -- see build_frailty_dataset.derive().
GRIP_CUTOFFS = {
    1: [(24.0, 29.0), (26.0, 30.0), (28.0, 30.0), (np.inf, 32.0)],  # men
    2: [(23.0, 17.0), (26.0, 17.3), (29.0, 18.0), (np.inf, 21.0)],  # women
}

# --- Exhaustion ---------------------------------------------------------
# Fried used two CES-D items ("everything I did was an effort" / "could not get
# going") and counted a response of 2 (a moderate amount of the time, 3-4 days)
# or 3 (most of the time) as meeting the criterion. NHANES fields the PHQ-9
# instead; DPQ040 ("felt tired or had little energy") is the closest analogue and
# shares the 0-3 frequency scale, where 2 = "more than half the days" and
# 3 = "nearly every day". So the >=2 threshold transfers directly.
EXHAUSTION_MIN = 2

# --- Weight loss --------------------------------------------------------
# Fried 2001 Appendix: K = (weight previous year - current weight) / weight
# previous year; criterion met if K >= 0.05 AND the subject does not report
# trying to lose weight. WHQ070 == 1 is "tried to lose weight in past year".
WEIGHT_LOSS_PCT = 5.0

# --- Low physical activity ----------------------------------------------
# This is the one criterion where Fried's RULE could not be reproduced, and the
# substitution is deliberate rather than a convenience.
#
# Fried defined low activity as the lowest sex-specific QUINTILE of kcal/week,
# which in CHS landed at <383 (men) / <270 (women) kcal/wk on the short
# Minnesota Leisure Time Activity questionnaire. Neither part transfers:
#   - The kcal values are instrument-specific; NHANES PAQ yields MET-minutes.
#   - The quintile RULE is not computable here. NHANES only counts activity in
#     bouts of >=10 continuous minutes at moderate-or-greater intensity, so it
#     records a hard zero for 38.9% of this 60+ sample. Minnesota LTA counted
#     light gardening, chores and bowling and so gave those people nonzero kcal.
#     With a 38.9% point mass at zero, no threshold can select the bottom 20%:
#     the 20th percentile IS zero for both sexes.
#
# So the criterion is defined on its own terms -- no reported moderate/vigorous
# activity, including walking or cycling for transport -- and labelled as such.
# Measured prevalence is 38.9% against Fried's 22%, i.e. this criterion is
# deliberately looser than the original and fires more often than the other
# three. It still tracks age monotonically (31% at 60-64 -> 56% at 80+), so it
# carries real severity signal, but any comparison to published Fried prevalence
# must account for it. Alternatives considered and rejected as worse: WHO 2020
# <600 MET-min/wk (54.8%), and reusing Fried's kcal numbers as if they were
# MET-minutes (47.8%, and unit-incoherent).
ACTIVITY_MET_MAX = 0.0
ACTIVITY_QUANTILE = 0.20  # reported for transparency only; not used as the rule

SEX_LABEL = {1: "men", 2: "women"}


def grip_cutoff(sex: float, bmi: float) -> float:
    """Fried's sex- and BMI-stratified grip threshold, in kg."""
    if pd.isna(sex) or pd.isna(bmi):
        return np.nan
    for bmi_upper, kg in GRIP_CUTOFFS[int(sex)]:
        if bmi <= bmi_upper:
            return kg
    return np.nan


def score(df: pd.DataFrame) -> pd.DataFrame:
    """Add the four criterion flags and the 0-4 total. Modifies a copy."""
    df = df.copy()

    # 1. Unintentional weight loss
    df["crit_weight_loss"] = (
        (df["pct_weight_change_1yr"] >= WEIGHT_LOSS_PCT) & (df["WHQ070"] != 1)
    ).astype(float).where(df["pct_weight_change_1yr"].notna() & df["WHQ070"].notna())

    # 2. Exhaustion
    df["crit_exhaustion"] = (df["DPQ040"] >= EXHAUSTION_MIN).astype(float).where(
        df["DPQ040"].notna()
    )

    # 3. Weakness (grip)
    cut = df.apply(lambda r: grip_cutoff(r["RIAGENDR"], r["BMXBMI"]), axis=1)
    df["grip_cutoff_kg"] = cut
    df["crit_weakness"] = (df["grip_max_kg"] <= cut).astype(float).where(
        df["grip_max_kg"].notna() & cut.notna()
    )

    # 4. Low physical activity -- no reported MVPA (see ACTIVITY_MET_MAX note)
    df["crit_low_activity"] = (df["met_min_week"] <= ACTIVITY_MET_MAX).astype(
        float
    ).where(df["met_min_week"].notna())
    df.attrs["activity_quintiles"] = {
        sex: df.loc[df["RIAGENDR"] == sex, "met_min_week"].quantile(ACTIVITY_QUANTILE)
        for sex in (1, 2)
    }

    # 5. Slowness proxy -- self-reported difficulty walking a quarter mile.
    # Fried's slowness criterion was defined as the slowest 20% on a timed walk.
    # NHANES 2011-2014 has no timed walk, but PFQ061B >= 2 ("some difficulty" or
    # worse) fires at 19.8% here, which lands almost exactly on the prevalence
    # Fried's cutoffs were constructed to produce. Code 5 ("does not do this
    # activity") is already NaN from the build step, not folded in either way.
    df["crit_slowness"] = (df["PFQ061B"] >= 2).astype(float).where(
        df["PFQ061B"].notna()
    )

    # Two 4-of-5 scores, for two different purposes. They are NOT interchangeable
    # and must never be compared to each other:
    #   frailty_score      weakness via grip -- the exam-measured version
    #   frailty_score_app  slowness via walking difficulty -- the version the
    #                      app's weekly check-in can actually reproduce, since
    #                      no consumer device gives us a dynamometer reading
    base = ["crit_weight_loss", "crit_exhaustion", "crit_low_activity"]
    for col, fourth in [("frailty_score", "crit_weakness"),
                        ("frailty_score_app", "crit_slowness")]:
        crits = base + [fourth]
        df[col] = df[crits].sum(axis=1).where(df[crits].notna().all(axis=1))

    df["n_criteria_present"] = df[base + ["crit_weakness"]].notna().sum(axis=1)
    return df


def print_cutoffs(df: pd.DataFrame) -> None:
    """Print every cutoff actually applied, for review."""
    crits = ["crit_weight_loss", "crit_exhaustion", "crit_weakness", "crit_low_activity"]
    thr = df.attrs["activity_quintiles"]

    print("=" * 78)
    print("CUTOFFS APPLIED  (Fried et al. 2001, J Gerontol 56A:M146-M156, Appendix)")
    print("=" * 78)

    print("\n1. UNINTENTIONAL WEIGHT LOSS   [source cutoff, unmodified]")
    print(f"   met if  pct_weight_change_1yr >= {WEIGHT_LOSS_PCT}%  AND  WHQ070 != 1 (not trying to lose)")
    print("   Fried: 'If K >= 0.05 and the subject does not report that he/she was trying to lose weight'")

    print("\n2. EXHAUSTION                  [instrument adapted: CES-D -> PHQ-9]")
    print(f"   met if  DPQ040 >= {EXHAUSTION_MIN}  (2 = more than half the days, 3 = nearly every day)")
    print("   Fried: CES-D response 2 ('3-4 days') or 3 ('most of the time') on either of two items")

    print("\n3. WEAKNESS / GRIP STRENGTH    [source cutoffs, unmodified; hand adapted]")
    print("   met if  grip_max_kg <= cutoff below")
    for sex, rows in GRIP_CUTOFFS.items():
        lo = 0.0
        parts = []
        for upper, kg in rows:
            band = f"BMI <={upper:g}" if lo == 0 else (
                f"BMI >{lo:g}" if np.isinf(upper) else f"BMI {lo:g}.1-{upper:g}")
            parts.append(f"{band}: <={kg:g} kg")
            lo = upper
        print(f"     {SEX_LABEL[sex]:<6} " + " | ".join(parts))
    print("   NOTE: Fried specifies dominant-hand max; NHANES does not record handedness,")
    print("         so max across both hands is used (NOT MGDCGSZ, which sums both hands).")

    print("\n4. LOW PHYSICAL ACTIVITY       *** RULE SUBSTITUTED -- READ THIS ***")
    print(f"   met if  met_min_week <= {ACTIVITY_MET_MAX:g}  (no moderate/vigorous activity at all,")
    print("           counting work, recreation, and walking/cycling for transport)")
    print("   Fried's rule was the lowest sex-specific QUINTILE of kcal/wk (<383 men, <270 women,")
    print("   Minnesota LTA). It is not computable here: NHANES only counts >=10-min bouts at")
    print("   moderate+ intensity and so records a hard zero for 38.9% of this sample, meaning")
    print(f"   the 20th percentile is itself zero for both sexes "
          f"(men {thr[1]:,.0f}, women {thr[2]:,.0f} MET-min/wk).")
    print("   Consequence: this criterion fires at 38.9% vs Fried's 22% -- looser than the")
    print("   original by construction. It does still rise monotonically with age (31% at")
    print("   60-64 -> 56% at 80+). Rejected alternatives: WHO 2020 <600 MET-min/wk (54.8%),")
    print("   Fried's kcal numbers reused as MET-minutes (47.8%, unit-incoherent).")

    print("\n5. SLOWNESS (GAIT SPEED)       [NOT SCORABLE]")
    print("   NHANES 2011-2014 has no timed walk. Score is therefore 0-4, not 0-5.")

    print("\n" + "=" * 78)
    print("RESULTING PREVALENCE   (vs. Fried 2001 Table 3, CHS, age 65+)")
    print("=" * 78)
    ref = {"crit_exhaustion": 17, "crit_weight_loss": 6,
           "crit_low_activity": 22, "crit_weakness": 20}
    print(f"{'criterion':<22} {'n scored':>9} {'% met':>8} {'CHS %':>8}")
    for c in crits:
        s = df[c].dropna()
        print(f"{c:<22} {len(s):>9,} {100*s.mean():>7.1f}% {ref[c]:>7}%")

    scored = df["frailty_score"].dropna()
    print(f"\ncomplete on all 4 criteria: {len(scored):,} of {len(df):,}")
    print("\nfrailty score distribution:")
    dist = scored.value_counts(normalize=True).sort_index()
    for k, v in dist.items():
        print(f"   {int(k)}: {100*v:>5.1f}%  ({int(scored.eq(k).sum()):,})")
    print(f"\nmean score {scored.mean():.3f}, sd {scored.std():.3f}")


if __name__ == "__main__":
    from pathlib import Path

    src = Path(__file__).resolve().parent.parent / "data" / "frailty_nhanes_60plus.csv"
    scored = score(pd.read_csv(src))
    print_cutoffs(scored)
    out = src.with_name("frailty_scored_60plus.csv")
    scored.to_csv(out, index=False)
    print(f"\nwrote {out}")
