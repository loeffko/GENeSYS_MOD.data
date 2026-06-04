# -*- coding: utf-8 -*-
"""Capacity bounds + RES potentials (merged).

Writes the following NA-side parameters in one pass so guardrail vs. potential
do not overlap:

  Par_ResidualCapacity         : 2025 base * retire^(y-2025), 2025-2040. Default
                                 retire = 0.95/yr (5% per year). P_Nuclear is
                                 held flat (1.0/yr) — fleet assumed to stay on.

  Par_TotalAnnualMinCapacity   : guardrail funnel 2026-2040
      2026-2028:  min = val*0.98 (±2%)
      2029-2035:  linearly widen to min = val*0.90 at 2035
      2036-2040:  hold the 2035 funnel min (no contraction post-2035)
      Nuclear is pinned to 1.0 (no downward widening).

  Par_TotalAnnualMaxCapacity   : guardrail funnel 2026-2035 widening up to 1.30
      For PV_Utility_Avg / Wind_Onshore_Avg (guardrail reps that have a
      restool potential): 2036-2040 linearly interp from the 2035 funnel
      max -> the per-region restool potential at 2040, every year filled.
      For Nuclear/Gas/Hydro (no restool potential): hold 2035 funnel max
      through 2040.
      Non-rep variants (PV_Utility_Inf/Opt/Tracking, Wind_Onshore_Inf/Opt,
      A_Rooftop_*) and Canada: every year 2025-2040 = restool potential
      (flat, no growth, since the value is the physical ceiling).

  Par_TagTechnologyToSubsets   : P_Nuclear -> Nuclear subset (idempotent)
  Par_GroupTotalAnnualMinCapacity : Nuclear x USA target trajectory 2035-2040

Sources:
  - NA_inputs/US Pools - Generation and Capacity_anonymized.xlsx (Pool-Region x
    Fuel Group x year 2025-2035, Capacity MW). Anonymized; values clamped >=0.
  - NA_restool/northamerica_potentials_combined.csv (PV/Wind/Rooftop GW)
  - NA_restool/canada_potentials_combined.csv

Idempotent: existing NA rows for the managed techs are removed from each CSV
before append. Canada bounds come only from the restool (Canada is not in the
US Pools file).

Run:  python NA_inputs/add_capacity_bounds.py            # dry-run (sample print)
      python NA_inputs/add_capacity_bounds.py --apply
"""
import os, sys
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_REPO = os.path.normpath(os.path.join(HERE, ".."))
SRC = os.path.join(HERE, "US Pools - Generation and Capacity_anonymized.xlsx")
POT_NA = os.path.join(DATA_REPO, "NA_restool", "northamerica_potentials_combined.csv")
POT_CA = os.path.join(DATA_REPO, "NA_restool", "canada_potentials_combined.csv")
PARAM = lambda n: os.path.join(DATA_REPO, "Data", "Parameters", n, n + ".csv")
apply = "--apply" in sys.argv

# Guardrail fuel-group -> representative model tech (US Pools dataset)
TECH = {"Natural Gas": "P_Gas_CCGT", "Solar": "P_PV_Utility_Avg",
        "Wind": "P_Wind_Onshore_Avg", "Hydro": "P_Hydro_Reservoir",
        "Nuclear": "P_Nuclear"}
MODEL_TECHS_GUARDRAIL = set(TECH.values())

# Restool potential column -> all model tech variants in that family.
# Each variant gets a share of the per-region potential (placeholder split until
# the resource-graded breakdown file lands): 40% Avg / 30% Opt / 30% Inf for
# Utility PV and Onshore Wind. Rooftop maps to a single power tech
# (P_PV_Rooftop_Commercial) — the area-based "A_Rooftop_*" entries are not
# touched here, since the rooftop *generation* capacity belongs on the P_ tech.
RESTOOL_MAP = {
    "PV Capacity [GW]": {
        "rep": "P_PV_Utility_Avg",
        "variants": {
            "P_PV_Utility_Avg": 0.40,
            "P_PV_Utility_Opt": 0.30,
            "P_PV_Utility_Inf": 0.30,
        },
    },
    "Wind Capacity [GW]": {
        "rep": "P_Wind_Onshore_Avg",
        "variants": {
            "P_Wind_Onshore_Avg": 0.40,
            "P_Wind_Onshore_Opt": 0.30,
            "P_Wind_Onshore_Inf": 0.30,
        },
    },
    "Rooftop Capacity [GW]": {
        "rep": None,
        "variants": {"P_PV_Rooftop_Commercial": 1.00},
    },
}
GUARDRAIL_REP_TO_RESTOOL_COL = {
    info["rep"]: col for col, info in RESTOOL_MAP.items() if info["rep"]
}
# Share that each variant takes of its parent restool column.
TECH_SHARE = {v: s for info in RESTOOL_MAP.values() for v, s in info["variants"].items()}
ALL_RESTOOL_TECHS = sorted(TECH_SHARE.keys())

# Full set of techs this script manages (guardrail + restool variants)
ALL_MANAGED_TECHS = MODEL_TECHS_GUARDRAIL | set(ALL_RESTOOL_TECHS)

RETIRE_DEFAULT = 0.95
RETIRE_PER_TECH = {"P_Nuclear": 1.0}
YEARS = list(range(2025, 2041))
DATE, WHO = "2026-06-04", "Konstantin Loffler <kl@wip.tu-berlin.de>"

# Nuclear/USA target floor (GroupTotalAnnualMinCapacity).
NUCLEAR_USA_GROUP_MIN = {
    2035: 116.0,   2036: 118.3,   2037: 121.43,
    2038: 123.932, 2039: 123.932, 2040: 129.832,
}


def margins(year, tech=None):
    """(min_factor, max_factor) widening from +/-2% (<=2028) to -10%/+30% (>=2035)."""
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


def read_restool_potentials():
    """Return {region: {col: GW}} from both NA + Canada potential CSVs."""
    out = {}
    for path in (POT_NA, POT_CA):
        df = pd.read_csv(path)
        for _, row in df.iterrows():
            region = str(row["region"])
            out[region] = {col: float(row[col]) for col in row.index
                           if col != "region" and not pd.isna(row[col])}
    return out


def main():
    df = pd.read_excel(SRC)
    cap = df[df["Measure"] == "Capacity MW"].copy()
    pot = read_restool_potentials()

    def gw(region, fuel, year):
        sel = cap[(cap["Pool-Regions"] == region) & (cap["Fuel Group"] == fuel)]
        if sel.empty or year not in sel.columns:
            return 0.0
        return max(0.0, float(sel.iloc[0][year])) / 1000.0   # MW->GW, clamp >=0

    pool_regions = sorted(cap["Pool-Regions"].unique())
    extra_regions = [r for r in pot.keys() if r not in pool_regions]  # Canada etc.

    res_rows, min_rows, max_rows = [], [], []

    # 1) Guardrail funnel (5 fuel groups x US pool regions)
    for region in pool_regions:
        # 2040 interpolation target per guardrail rep = (region potential) * (rep share)
        pot_for_rep = {}
        for tech, col in GUARDRAIL_REP_TO_RESTOOL_COL.items():
            raw = pot.get(region, {}).get(col)
            pot_for_rep[tech] = raw * TECH_SHARE.get(tech, 0.0) if raw is not None else None
        for fuel, tech in TECH.items():
            base = gw(region, fuel, 2025)
            retire = RETIRE_PER_TECH.get(tech, RETIRE_DEFAULT)
            for y in YEARS:
                res_rows.append((region, tech, y, round(base * retire ** (y - 2025), 6)))

            # 2035 funnel max (anchor for post-2035 interpolation)
            val_2035 = base if tech == "P_Nuclear" else gw(region, fuel, 2035)
            _, mx_at_2035 = margins(2035, tech)
            max_2035 = val_2035 * mx_at_2035
            mn_at_2035 = margins(2035, tech)[0]
            min_2035 = val_2035 * mn_at_2035

            target_2040 = pot_for_rep.get(tech)   # None if no restool potential

            for y in range(2026, 2041):
                if y <= 2035:
                    val = base if tech == "P_Nuclear" else gw(region, fuel, y)
                    mn, mx = margins(y, tech)
                    min_rows.append((region, tech, y, round(val * mn, 6)))
                    max_rows.append((region, tech, y, round(val * mx, 6)))
                else:
                    # min: hold 2035 funnel min (no contraction post-2035)
                    min_rows.append((region, tech, y, round(min_2035, 6)))
                    # max: interp 2035 funnel -> 2040 restool potential if available
                    if target_2040 is not None and target_2040 > 0:
                        frac = (y - 2035) / 5.0
                        interp = max_2035 + (target_2040 - max_2035) * frac
                        max_rows.append((region, tech, y, round(interp, 6)))
                    else:
                        max_rows.append((region, tech, y, round(max_2035, 6)))

        # 2) Non-rep restool variants: every year 2025-2040 = potential * share (flat)
        for col, info in RESTOOL_MAP.items():
            pot_val = pot.get(region, {}).get(col, 0.0)
            for variant, share in info["variants"].items():
                if variant == info["rep"]:
                    continue
                for y in YEARS:
                    max_rows.append((region, variant, y, round(pot_val * share, 6)))

    # 3) Extra regions (Canada): only restool potentials (no Pool source data)
    for region in extra_regions:
        for col, info in RESTOOL_MAP.items():
            pot_val = pot.get(region, {}).get(col, 0.0)
            for variant, share in info["variants"].items():
                for y in YEARS:
                    max_rows.append((region, variant, y, round(pot_val * share, 6)))

    all_regions = pool_regions + extra_regions

    def write(param, rows, src):
        path = PARAM(param)
        d = pd.read_csv(path)
        d = d.rename(columns={"Unnamed: 4": ""})
        drop = d["Region"].isin(all_regions) & d["Technology"].isin(ALL_MANAGED_TECHS)
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

    r1 = write("Par_ResidualCapacity", res_rows,
               "US Pools gen/cap 2025 base, 5%/yr retirement (Nuclear held flat)")
    r2 = write("Par_TotalAnnualMinCapacity", min_rows,
               "US Pools gen/cap, widening band (min) — Nuclear pinned, post-2035 held at 2035 funnel min")
    r3 = write("Par_TotalAnnualMaxCapacity", max_rows,
               "Guardrail (2026-2035) + interp to NA_restool potential (2036-2040); "
               "non-rep variants & Canada use restool potential flat across years")

    r4 = write_subset_row("Par_TagTechnologyToSubsets", "P_Nuclear", "Nuclear")
    r5 = write_group_min(NUCLEAR_USA_GROUP_MIN, "Nuclear", "USA",
                         "US nuclear capacity target trajectory")

    # Sample print: PJM P_Gas_CCGT (no restool ceiling — held flat post-2035)
    #               PJM P_PV_Utility_Avg (interpolates to PV potential at 2040)
    for ex_r, ex_t in (("PJM", "P_Gas_CCGT"), ("PJM", "P_PV_Utility_Avg")):
        print(f"\nSample {ex_r} {ex_t} (GW):  Year  Residual    Min      Max")
        res = {y: v for (r, t, y, v) in res_rows if r == ex_r and t == ex_t}
        mn = {y: v for (r, t, y, v) in min_rows if r == ex_r and t == ex_t}
        mx = {y: v for (r, t, y, v) in max_rows if r == ex_r and t == ex_t}
        for y in YEARS:
            print(f"          {y}  {res.get(y,0):>9.3f}  {mn.get(y, float('nan')):>7.3f}  "
                  f"{mx.get(y, float('nan')):>7.3f}")

    print(f"\n{'APPLIED' if apply else 'DRY-RUN'}: Residual -{r1[0]}/+{r1[1]} ; "
          f"MinCap -{r2[0]}/+{r2[1]} ; MaxCap -{r3[0]}/+{r3[1]} ; "
          f"NuclearSubset -{r4[0]}/+{r4[1]} ; "
          f"NuclearGroupMin -{r5[0]}/+{r5[1]} "
          f"(pool_regions={len(pool_regions)}, extra={len(extra_regions)}, "
          f"managed_techs={len(ALL_MANAGED_TECHS)})")
    if not apply:
        print("\n(use --apply to write)")


if __name__ == "__main__":
    main()
