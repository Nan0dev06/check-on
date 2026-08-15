"""Download the NHANES files needed for the frailty trajectory model.

Cycles G (2011-2012) and H (2013-2014) are the only two that carry the muscle
strength (grip) exam, so they are the only ones that can supply all four Fried
frailty components at once.
"""

import urllib.request
from pathlib import Path

RAW = Path(__file__).resolve().parent.parent / "data" / "nhanes_raw"

# component -> NHANES file stem
FILES = {
    "DEMO": "age, sex, exam weights",
    "WHQ": "self-reported weight now / 1 year ago -> weight loss",
    "DPQ": "PHQ-9, incl. tired-or-little-energy -> exhaustion",
    "PAQ": "physical activity questionnaire",
    "MGX": "grip strength (muscle strength exam)",
    "BMX": "measured weight/height/BMI",
    "PFQ": "physical functioning, incl. walking difficulty",
}

CYCLES = {"G": "2011", "H": "2013"}  # suffix -> first year of cycle (URL path)

URL = "https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/{year}/DataFiles/{stem}_{suffix}.xpt"


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    for suffix, year in CYCLES.items():
        for stem in FILES:
            name = f"{stem}_{suffix}.xpt"
            dest = RAW / name
            if dest.exists():
                print(f"  have {name} ({dest.stat().st_size:,} bytes)")
                continue
            url = URL.format(year=year, stem=stem, suffix=suffix)
            print(f"  get  {name} <- {url}")
            urllib.request.urlretrieve(url, dest)
            print(f"       {dest.stat().st_size:,} bytes")
    print(f"\nraw files in {RAW}")


if __name__ == "__main__":
    main()
