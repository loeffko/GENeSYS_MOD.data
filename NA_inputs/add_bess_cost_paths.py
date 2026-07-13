"""Write the Li-Ion cost paths for the bess_cost_low* scenario subfolders.

Rule (matches the original hand-built 0.5 files): both battery cost components
run linearly from the BASE 2025 value down to (BASE 2040 value x MULT) at 2040;
pre-2025 milestone rows keep the base values. Applied to
  Par_CapitalCost         D_Battery_Li-Ion  (power component, MEUR/GW)
  Par_CapitalCostStorage  S_Battery_Li-Ion  (energy component, MEUR/PJ)
for the three subfolders (the _6h/_8h variants differ only via their
Par_StorageE2PRatio files, which this script does not touch).

Run:  python NA_inputs/add_bess_cost_paths.py --mult 0.4 --apply
"""
import os, sys
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_REPO = os.path.normpath(os.path.join(HERE, ".."))
PARAMS = os.path.join(DATA_REPO, "Data", "Parameters")

MULT = float(sys.argv[sys.argv.index("--mult") + 1]) if "--mult" in sys.argv else 0.4
apply = "--apply" in sys.argv
SUBDIRS = ["NorthAmerica_bess_optimistic"]   # optimistic = low cost + 7h duration (2026-07-13 restructure)
TARGETS = [("Par_CapitalCost", "Technology", "D_Battery_Li-Ion"),
           ("Par_CapitalCostStorage", "Storage", "S_Battery_Li-Ion")]
SRC = f"BESS cost sensitivity: 2040 base cost x{MULT}, linear from 2025"
DATE, WHO = "2026-07-09", "Konstantin Loffler <kl@wip.tu-berlin.de>"

for param, techcol, tech in TARGETS:
    base = pd.read_csv(os.path.join(PARAMS, param, f"{param}.csv"))
    base = base.rename(columns={c: "" for c in base.columns if str(c).startswith("Unnamed")})
    d = base[base[techcol] == tech].copy()
    yr = pd.to_numeric(d.Year)
    v2025 = float(d.loc[yr == 2025, "Value"].iloc[0])
    v2040_target = float(d.loc[yr == 2040, "Value"].iloc[0]) * MULT
    slope = (v2025 - v2040_target) / 15.0
    # 2026-2040: linear from the 2025 base value to base2040 x MULT;
    # beyond 2040 (outside the horizon): base value x MULT (matches the 0.5 files)
    inh = (yr > 2025) & (yr <= 2040)
    d.loc[inh, "Value"] = yr[inh].map(lambda y: round(v2025 - slope * (y - 2025), 5))
    d.loc[yr > 2040, "Value"] = (d.loc[yr > 2040, "Value"].astype(float) * MULT).round(5)
    d["Source"] = SRC
    d["Updated at"] = DATE
    d["Updated by"] = WHO
    for sub in SUBDIRS:
        outdir = os.path.join(PARAMS, param, sub)
        os.makedirs(outdir, exist_ok=True)
        if apply:
            d.to_csv(os.path.join(outdir, f"{param}.csv"), index=False, lineterminator="\n")
    print(f"{param}/{tech}: 2025 {v2025:.0f} -> 2040 {v2040_target:.0f} "
          f"({len(d)} rows x {len(SUBDIRS)} subfolders){' APPLIED' if apply else ' DRY-RUN'}")
