# -*- coding: utf-8 -*-
"""Integrate NA_restool POTENTIALS into Par_TotalAnnualMaxCapacity.

Replaces the 2035+ rows of `Par_TotalAnnualMaxCapacity` for each NA region ×
renewable tech with the restool potential. 2018-2030 rows are preserved (gradual
ramp). An existing `Year=All` row is split into explicit KEEP_YRS (preserved
value) + FUTURE_YRS (new potential). The per-region potential is applied as the
upper deployment bound for each variant of PV / Wind separately.

Run independently of the timeseries updater (`add_na_restool_timeseries.py`)
or together via `add_na_restool_full.py`.
"""
import csv
import os

HERE = os.path.dirname(os.path.abspath(__file__))
RESTOOL = os.path.join(HERE, "NA_restool")
MAXCAP_CSV = os.path.join(HERE, "Data", "Parameters",
                          "Par_TotalAnnualMaxCapacity",
                          "Par_TotalAnnualMaxCapacity.csv")

NA_US      = ["California", "ERCOT", "MISO", "NewEngland", "NewYork",
              "PJM", "SERC", "SPP", "WECC"]
NA_ALL     = NA_US + ["Canada"]
FUTURE_YRS = [2035, 2040, 2045, 2050]
KEEP_YRS   = [2018, 2025, 2030]   # preserved unchanged

# Potentials CSV column -> list of model techs that should share that potential
POTENTIAL_MAP = {
    "PV Capacity [GW]":      ["P_PV_Utility_Avg", "P_PV_Utility_Inf",
                              "P_PV_Utility_Opt", "P_PV_Utility_Tracking"],
    "Wind Capacity [GW]":    ["P_Wind_Onshore_Avg", "P_Wind_Onshore_Inf",
                              "P_Wind_Onshore_Opt"],
    "Rooftop Capacity [GW]": ["A_Rooftop_Commercial", "A_Rooftop_Residential"],
}

STAMP = "2026-06-02"
AUTHOR = "Konstantin Loffler <kl@wip.tu-berlin.de>"
SOURCE = "GENeSYS-MOD.tools NA_restool"


def read_potentials():
    out = {}
    for fn in ("northamerica_potentials_combined.csv", "canada_potentials_combined.csv"):
        path = os.path.join(RESTOOL, fn)
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                r = row["region"]
                out[r] = {k: float(v) for k, v in row.items() if k != "region"}
    return out


def main():
    print("=== TotalAnnualMaxCapacity (NA_restool, 2035+) ===")
    pots = read_potentials()
    with open(MAXCAP_CSV, "r", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    header = rows[0]
    targets = set()
    for col, techs in POTENTIAL_MAP.items():
        for t in techs:
            for r in NA_ALL:
                targets.add((r, t))
    kept = [header]
    dropped = 0
    for row in rows[1:]:
        if len(row) < 4:
            kept.append(row); continue
        rgn, tech, year, val = row[0], row[1], row[2], row[3]
        if (rgn, tech) in targets and (year == "All"
                                       or year in {str(y) for y in FUTURE_YRS}
                                       or year in {str(y) for y in KEEP_YRS}):
            if year == "All":
                try:
                    old_val = float(val)
                except ValueError:
                    old_val = None
                if old_val is not None:
                    for y in KEEP_YRS:
                        kept.append([rgn, tech, str(y), str(old_val), "", "GW",
                                     "preserved from prior 'All' entry",
                                     STAMP, AUTHOR])
                dropped += 1
                continue
            if year in {str(y) for y in FUTURE_YRS}:
                dropped += 1
                continue
            kept.append(row)
        else:
            kept.append(row)
    added = 0
    for col, techs in POTENTIAL_MAP.items():
        for r in NA_ALL:
            if r not in pots or col not in pots[r]:
                continue
            cap = round(pots[r][col], 3)
            for t in techs:
                for y in FUTURE_YRS:
                    kept.append([r, t, str(y), str(cap), "", "GW", SOURCE, STAMP, AUTHOR])
                    added += 1
    with open(MAXCAP_CSV, "w", encoding="utf-8", newline="") as f:
        csv.writer(f).writerows(kept)
    print(f"  dropped {dropped} existing rows, added {added} new rows (regions×techs×{len(FUTURE_YRS)} years)")


if __name__ == "__main__":
    main()
    print("\nDone.")
