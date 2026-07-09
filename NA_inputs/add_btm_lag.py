"""BTM grid-connection lag sensitivity (btm_lag).

Behind-the-meter data-center facilities connect to the grid with a LAG_YEARS
delay: capacity additions (year-over-year deltas of the BTM capacity outlook,
2026 onward; the 2025 stock never connects) appear LAG_YEARS later as
ResidualCapacity (+ the same amount on TotalAnnualMaxCapacity for headroom),
and the matching BTM demand (btm_twh from the FEL demand workbook) joins
Power_DataCenter with the same lag. Connections bypass the turbine-supply
group caps (the units were already built behind the meter).

TotalAnnualMinCapacity is deliberately NOT raised (v5a): a residual can never
retire (TotalCapacity >= ResidualCapacity by construction), so the connected
BTM fleet stays online regardless — and it counts TOWARD the base funnel min,
letting the model build correspondingly less endogenous FTM capacity instead
of stacking the BTM chain on top of an unchanged base fleet.

Tech mapping (per project decision):
  dc_gas       -> 70% P_Gas_OCGT, 30% P_Gas_CCGT
  dc_other     -> 50% P_Gas_Engines, 50% P_SOFC
  dc_fuel_cell -> 100% P_SOFC
  dc_solar     -> 100% P_PV_Utility_Avg
P_SOFC is an exogenous-only fleet: residual = max = connected BTM value,
min = 0 (no endogenous SOFC on top); the other techs ADD to the max/residual
rows the bounds script wrote for this scenario.

Runs AFTER convert_fel_to_demand + add_capacity_bounds in the builder:
  python NA_inputs/add_btm_lag.py --apply --scenario-subdir NorthAmerica_btm_lag
"""
import os, sys
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_REPO = os.path.normpath(os.path.join(HERE, ".."))
PARAMS = os.path.join(DATA_REPO, "Data", "Parameters")
BTM_XLSX = os.path.join(HERE, "BTM_Generation_Mix_Capacity_v06.xlsx")
FEL_XLSX = os.path.join(HERE, "base_fel_v260707_v2.xlsx")

apply = "--apply" in sys.argv
SUBDIR = sys.argv[sys.argv.index("--scenario-subdir") + 1] if "--scenario-subdir" in sys.argv else None
if SUBDIR is None:
    sys.exit("btm_lag is a scenario-only construct: pass --scenario-subdir <name>")

LAG_YEARS = 4
YEARS = list(range(2025, 2041))
BASE_YEAR = 2025
DATE, WHO = "2026-07-08", "Konstantin Loffler <kl@wip.tu-berlin.de>"

REGION_MAP = {  # BTM/FEL geo_code -> model region ('US' national aggregate ignored)
    "US_R_CALIFORNIA": "California", "US_R_ERCOT": "ERCOT", "US_R_ISONE": "NewEngland",
    "US_R_MISO": "MISO", "US_R_NYISO": "NewYork", "US_R_PJM": "PJM",
    "US_R_SERC": "SERC", "US_R_SPP": "SPP", "US_R_WECC": "WECC",
    "US_R_FRCC": "SERC", "CA": "Canada",
}
TECH_MAP = {  # BTM tech -> [(model tech, share)]
    "dc_gas":       [("P_Gas_OCGT", 0.70), ("P_Gas_CCGT", 0.30)],
    "dc_other":     [("P_Gas_Engines", 0.50), ("P_SOFC", 0.50)],
    "dc_fuel_cell": [("P_SOFC", 1.00)],
    "dc_solar":     [("P_PV_Utility_Avg", 1.00)],
}
SRC = f"BTM grid-connection lag {LAG_YEARS}y (BTM_Generation_Mix_Capacity_v06 Calc, data_centers)"


def connected_series(level_by_year):
    """cumulative-additions-since-BASE_YEAR, lagged: connected(y) = level(y-LAG) - level(BASE)."""
    base = level_by_year.get(BASE_YEAR, 0.0)
    out = {}
    for y in YEARS:
        yy = y - LAG_YEARS
        out[y] = max(0.0, level_by_year.get(yy, base if yy < BASE_YEAR else level_by_year.get(max(level_by_year), base)) - base) if yy >= BASE_YEAR else 0.0
    return out


def main():
    # ---- capacity: BTM Calc tab, data_centers, regional rows only ----
    calc = pd.read_excel(BTM_XLSX, "Calc")
    calc = calc[(calc.sector == "data_centers") & calc.geo_code.isin(REGION_MAP)]
    cap = calc.groupby(["geo_code", "tech", "year"]).capacity_gw_installed.sum()
    add_cap = {}   # (region, model_tech, year) -> GW connected
    for (geo, btm_tech), grp in cap.groupby(level=[0, 1]):
        if btm_tech not in TECH_MAP:
            continue
        levels = {int(y): float(v) for (_, _, y), v in grp.items()}
        conn = connected_series(levels)
        r = REGION_MAP[geo]
        for tech, share in TECH_MAP[btm_tech]:
            for y, v in conn.items():
                if v * share > 1e-6:
                    add_cap[(r, tech, y)] = add_cap.get((r, tech, y), 0.0) + v * share

    # ---- demand: FEL _Data_Grid btm_twh, data_centers ----
    dg = pd.read_excel(FEL_XLSX, "_Data_Grid")
    dg = dg[(dg.sector == "data_centers") & dg.geo_code.isin(REGION_MAP)]
    btm = dg.groupby(["geo_code", "year"]).btm_twh.sum()
    add_dem = {}   # (region, year) -> PJ
    for geo, grp in btm.groupby(level=0):
        levels = {int(y): float(v) for (_, y), v in grp.items()}
        conn = connected_series(levels)
        r = REGION_MAP[geo]
        for y, v in conn.items():
            if v > 1e-9:
                add_dem[(r, y)] = add_dem.get((r, y), 0.0) + v * 3.6   # TWh -> PJ

    def scen_csv(param):
        return os.path.join(PARAMS, param, SUBDIR, param + ".csv")

    # ---- capacity params: residual + max only (min stays the base funnel; the
    # connected residual counts toward it, so endogenous FTM builds can shrink) ----
    for param in ("Par_ResidualCapacity", "Par_TotalAnnualMinCapacity", "Par_TotalAnnualMaxCapacity"):
        path = scen_csv(param)
        d = pd.read_csv(path)
        d = d.rename(columns={c: "" for c in d.columns if str(c).startswith("Unnamed")})
        d.loc[d.Technology == "P_SOFC", "Value"] = 0.0   # exogenous-only tech: no open funnel
        if param == "Par_TotalAnnualMinCapacity":
            if apply:
                d.to_csv(path, index=False, lineterminator="\n")
            print(f"{param}: no bumps (min stays base funnel; SOFC min = 0)")
            continue
        idx = {(r.Region, r.Technology, r.Year): i for i, r in enumerate(d.itertuples())}
        new_rows = []
        bumped = 0
        for (r, t, y), v in sorted(add_cap.items()):
            key = (r, t, y)
            if key in idx:
                if t == "P_SOFC":
                    # exogenous fleet: res = max = connected BTM value (min = 0)
                    d.at[idx[key], "Value"] = round(v, 6)
                else:
                    d.at[idx[key], "Value"] = round(float(d.at[idx[key], "Value"]) + v, 6)
                bumped += 1
            else:
                new_rows.append({"Region": r, "Technology": t, "Year": y, "Value": round(v, 6),
                                 "": "", "Unit": "GW", "Source": SRC,
                                 "Updated at": DATE, "Updated by": WHO})
        if new_rows:
            d = pd.concat([d, pd.DataFrame(new_rows)[d.columns]], ignore_index=True)
        if apply:
            d.to_csv(path, index=False, lineterminator="\n")
        print(f"{param}: +{bumped} bumped, +{len(new_rows)} new rows")

    # ---- demand: bump Power_DataCenter in the scenario demand rows ----
    path = scen_csv("Par_SpecifiedAnnualDemand")
    d = pd.read_csv(path)
    d = d.rename(columns={c: "" for c in d.columns if str(c).startswith("Unnamed")})
    bumped = 0
    for i, row in d.iterrows():
        key = (row.Region, int(row.Year))
        if row.Fuel == "Power_DataCenter" and key in add_dem:
            d.at[i, "Value"] = round(float(row.Value) + add_dem[key], 6)
            bumped += 1
    if apply:
        d.to_csv(path, index=False, lineterminator="\n")
    tot40 = sum(v for (r, y), v in add_dem.items() if y == 2040) / 3.6
    cap40 = sum(v for (r, t, y), v in add_cap.items() if y == 2040)
    print(f"Par_SpecifiedAnnualDemand: +{bumped} Power_DataCenter rows bumped")
    print(f"2040 connected: {cap40:.1f} GW capacity, {tot40:.1f} TWh demand")
    print("APPLIED." if apply else "DRY-RUN.")


if __name__ == "__main__":
    main()
