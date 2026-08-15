"""Build the analysis extract for the frailty trajectory model: NHANES 2011-2014, age 60+.

Pulls the variables behind the four Fried frailty components the project needs
(unintentional weight loss, exhaustion, low physical activity, weakness/walking
difficulty), converts NHANES refused/don't-know sentinel codes to NaN, and
writes one row per participant.

No cutoffs or frailty scoring here -- that belongs to the model step.
"""

import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "nhanes_raw"
OUT = ROOT / "data" / "frailty_nhanes_60plus.csv"

CYCLES = {"G": "2011-2012", "H": "2013-2014"}

KEEP = {
    "DEMO": ["SEQN", "RIAGENDR", "RIDAGEYR", "RIDRETH3", "DMDEDUC2",
             "WTMEC2YR", "SDMVPSU", "SDMVSTRA"],
    "WHQ": ["SEQN", "WHD020", "WHD050", "WHQ040", "WHQ070"],
    "DPQ": ["SEQN", "DPQ040"],
    "PAQ": ["SEQN", "PAQ605", "PAQ610", "PAD615", "PAQ620", "PAQ625", "PAD630",
            "PAQ635", "PAQ640", "PAD645",
            "PAQ650", "PAQ655", "PAD660", "PAQ665", "PAQ670", "PAD675", "PAD680"],
    "MGX": ["SEQN", "MGDCGSZ", "MGXH1T1", "MGXH2T1", "MGXH1T2", "MGXH2T2",
            "MGXH1T3", "MGXH2T3"],
    "BMX": ["SEQN", "BMXWT", "BMXHT", "BMXBMI"],
    "PFQ": ["SEQN", "PFQ061B"],
}

# NHANES codes meaning "refused" / "don't know", by variable.
SENTINELS = {
    "WHD020": [7777, 9999], "WHD050": [7777, 9999],
    "WHQ040": [7, 9], "WHQ070": [7, 9],
    "DPQ040": [7, 9],
    "PAQ605": [7, 9], "PAQ620": [7, 9], "PAQ635": [7, 9],
    "PAQ650": [7, 9], "PAQ665": [7, 9],
    "PAQ610": [77, 99], "PAQ625": [77, 99], "PAQ640": [77, 99],
    "PAQ655": [77, 99], "PAQ670": [77, 99],
    "PAD615": [7777, 9999], "PAD630": [7777, 9999], "PAD645": [7777, 9999],
    "PAD660": [7777, 9999], "PAD675": [7777, 9999], "PAD680": [7777, 9999],
    # PFQ061B code 5 is "does not do this activity", which is semantically
    # ambiguous (too frail to walk that far vs. simply never does) -- NaN rather
    # than guess-encoding it as either extreme. PFQ061B is supplementary only
    # and is not used for frailty scoring.
    "PFQ061B": [5, 7, 9],
    "DMDEDUC2": [7, 9],
}

# Self-reported weight recall and self-reported activity minutes both carry
# implausible tails in NHANES (e.g. reported weight nearly doubling in a year,
# or 12 h/day of vigorous activity every day). Winsorizing these at the 1st/99th
# percentile is standard practice for self-reported NHANES variables, not an
# arbitrary cut.
WINSORIZE = ["pct_weight_change_1yr", "met_min_week"]

LABELS = {
    "SEQN": "NHANES participant id",
    "cycle": "survey cycle",
    "RIAGENDR": "sex (1=male, 2=female)",
    "RIDAGEYR": "age in years (80 = topcoded 80+)",
    "RIDRETH3": "race/ethnicity",
    "DMDEDUC2": "education, adults 20+",
    "WTMEC2YR": "MEC exam sample weight (2-yr)",
    "SDMVPSU": "survey design PSU",
    "SDMVSTRA": "survey design stratum",
    "WHD020": "[loss] self-reported weight now (lb)",
    "WHD050": "[loss] self-reported weight 1 year ago (lb)",
    "WHQ040": "[loss] would like to weigh (1=more, 2=less, 3=same)",
    "WHQ070": "[loss] tried to lose weight in past year (1=yes, 2=no)",
    "DPQ040": "[exhaustion] felt tired / little energy, past 2wk (0=not at all, 1=several days, 2=>half the days, 3=nearly every day)",
    "PAQ605": "[activity] vigorous work activity (1=yes, 2=no)",
    "PAQ610": "[activity] vigorous work, days/week",
    "PAD615": "[activity] vigorous work, min/day",
    "PAQ620": "[activity] moderate work activity (1=yes, 2=no)",
    "PAQ625": "[activity] moderate work, days/week",
    "PAD630": "[activity] moderate work, min/day",
    "PAQ635": "[activity] walks or bicycles for transport (1=yes, 2=no)",
    "PAQ640": "[activity] transport walk/bike, days/week",
    "PAD645": "[activity] transport walk/bike, min/day",
    "PAQ650": "[activity] vigorous recreation (1=yes, 2=no)",
    "PAQ655": "[activity] vigorous recreation, days/week",
    "PAD660": "[activity] vigorous recreation, min/day",
    "PAQ665": "[activity] moderate recreation (1=yes, 2=no)",
    "PAQ670": "[activity] moderate recreation, days/week",
    "PAD675": "[activity] moderate recreation, min/day",
    "PAD680": "[activity] sedentary minutes/day",
    "MGDCGSZ": "[weakness] combined grip strength, kg (sum of best per hand)",
    "PFQ061B": "[walking] difficulty walking a quarter mile (1=none, 2=some, 3=much, 4=unable, 5=does not do)",
    "BMXWT": "measured weight (kg)",
    "BMXHT": "measured height (cm)",
    "BMXBMI": "measured BMI",
    "pct_weight_change_1yr": "derived: (wt 1yr ago - wt now) / wt 1yr ago * 100, positive = lost weight",
    "met_min_week": "derived: MET-minutes/week from the 4 PAQ domains (vig=8, mod=4)",
    "grip_max_kg": "derived: max single-trial grip across both hands (kg)",
}

# domain -> (MET value, days var, minutes var, gate var). MET values follow the
# GPAQ convention NHANES documents: 8.0 vigorous, 4.0 moderate, 4.0 active
# transport. Walking/cycling for transport is included because Fried's Minnesota
# Leisure Time questionnaire counts walking explicitly; leaving it out drops
# exactly the low-intensity activity older adults actually do.
MET = {
    "vig_work": (8.0, "PAQ610", "PAD615", "PAQ605"),
    "mod_work": (4.0, "PAQ625", "PAD630", "PAQ620"),
    "transport": (4.0, "PAQ640", "PAD645", "PAQ635"),
    "vig_rec": (8.0, "PAQ655", "PAD660", "PAQ650"),
    "mod_rec": (4.0, "PAQ670", "PAD675", "PAQ665"),
}

GRIP_TRIALS = ["MGXH1T1", "MGXH2T1", "MGXH1T2", "MGXH2T2", "MGXH1T3", "MGXH2T3"]


def load_cycle(suffix: str) -> pd.DataFrame:
    """Merge one NHANES cycle's files on SEQN, keeping only wanted columns."""
    merged = None
    for stem, cols in KEEP.items():
        df = pd.read_sas(RAW / f"{stem}_{suffix}.xpt", format="xport")[cols]
        merged = df if merged is None else merged.merge(df, on="SEQN", how="left")
    merged.insert(1, "cycle", CYCLES[suffix])
    # SAS transport stores some zeros as denormals (e.g. 5.4e-79); snap them to 0
    # so coded answers like DPQ040=0 compare correctly.
    num = merged.select_dtypes("number")
    merged[num.columns] = num.mask(num.abs() < 1e-20, 0.0)
    return merged


def clean(df: pd.DataFrame) -> pd.DataFrame:
    for var, codes in SENTINELS.items():
        df[var] = df[var].where(~df[var].isin(codes))
    return df


def derive(df: pd.DataFrame) -> pd.DataFrame:
    df["pct_weight_change_1yr"] = (df["WHD050"] - df["WHD020"]) / df["WHD050"] * 100

    met = pd.Series(0.0, index=df.index)
    any_answered = pd.Series(False, index=df.index)
    for mets, days, mins, gate in MET.values():
        # gate == 2 ("no") means zero minutes in that domain, not missing
        said_no = df[gate] == 2
        contrib = (df[days] * df[mins] * mets).fillna(0)
        met += contrib.where(~said_no, 0)
        any_answered |= df[gate].notna()
    df["met_min_week"] = met.where(any_answered)

    # NHANES 2011-2014 randomizes which hand is tested first (MGAPHAND /
    # MGATHAND are "hand assigned for practice" / "begin test with this hand")
    # and never records handedness, so Fried's dominant-hand grip cannot be
    # reproduced. Max across both hands is the usual substitute. Note this is
    # NOT MGDCGSZ, which is the *sum* of both hands and roughly 2x too large to
    # compare against Fried's single-hand cutoffs.
    df["grip_max_kg"] = df[GRIP_TRIALS].max(axis=1)

    for col in WINSORIZE:
        lo, hi = df[col].quantile([0.01, 0.99])
        df[col] = df[col].clip(lo, hi)
    return df


def main() -> None:
    df = pd.concat([load_cycle(s) for s in CYCLES], ignore_index=True)
    df = df[df["RIDAGEYR"] >= 60].reset_index(drop=True)
    df = derive(clean(df))
    df = df.drop(columns=GRIP_TRIALS)
    df["SEQN"] = df["SEQN"].astype(int)
    df.to_csv(OUT, index=False)
    print(f"wrote {OUT}  ({len(df):,} participants aged 60+)")
    return df


if __name__ == "__main__":
    main()
