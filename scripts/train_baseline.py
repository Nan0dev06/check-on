"""Train the expected-frailty baseline model on NHANES 2011-2014, age 60+.

WHAT THIS MODEL OUTPUTS -- be precise about this, it is easy to overclaim:
Given an age (and sex), it predicts the EXPECTED / TYPICAL adapted frailty score
for someone with that profile, estimated from a population cross-section. It is
a POPULATION BASELINE TO COMPARE AGAINST, not a per-person trajectory forecast.

NHANES observes each participant once, so nothing here tracks an individual over
time. The app supplies the per-person trajectory later, from repeated check-ins;
this model only says what score is typical for that age/sex, so the app can ask
whether a given person is above, at, or below that band. Any claim that this
model "predicts decline" for an individual would be wrong.

Target is the adapted 0-4 Fried score from score_frailty.py (gait speed is not
measurable in these NHANES cycles, so it is 4 criteria, not the clinical 5).

DOCUMENTED LIMITATION: NHANES topcodes age at 80 -- every participant 80 and
older is coded exactly 80. The upper end of the age curve is therefore
compressed and the model cannot distinguish an 80-year-old from a 92-year-old.
We are not engineering around this; it is stated plainly as a caveat.
"""

import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split

from score_frailty import score

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "frailty_nhanes_60plus.csv"
MODEL_OUT = ROOT / "models" / "frailty_baseline.joblib"
SEED = 42


def features(df: pd.DataFrame) -> pd.DataFrame:
    """age, sex, and their interaction -- deliberately tiny and inspectable."""
    return pd.DataFrame({
        "age": df["RIDAGEYR"],
        "female": (df["RIAGENDR"] == 2).astype(int),
        "age_x_female": df["RIDAGEYR"] * (df["RIAGENDR"] == 2),
    })


def main() -> None:
    df = score(pd.read_csv(SRC))
    df = df[df["frailty_score"].notna()].reset_index(drop=True)

    X, y = features(df), df["frailty_score"]
    # WTMEC2YR is a 2-year exam weight; halve it when pooling two cycles so the
    # pooled weights represent one population, not two stacked ones.
    w = df["WTMEC2YR"] / 2

    Xtr, Xte, ytr, yte, wtr, wte = train_test_split(
        X, y, w, test_size=0.25, random_state=SEED
    )
    print(f"train {len(Xtr):,}  test {len(Xte):,}   (complete-case, all 4 criteria scored)")

    models = {
        "baseline (predict mean)": DummyRegressor(strategy="mean"),
        "linear: age + sex": LinearRegression(),
        "linear: age + sex + age*sex": LinearRegression(),
        "random forest (depth 4)": RandomForestRegressor(
            n_estimators=300, max_depth=4, min_samples_leaf=50, random_state=SEED
        ),
    }
    cols = {
        "baseline (predict mean)": ["age", "female"],
        "linear: age + sex": ["age", "female"],
        "linear: age + sex + age*sex": ["age", "female", "age_x_female"],
        "random forest (depth 4)": ["age", "female"],
    }

    print(f"\n{'model':<30} {'MAE':>7} {'RMSE':>7} {'R2':>8}")
    fitted = {}
    for name, mdl in models.items():
        c = cols[name]
        mdl.fit(Xtr[c], ytr, sample_weight=wtr)
        p = mdl.predict(Xte[c])
        print(f"{name:<30} {mean_absolute_error(yte, p):>7.3f} "
              f"{np.sqrt(mean_squared_error(yte, p)):>7.3f} {r2_score(yte, p):>8.4f}")
        fitted[name] = (mdl, c)

    # --- interpretability: what did the linear model actually learn? --------
    lin, lc = fitted["linear: age + sex + age*sex"]
    print("\nlinear coefficients (survey-weighted, frailty points):")
    for n, coef in zip(lc, lin.coef_):
        print(f"   {n:<14} {coef:+.5f}")
    print(f"   {'intercept':<14} {lin.intercept_:+.5f}")
    print(f"   -> men:   +{lin.coef_[0]:.4f} points/yr  ({10*lin.coef_[0]:.3f} per decade)")
    print(f"   -> women: +{lin.coef_[0]+lin.coef_[2]:.4f} points/yr "
          f"({10*(lin.coef_[0]+lin.coef_[2]):.3f} per decade)")

    # --- sanity check 1: is predicted frailty monotone in age? --------------
    # Observed column is survey-weighted to match the weighted predictions;
    # the unweighted mean runs higher because NHANES oversamples older and
    # lower-income adults, who are frailer than the US population average.
    print("\nSANITY: predicted score by age, must increase monotonically")
    print(f"{'age':>5} {'men':>7} {'women':>7} {'obs(wtd)':>9} {'obs(unw)':>9} {'n':>6}")
    ok = True
    prev = {0: -np.inf, 1: -np.inf}
    for age in np.arange(60, 81, 2):
        row = []
        for fem in (0, 1):
            f = pd.DataFrame({"age": [age], "female": [fem], "age_x_female": [age * fem]})
            pred = lin.predict(f[lc])[0]
            row.append(pred)
            if pred < prev[fem] - 1e-9:
                ok = False
            prev[fem] = pred
        b = df[(df.RIDAGEYR >= age - 1) & (df.RIDAGEYR <= age + 1)]
        ow = np.average(b.frailty_score, weights=b.WTMEC2YR) if len(b) else np.nan
        print(f"{age:>5} {row[0]:>7.3f} {row[1]:>7.3f} {ow:>9.3f} "
              f"{b.frailty_score.mean():>9.3f} {len(b):>6,}")
    print(f"   monotonically increasing in age: {'YES' if ok else 'NO'}")

    # --- sanity check 2: calibration of the baseline band -------------------
    # This is the metric that matters for the app's actual use: the model is
    # only ever asked for the TYPICAL score at an age, so what must be accurate
    # is the group mean, not any individual's score.
    print("\nSANITY: calibration -- predicted vs observed MEAN by age band (weighted)")
    bands = pd.cut(df.RIDAGEYR, [59, 64, 69, 74, 79, 80],
                   labels=["60-64", "65-69", "70-74", "75-79", "80 (topcoded)"])
    print(f"{'band':<16} {'n':>6} {'obs mean':>9} {'pred mean':>10} {'diff':>7}")
    for name, g in df.assign(b=bands).groupby("b", observed=True):
        obs = np.average(g.frailty_score, weights=g.WTMEC2YR)
        pred = np.average(lin.predict(features(g)[lc]), weights=g.WTMEC2YR)
        print(f"{str(name):<16} {len(g):>6,} {obs:>9.3f} {pred:>10.3f} {pred-obs:>+7.3f}")

    resid = y - lin.predict(X[lc])
    print(f"\nresidual SD = {resid.std():.3f} frailty points "
          f"(target SD = {y.std():.3f})")
    print("   -> individual scores scatter widely around the age curve. That is the")
    print("      expected shape: age and sex set the BAND, not a person's score.")

    # --- example predictions ------------------------------------------------
    print("\nEXAMPLE PREDICTIONS (expected score for that profile, 0-4 scale)")
    print(f"{'profile':<22} {'predicted':>10}   interpretation")
    for age, fem in [(62, 0), (62, 1), (70, 0), (70, 1), (78, 0), (78, 1), (80, 1)]:
        f = pd.DataFrame({"age": [age], "female": [fem], "age_x_female": [age * fem]})
        p = lin.predict(f[lc])[0]
        lab = f"{age}yo {'woman' if fem else 'man'}"
        note = ("typical: ~1 criterion" if p >= 0.75 else "typical: <1 criterion")
        print(f"{lab:<22} {p:>10.3f}   {note}")
    print("\n  '80yo' means 80 OR OLDER -- NHANES topcodes age at 80.")

    MODEL_OUT.parent.mkdir(exist_ok=True)
    save(lin, lc, "adapted_fried_0_4_grip", MODEL_OUT)

    # --- app-comparable baseline -------------------------------------------
    # The grip-based score above cannot be reproduced by the app: the weekly
    # check-in has no dynamometer. This second baseline swaps the weakness
    # criterion for slowness (self-reported difficulty walking a quarter mile),
    # which the check-in CAN collect, so a person's in-app score and the
    # population expectation are finally on the same instrument.
    print("\n" + "=" * 62)
    print("APP-COMPARABLE BASELINE (slowness instead of grip weakness)")
    print("=" * 62)
    app = score(pd.read_csv(SRC))
    app = app[app["frailty_score_app"].notna()].reset_index(drop=True)
    Xa, ya, wa = features(app), app["frailty_score_app"], app["WTMEC2YR"] / 2
    lina = LinearRegression().fit(Xa[lc], ya, sample_weight=wa)
    print(f"n = {len(app):,}   mean score {ya.mean():.3f}   sd {ya.std():.3f}")
    print(f"   men   +{10*lina.coef_[0]:.3f} pts/decade")
    print(f"   women +{10*(lina.coef_[0]+lina.coef_[2]):.3f} pts/decade")
    ra = ya - lina.predict(Xa[lc])
    print(f"   residual sd {ra.std():.3f};  85th pct {ra.quantile(.85):+.3f}, "
          f"90th {ra.quantile(.90):+.3f}")
    print(f"   P(residual >= 1.0) = {100*(ra >= 1.0).mean():.1f}%")
    save(lina, lc, "adapted_fried_0_4_app",
         MODEL_OUT.with_name("frailty_baseline_app.joblib"))


def save(model, cols, target, path) -> None:
    try:
        import joblib
        joblib.dump({"model": model, "features": cols, "target": target,
                     "trained_on": "NHANES 2011-2014, age 60+, survey-weighted"},
                    path)
        print(f"saved {path}")
    except ImportError:
        print("joblib not installed; model not persisted")


if __name__ == "__main__":
    main()
