"""From NA_inputs/US Pools - Generation and Capacity_anonymized.xlsx (Capacity MW by
Pool-Region x Fuel Group x year 2025-2035) build, for the 4 currently-mapped technologies:

  ResidualCapacity        : 2025 capacity as the base; 5% retires each year
                            (no retirement data yet) -> base * 0.95^(year-2025), 2025-2040.
  TotalAnnualMinCapacity   } 2026-2040, bracketing the file's per-year capacity with a
  TotalAnnualMaxCapacity   } "widening" margin:
      2026-2028:  min = val*0.98 , max = val*1.02     (+/-2%)
      2029-2035:  linearly widen to  min = val*0.90 , max = val*1.30  at 2035
      2036-2040:  hold the 2035 value, margins stay at -10% / +30%

Fuel Group -> model technology (only these 4 for now; Coal/Nuclear ignored):
  Natural Gas -> P_Gas_CCGT
  Solar       -> P_PV_Utility_Avg      (note: the model tech is P_PV_*, not P_Solar_*)
  Wind        -> P_Wind_Onshore_Avg
  Hydro       -> P_Hydro_Reservoir

Capacity MW -> model GW (/1000). Negative anonymized capacities are clamped to 0
(invalid; no-op on real data). Canada is not in this file -> no bounds written for it.

Idempotent: existing NA rows for the 4 techs are removed from each CSV before appending.
Run:  python NA_inputs/add_capacity_bounds.py            # dry-run (prints a sample)
      python NA_inputs/add_capacity_bounds.py --apply
"""
import os, sys
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_REPO = os.path.normpath(os.path.join(HERE, ".."))
SRC = os.path.join(HERE, "US Pools - Generation and Capacity_anonymized.xlsx")
PARAM = lambda n: os.path.join(DATA_REPO, "Data", "Parameters", n, n + ".csv")
apply = "--apply" in sys.argv

TECH = {"Natural Gas": "P_Gas_CCGT", "Solar": "P_PV_Utility_Avg",
        "Wind": "P_Wind_Onshore_Avg", "Hydro": "P_Hydro_Reservoir",
        "Nuclear": "P_Nuclear"}
MODEL_TECHS = set(TECH.values())
RETIRE_DEFAULT = 0.95  # 5% of residual retires each year (gas/solar/wind/hydro)
# Per-tech retire rate override. Nuclear stays online (no retirement assumed) —
# the existing fleet is kept flat at the 2025 value through 2040.
RETIRE_PER_TECH = {"P_Nuclear": 1.0}
YEARS = list(range(2025, 2041))
DATE, WHO = "2026-05-28", "Konstantin Loffler <kl@wip.tu-berlin.de>"

# Annual numerical floor (2035-2040 reported for Nuclear/USA in GW). Used as
# Par_GroupTotalAnnualMinCapacity (TechnologySubset=Nuclear, RegionSubset=USA).
NUCLEAR_USA_GROUP_MIN = {
    2035: 116.0,   2036: 118.3,   2037: 121.43,
    2038: 123.932, 2039: 123.932, 2040: 129.832,
}


def margins(year, tech=None):
    """(min_factor, max_factor) widening from +/-2% (<=2028) to -10%/+30% (>=2035).
    P_Nuclear keeps min_factor pinned to 1.0 (no downward widening) — the
    target/floor below uses GroupTotalAnnualMinCapacity instead. Max-side
    widening is preserved so the model can still build more nuclear per region
    if it wants to hit the national target."""
    y = min(year, 2035)
    if y <= 2028:
        mn, mx = 0.98, 1.02
    else:
        frac = (y - 2028) / (2035 - 2028)
        mn = 0.98 + (0.90 - 0.98) * frac
        mx = 1.02 + (1.30 - 1.02) * frac
    if tech == "P_Nuclear":
        mn = 1.0
    return mn, mx


def main():
    df = pd.read_excel(SRC)
    cap = df[df["Measure"] == "Capacity MW"].copy()

    def gw(region, fuel, year):
        sel = cap[(cap["Pool-Regions"] == region) & (cap["Fuel Group"] == fuel)]
        if sel.empty or year not in sel.columns:
            return 0.0
        return max(0.0, float(sel.iloc[0][year])) / 1000.0   # MW->GW, clamp >=0

    regions = sorted(cap["Pool-Regions"].unique())
    res_rows, min_rows, max_rows = [], [], []
    for region in regions:
        for fuel, tech in TECH.items():
            base = gw(region, fuel, 2025)
            retire = RETIRE_PER_TECH.get(tech, RETIRE_DEFAULT)
            for y in YEARS:
                res_rows.append((region, tech, y, round(base * retire ** (y - 2025), 6)))
            for y in range(2026, 2041):
                if tech == "P_Nuclear":
                    val = base   # hold 2025 capacity flat across the horizon
                else:
                    val = gw(region, fuel, min(y, 2035))  # hold 2035 value for 2036-2040
                mn, mx = margins(y, tech)
                min_rows.append((region, tech, y, round(val * mn, 6)))
                max_rows.append((region, tech, y, round(val * mx, 6)))

    def write(param, rows, src):
        path = PARAM(param)
        d = pd.read_csv(path)
        d = d.rename(columns={"Unnamed: 4": ""})
        drop = d["Region"].isin(regions) & d["Technology"].isin(MODEL_TECHS)
        nd = int(drop.sum())
        d = d[~drop]
        add = pd.DataFrame([{"Region": r, "Technology": t, "Year": y, "Value": v, "": "",
                             "Unit": "GW", "Source": src, "Updated at": DATE, "Updated by": WHO}
                            for (r, t, y, v) in rows])
        add = add[d.columns]
        out = pd.concat([d, add], ignore_index=True)
        if apply:
            out.to_csv(path, index=False)
        return nd, len(rows)

    def write_subset_row(param, tech, subset):
        """Append a (Technology, Subset, 1, ...) row to a Par_Tag*ToSubsets CSV
        if not already present. Idempotent."""
        path = os.path.join(DATA_REPO, "Data", "Parameters", "00_Sets&Tags", param + ".csv")
        d = pd.read_csv(path)
        already = ((d["Technology"] == tech) & (d["Subset"] == subset)).any()
        if already:
            return 0, 0
        d = d.rename(columns={"Unnamed: 3": ""})
        new = pd.DataFrame([{"Technology": tech, "Subset": subset, "Value": 1, "": "",
                             "Unit": "Binary", "Source": "not relevant",
                             "Updated at": DATE, "Updated by": WHO}])
        new = new[d.columns]
        out = pd.concat([d, new], ignore_index=True)
        if apply:
            out.to_csv(path, index=False)
        return 0, 1

    def write_group_min(year_to_gw, tech_subset, region_subset, src):
        """Replace any (TechnologySubset, RegionSubset) rows in
        Par_GroupTotalAnnualMinCapacity with the supplied (year -> GW) entries."""
        path = PARAM("Par_GroupTotalAnnualMinCapacity")
        d = pd.read_csv(path)
        d = d.rename(columns={"Unnamed: 4": ""})
        drop = (d["TechnologySubset"] == tech_subset) & (d["RegionSubset"] == region_subset)
        nd = int(drop.sum())
        d = d[~drop]
        new = pd.DataFrame([{"TechnologySubset": tech_subset, "RegionSubset": region_subset,
                             "Year": y, "Value": v, "": "", "Unit": "GW", "Source": src,
                             "Updated at": DATE, "Updated by": WHO}
                            for y, v in sorted(year_to_gw.items())])
        new = new[d.columns]
        out = pd.concat([d, new], ignore_index=True)
        if apply:
            out.to_csv(path, index=False)
        return nd, len(new)

    r1 = write("Par_ResidualCapacity", res_rows, "US Pools gen/cap 2025 base, 5%/yr retirement (Nuclear held flat)")
    r2 = write("Par_TotalAnnualMinCapacity", min_rows, "US Pools gen/cap, widening band (min) — Nuclear pinned to actual value")
    r3 = write("Par_TotalAnnualMaxCapacity", max_rows, "US Pools gen/cap, widening band (max)")

    # --- Nuclear/USA Group floor + subset wiring -----------------------------
    # Add P_Nuclear to the "Nuclear" technology subset and write per-year
    # GroupTotalAnnualMinCapacity floor for Nuclear x USA.
    r4 = write_subset_row("Par_TagTechnologyToSubsets", "P_Nuclear", "Nuclear")
    r5 = write_group_min(NUCLEAR_USA_GROUP_MIN, "Nuclear", "USA",
                          "US nuclear capacity target trajectory")

    # sample print
    ex_r, ex_t = "PJM", "P_Gas_CCGT"
    print(f"Sample {ex_r} {ex_t} (GW):  Year  Residual    Min      Max")
    res = {y: v for (r, t, y, v) in res_rows if r == ex_r and t == ex_t}
    mn = {y: v for (r, t, y, v) in min_rows if r == ex_r and t == ex_t}
    mx = {y: v for (r, t, y, v) in max_rows if r == ex_r and t == ex_t}
    for y in YEARS:
        print(f"          {y}  {res.get(y,0):>9.3f}  {mn.get(y,float('nan')):>7.3f}  {mx.get(y,float('nan')):>7.3f}")
    print(f"\n{'APPLIED' if apply else 'DRY-RUN'}: Residual -{r1[0]}/+{r1[1]} ; "
          f"MinCap -{r2[0]}/+{r2[1]} ; MaxCap -{r3[0]}/+{r3[1]} ; "
          f"NuclearSubset -{r4[0]}/+{r4[1]} ; "
          f"NuclearGroupMin -{r5[0]}/+{r5[1]} "
          f"(regions={len(regions)}, techs={len(TECH)})")
    if not apply:
        print("(use --apply to write)")


if __name__ == "__main__":
    main()
