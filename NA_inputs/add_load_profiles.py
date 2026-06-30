"""Replace the North-American region columns in Data/Timeseries/TS_LOAD/TS_LOAD.csv
with the 8760-hour load profiles from NA_inputs/8760 Demand - US Pools_anonymized.xlsx.

The file holds 9 of the 10 NA regions (Canada missing) -> Canada is duplicated from
NewYork for now. These profiles become the Power_General demand profile: GENeSYS-MOD's
timeseries_reduction assigns the (re-normalised) LOAD shape to every demand fuel, and
Power_General carries the bulk NA power demand.

Only the 10 NA columns are rewritten; all other (EU) columns and the source/header lines
are left byte-for-byte unchanged. Idempotent (re-run overwrites the same columns).
Run after the demand converter, before script_northamerica.py:
    python NA_inputs/add_load_profiles.py
"""
import os
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_REPO = os.path.normpath(os.path.join(HERE, ".."))
SRC_XLSX = os.path.join(HERE, "8760 Demand - US Pools.xlsx")
TS_LOAD = os.path.join(DATA_REPO, "Data", "Timeseries", "TS_LOAD", "TS_LOAD.csv")

FILE_REGIONS = ["California", "WECC", "SPP", "MISO", "ERCOT", "SERC", "PJM",
                "NewYork", "NewEngland"]   # 9 regions present in the source file


def main():
    new = pd.read_excel(SRC_XLSX)
    assert len(new) == 8760, f"expected 8760 hourly rows, got {len(new)}"
    missing = [r for r in FILE_REGIONS if r not in new.columns]
    assert not missing, f"source file missing region columns: {missing}"

    # preserve the source annotation line (line 1); header is on line 2
    with open(TS_LOAD, "r", encoding="utf-8", newline="") as f:
        src_line = f.readline()
    df = pd.read_csv(TS_LOAD, skiprows=1, dtype=str, keep_default_na=False)
    assert len(df) == 8760, f"TS_LOAD.csv has {len(df)} data rows, expected 8760"

    # overwrite the NA columns (positional row alignment: both chronological from Jan 1 Hr 1)
    for r in FILE_REGIONS:
        if r not in df.columns:
            raise KeyError(f"{r} column not in TS_LOAD.csv (run expand_northamerica once first)")
        df[r] = ["{:.9g}".format(float(v)) for v in new[r].to_numpy()]
    df["Canada"] = df["NewYork"].values          # Canada missing in source -> copy NewYork

    with open(TS_LOAD, "w", encoding="utf-8", newline="") as f:
        f.write(src_line if src_line.endswith("\n") else src_line + "\n")
        df.to_csv(f, index=False, lineterminator="\n")

    print(f"Updated 10 NA load columns (9 from file + Canada=NewYork) in {os.path.relpath(TS_LOAD, DATA_REPO)}")
    print("Per-region mean (should be ~similar shape, re-normalised downstream):")
    for r in FILE_REGIONS + ["Canada"]:
        col = df[r].astype(float)
        print(f"  {r:12s} mean={col.mean():.4f}  min={col.min():.4f}  max={col.max():.4f}")


if __name__ == "__main__":
    main()
