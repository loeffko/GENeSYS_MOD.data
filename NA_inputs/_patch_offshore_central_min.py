# One-off local patch: NY/NE offshore MIN -> Central case (see
# add_offshore_wind_bounds.py CENTRAL_MIN_REGIONS). This machine only holds the
# ANONYMIZED scenario file, so ONLY the two min-row sets are touched (values
# clamped to the existing real-data max rows to keep min <= max); everything
# else keeps the real-file bounds. The next real-data offshore rebuild on the
# data machine supersedes this patch.
import os
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_REPO = os.path.normpath(os.path.join(HERE, ".."))
FEL = os.path.join(HERE, "260421_FEL_US_Offshore_Wind_Scenarios_long_anonymized.xlsx")
P = lambda n: os.path.join(DATA_REPO, "Data", "Parameters", n, n + ".csv")
REP = "P_Wind_Offshore_Shallow"
REGIONS = {"NYISO": "NewYork", "ISO-NE": "NewEngland"}
YEARS = list(range(2025, 2041))

fel = pd.read_excel(FEL)
cen = fel[(fel.Scenario == "Central Case") & fel.Technology.isin(REGIONS)]
cum = {}
for lab, grp in cen.groupby("Technology"):
    s = grp.set_index("Year").Value.reindex(range(2025, 2041)).fillna(0).cumsum()
    cum[REGIONS[lab]] = s.round(3).to_dict()

mx = pd.read_csv(P("Par_TotalAnnualMaxCapacity"))
maxval = {(r.Region, int(r.Year)): float(r.Value) for r in
          mx[(mx.Technology == REP) & mx.Region.isin(REGIONS.values())].itertuples()}

mn = pd.read_csv(P("Par_TotalAnnualMinCapacity"))
mn = mn.rename(columns={c: "" for c in mn.columns if str(c).startswith("Unnamed")})
n = 0
for i, row in mn.iterrows():
    if row.Technology == REP and row.Region in cum and int(row.Year) in YEARS and int(row.Year) > 2025:
        want = cum[row.Region][int(row.Year)]
        cap = maxval.get((row.Region, int(row.Year)), want)
        mn.at[i, "Value"] = round(min(want, cap), 3)
        mn.at[i, "Source"] = "SLA Offshore Wind Scenarios (CENTRAL case min - NY/NE mandates; anonymized file, clamped to max)"
        mn.at[i, "Updated at"] = "2026-07-13"
        n += 1
mn.to_csv(P("Par_TotalAnnualMinCapacity"), index=False, lineterminator="\n")
print(f"patched {n} NY/NE offshore min rows to Central (clamped)")
for r in ("NewYork", "NewEngland"):
    print(r, {y: round(min(cum[r][y], maxval.get((r, y), 9e9)), 2) for y in (2030, 2035, 2040)})
