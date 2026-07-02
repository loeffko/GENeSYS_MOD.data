"""Convert the dispatch-model configuration CSVs (Data/Dispatch/*.csv) into a
single DispatchData_<label>.xlsx (one sheet per CSV, sheet name = file stem) in
Output/output_excel. The dispatch model (GENeSYS_MOD.jl genesysmod_dispatch_
fullyear, `dispatch_data_file` argument) reads this workbook from InputData.

The files are region-agnostic long-format tables (Region='World' rows act as
defaults; regions absent from a table fall back to neutral behaviour in the
model), so the same Data/Dispatch source serves any model region - pass a label
to name the output for your region set.

Usage:  python convert_dispatch_data.py [label] [region1 region2 ...]
        default label NorthAmerica, no region filter (all rows pass through).
e.g.    python convert_dispatch_data.py Europe DE FR PL World
"""
import os, sys, glob
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_REPO = os.path.normpath(os.path.join(HERE, ".."))
SRC_DIR = os.path.join(DATA_REPO, "Data", "Dispatch")
OUT_DIR = os.path.join(DATA_REPO, "Output", "output_excel")

label = sys.argv[1] if len(sys.argv) > 1 else "NorthAmerica"
regions = sys.argv[2:] or None          # optional region filter (keep 'World'!)

out = os.path.join(OUT_DIR, f"DispatchData_{label}.xlsx")
files = sorted(glob.glob(os.path.join(SRC_DIR, "Par_*.csv")))
if not files:
    sys.exit(f"no Par_*.csv found in {SRC_DIR}")

os.makedirs(OUT_DIR, exist_ok=True)
with pd.ExcelWriter(out, engine="openpyxl") as xw:
    for f in files:
        name = os.path.splitext(os.path.basename(f))[0]
        d = pd.read_csv(f)
        d.columns = ["" if str(c).startswith("Unnamed") else c for c in d.columns]
        if regions and "Region" in d.columns:
            d = d[d["Region"].isin(set(regions) | {"World"})]
        d.to_excel(xw, sheet_name=name[:31], index=False)
        print(f"  {name:32} {len(d):>4} rows")
print(f"wrote {out}")
