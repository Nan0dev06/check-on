"""Validate the FAERS PRR pipeline on a known-positive and known-negative pair.

POSITIVE CONTROL -- amlodipine + peripheral oedema.
Chosen because it is the textbook prescribing cascade this whole project is
about: amlodipine (and dihydropyridine calcium channel blockers generally)
causes dose-dependent ankle/peripheral oedema by preferential arteriolar
dilation, the oedema gets read as fluid overload, and a loop diuretic gets
added to treat a side effect. Independently verifiable outside FAERS: it is
listed as a common adverse reaction on the FDA's own Norvasc label, and the
cascade is a standard worked example in the deprescribing literature.

NEGATIVE CONTROL -- amlodipine + alopecia.
Chosen deliberately over a rare pair. Alopecia has no pharmacological basis as
an amlodipine effect, but it is common enough overall (194,177 reports) that
the pair still clears the case-count and chi-squared bars. That makes it the
useful negative: it demonstrates the criteria are conjunctive, and that PRR is
the one doing the discriminating -- not just small numbers failing a>=3.
"""

from faers_prr import MIN_CASES, MIN_CHI2, MIN_PRR, compute_prr


def report(result) -> None:
    c = result.counts
    print("=" * 78)
    print(f"{result.drug.upper()}  +  {result.symptom.upper()}")
    print("=" * 78)

    print(f"\nMedDRA terms queried ({len(result.meddra_terms)}):")
    print(f"   {', '.join(result.meddra_terms)}")
    print(f"drug matched via: patient.drug.{result.drug_field}")

    print("\nQUERIES CONSTRUCTED:")
    for label, q in c.queries.items():
        print(f"   {label}")
        print(f"      {q}")

    print("\n2x2 TABLE (reports):")
    print(f"   {'':<22}{'symptom':>14}{'other':>16}{'total':>16}")
    print(f"   {'this drug':<22}{c.a:>14,}{c.b:>16,}{c.a + c.b:>16,}")
    print(f"   {'all other drugs':<22}{c.c:>14,}{c.d:>16,}{c.c + c.d:>16,}")
    print(f"   {'total':<22}{c.a + c.c:>14,}{c.b + c.d:>16,}{c.n_total:>16,}")

    exposed = c.a / (c.a + c.b)
    background = c.c / (c.c + c.d)
    print(f"\n   reported in {exposed:.4%} of this drug's reports")
    print(f"   vs          {background:.4%} of all other drugs' reports")

    print(f"\nPRR   = {result.prr:.3f}   (95% CI {result.ci_low:.3f} - {result.ci_high:.3f})")
    print(f"chi2  = {result.chi2:,.1f}   (Yates-corrected)")
    print(f"cases = {c.a:,}")

    print("\nEVANS CRITERIA (all three required):")
    for label, ok in [
        (f"cases >= {MIN_CASES}", c.a >= MIN_CASES),
        (f"PRR   >= {MIN_PRR}", result.prr >= MIN_PRR),
        (f"chi2  >= {MIN_CHI2}", result.chi2 >= MIN_CHI2),
    ]:
        print(f"   [{'PASS' if ok else 'FAIL'}]  {label}")
    verdict = "SIGNAL" if result.is_signal else "NO SIGNAL"
    print(f"\n   ==> {verdict}")
    if not result.is_signal:
        print(f"       failed: {'; '.join(result.failed_criteria())}")
    print()


if __name__ == "__main__":
    print("\n### POSITIVE CONTROL " + "#" * 57 + "\n")
    pos = compute_prr("amlodipine", "swollen", terms=["OEDEMA PERIPHERAL"])
    report(pos)

    print("\n### NEGATIVE CONTROL " + "#" * 57 + "\n")
    neg = compute_prr("amlodipine", "hair loss", terms=["ALOPECIA"])
    report(neg)

    print("\n### REAL ICON MAPPING, positive drug " + "#" * 41 + "\n")
    icon = compute_prr("amlodipine", "dizzy")
    report(icon)

    ok = pos.is_signal and not neg.is_signal
    print("=" * 78)
    print(f"VALIDATION {'PASSED' if ok else 'FAILED'}: "
          f"positive control {'signals' if pos.is_signal else 'does not signal'}, "
          f"negative control {'signals' if neg.is_signal else 'does not signal'}")
    print("=" * 78)
