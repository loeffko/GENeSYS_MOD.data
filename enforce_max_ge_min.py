# -*- coding: utf-8 -*-
"""Sanity sweep: ensure TotalAnnualMaxCapacity >= TotalAnnualMinCapacity
(and same for GroupTotalAnnualMax/MinCapacity).

When the input scenarios are produced independently (e.g. Low / High offshore
scenarios) the resulting Min value can occasionally exceed the corresponding
Max for a given (Region, Technology, Year), which makes the model infeasible
by construction.

This script scans both files and, where Min > Max, raises Max to Min so the
constraint is just tight (not violated). Existing rows are rewritten in-place.

Run:  python enforce_max_ge_min.py            # dry-run (prints conflicts)
      python enforce_max_ge_min.py --apply
"""
import os
import sys
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PARAM = lambda n: os.path.join(HERE, "Data", "Parameters", n, n + ".csv")
apply = "--apply" in sys.argv

STAMP = "2026-06-04"
WHO = "Konstantin Loffler <kl@wip.tu-berlin.de>"


def _normalize(d):
    """Rename anonymous 'Unnamed: 4' column to '' to match other writers."""
    return d.rename(columns={"Unnamed: 4": ""})


def fix_pair(min_path, max_path, key_cols, label):
    """Read both CSVs, find rows where min > max for the same (key_cols), and
    update max to min. Returns (n_conflicts, conflicts_list)."""
    d_min = _normalize(pd.read_csv(min_path))
    d_max = _normalize(pd.read_csv(max_path))

    # Build {(key1, key2, ...): max_value} from d_max (last entry wins for dup keys)
    max_lookup = {tuple(str(row[c]) for c in key_cols): (idx, float(row["Value"]))
                  for idx, row in d_max.iterrows() if pd.notna(row.get("Value"))}

    conflicts = []
    for _, mrow in d_min.iterrows():
        if pd.isna(mrow.get("Value")):
            continue
        key = tuple(str(mrow[c]) for c in key_cols)
        mn_val = float(mrow["Value"])
        if key not in max_lookup:
            # No max entry => effectively unlimited (999999 sentinel). Skip.
            continue
        idx, mx_val = max_lookup[key]
        if mn_val > mx_val:
            conflicts.append((key, mn_val, mx_val))
            d_max.at[idx, "Value"] = mn_val
            d_max.at[idx, "Source"] = "MaxCap raised to MinCap by enforce_max_ge_min.py"
            d_max.at[idx, "Updated at"] = STAMP
            d_max.at[idx, "Updated by"] = WHO
            max_lookup[key] = (idx, mn_val)

    print(f"[{label}] conflicts: {len(conflicts)}")
    for key, mn, mx in conflicts[:10]:
        print(f"   {key}: min={mn:.4f} > max={mx:.4f}  -> max set to {mn:.4f}")
    if len(conflicts) > 10:
        print(f"   ... and {len(conflicts) - 10} more")

    if apply and conflicts:
        d_max.to_csv(max_path, index=False)
        print(f"[{label}] WROTE {max_path}")
    return len(conflicts)


def main():
    print("Scanning Par_TotalAnnualMin/MaxCapacity...")
    n1 = fix_pair(
        PARAM("Par_TotalAnnualMinCapacity"),
        PARAM("Par_TotalAnnualMaxCapacity"),
        key_cols=["Region", "Technology", "Year"],
        label="TotalAnnualCapacity",
    )
    print("\nScanning Par_GroupTotalAnnualMin/MaxCapacity...")
    n2 = fix_pair(
        PARAM("Par_GroupTotalAnnualMinCapacity"),
        PARAM("Par_GroupTotalAnnualMaxCapacity"),
        key_cols=["TechnologySubset", "RegionSubset", "Year"],
        label="GroupTotalAnnualCapacity",
    )
    print(f"\n{'APPLIED' if apply else 'DRY-RUN'}: total conflicts fixed = {n1 + n2}")
    if not apply:
        print("(use --apply to write)")


if __name__ == "__main__":
    main()
