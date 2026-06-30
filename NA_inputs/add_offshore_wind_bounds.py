# -*- coding: utf-8 -*-
"""Offshore wind capacity bounds for North America.

Inputs:
  - NA_inputs/260421_FEL_US_Offshore_Wind_Scenarios_long_anonymized.xlsx
      Annual additions per year per region (CAISO / ISO-NE / NYISO / PJM / Other)
      under Low / Central / High scenarios. Anonymized; values are non-negative.
      Cumulative installed = cumsum of per-year additions.
  - NA_restool/northamerica_potentials_combined.csv  (general Wind Capacity GW)
  - NA_restool/canada_potentials_combined.csv

Writes (idempotent — old rows replaced before append):

  1. For each directly-mentioned region (CAISO/ISO-NE/NYISO/PJM):
        Par_TotalAnnualMinCapacity  : Low-scenario cumulative,  per year, P_Wind_Offshore_Shallow
        Par_TotalAnnualMaxCapacity  : Central cumulative up to 2033, High cumulative
                                      from 2034, per year, P_Wind_Offshore_Shallow
     (Single representative offshore tech — model picks Shallow / Deep / Transitional
      via cost, but the aggregate cap binds Shallow which is the largest pool.)

  2. For not-directly-mentioned US regions (MISO/ERCOT/SPP/SERC/WECC) + Canada:
        Par_TotalAnnualMaxCapacity = Wind Capacity from restool potentials,
        flat across 2025-2040, applied to P_Wind_Offshore_Deep / Shallow / Transitional.

  3. New region subset "Other_Offshore_Regions" = {MISO, ERCOT, SPP, SERC, WECC}
     added to Par_TagRegionToSubsets.

  4. New tech subset "OffshoreWind" = {P_Wind_Offshore_Deep, _Shallow, _Transitional}
     added to Par_TagTechnologyToSubsets.

  5. Par_GroupTotalAnnualMinCapacity / MaxCapacity rows for
        OffshoreWind x Other_Offshore_Regions x year, with the FEL "Other"
        Low cumulative as min and "Other" Central(<=2033)/High(>2033) cumulative as max.

Run:  python NA_inputs/add_offshore_wind_bounds.py            # dry-run
      python NA_inputs/add_offshore_wind_bounds.py --apply
"""
import os
import sys
import openpyxl
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_REPO = os.path.normpath(os.path.join(HERE, ".."))
FEL_PATH = os.path.join(HERE, "260421_FEL_US_Offshore_Wind_Scenarios_long.xlsx")
POT_NA = os.path.join(DATA_REPO, "NA_restool", "northamerica_potentials_combined.csv")
POT_CA = os.path.join(DATA_REPO, "NA_restool", "canada_potentials_combined.csv")
PARAM = lambda n: os.path.join(DATA_REPO, "Data", "Parameters", n, n + ".csv")
TAG_PATH = lambda n: os.path.join(DATA_REPO, "Data", "Parameters", "00_Sets&Tags", n + ".csv")
apply = "--apply" in sys.argv

# FEL region label -> model region (None means handled as Group via "Other_Offshore_Regions")
DIRECT = {"CAISO": "California", "ISO-NE": "NewEngland", "NYISO": "NewYork", "PJM": "PJM"}
US_REGIONS = ["California", "ERCOT", "MISO", "NewEngland", "NewYork",
              "PJM", "SERC", "SPP", "WECC"]
OTHER_OFFSHORE_REGIONS = sorted(set(US_REGIONS) - set(DIRECT.values()))
OFFSHORE_TECHS = ["P_Wind_Offshore_Deep", "P_Wind_Offshore_Shallow",
                  "P_Wind_Offshore_Transitional"]
# Map model tech -> potential column in northamerica_potentials_combined.csv
POT_COL = {
    "P_Wind_Offshore_Shallow":      "Offshore Wind shallow [GW]",
    "P_Wind_Offshore_Transitional": "Offshore Wind transitional [GW]",
    "P_Wind_Offshore_Deep":         "Offshore Wind deep [GW]",
}
REP_TECH = "P_Wind_Offshore_Shallow"     # representative tech for per-region bounds
YEARS = list(range(2025, 2041))

DATE = "2026-06-04"
WHO = "Konstantin Loffler <kl@wip.tu-berlin.de>"


def read_fel():
    """Return {(scenario, region_label): {year: annual_addition_GW}}."""
    wb = openpyxl.load_workbook(FEL_PATH, read_only=True, data_only=True)
    ws = wb["Long_Table"]
    out = {}
    for row in ws.iter_rows(values_only=True):
        if row[0] == "Year" or row[0] is None:
            continue
        y, t, s, _, v = int(row[0]), row[1], row[2], row[3], float(row[4] or 0)
        out.setdefault((s, t), {})[y] = v
    return out


def cumulative(yr_to_val):
    out, run = {}, 0.0
    for y in YEARS:
        run += yr_to_val.get(y, 0.0)
        out[y] = round(run, 6)
    return out


CENTRAL_UNTIL = 2033   # Central case is the upper bound through this year; High after


def offshore_max(central, high):
    """Upper bound = Central cumulative up to and incl. CENTRAL_UNTIL (2033), High
    cumulative from the year after. Forced non-decreasing: a cumulative capacity cap
    must never shrink, and in the anonymized data the 'Other' Central can exceed High
    (which would otherwise make the cap drop and become infeasible). Both args are
    cumulative dicts."""
    out, run = {}, 0.0
    for y in YEARS:
        v = central[y] if y <= CENTRAL_UNTIL else high[y]
        v = max(v, run)
        out[y] = round(v, 6)
        run = v
    return out


def read_offshore_potential():
    """Return {region: {tech: GW}} for the three offshore wind techs.

    Uses the per-type columns in northamerica_potentials_combined.csv
    (Offshore Wind shallow/transitional/deep). The Canada potentials CSV does
    not yet expose offshore breakdowns; falls back to 0 for Canada per type
    until that file is updated."""
    out = {}
    df_na = pd.read_csv(POT_NA)
    for _, r in df_na.iterrows():
        reg = str(r["region"])
        out[reg] = {t: float(r[col]) for t, col in POT_COL.items() if col in r}
    df_ca = pd.read_csv(POT_CA)
    for _, r in df_ca.iterrows():
        reg = str(r["region"])
        out[reg] = {t: float(r[col]) if col in r else 0.0 for t, col in POT_COL.items()}
    return out


# ---------- writers ----------
def _rewrite_cap(param_name, drop_mask_fn, new_rows, src):
    path = PARAM(param_name)
    d = pd.read_csv(path)
    d = d.rename(columns={"Unnamed: 4": ""})
    drop = drop_mask_fn(d)
    nd = int(drop.sum())
    d = d[~drop]
    add = pd.DataFrame([{"Region": r, "Technology": t, "Year": y, "Value": v, "": "",
                         "Unit": "GW", "Source": src, "Updated at": DATE, "Updated by": WHO}
                        for (r, t, y, v) in new_rows])
    add = add[d.columns]
    out = pd.concat([d, add], ignore_index=True)
    if apply:
        out.to_csv(path, index=False)
    return nd, len(new_rows)


def _rewrite_group(param_name, ts, rs, year_to_val, src):
    path = PARAM(param_name)
    d = pd.read_csv(path)
    d = d.rename(columns={"Unnamed: 4": ""})
    drop = (d["TechnologySubset"] == ts) & (d["RegionSubset"] == rs)
    nd = int(drop.sum())
    d = d[~drop]
    add = pd.DataFrame([{"TechnologySubset": ts, "RegionSubset": rs, "Year": y,
                         "Value": v, "": "", "Unit": "GW", "Source": src,
                         "Updated at": DATE, "Updated by": WHO}
                        for y, v in sorted(year_to_val.items())])
    add = add[d.columns]
    out = pd.concat([d, add], ignore_index=True)
    if apply:
        out.to_csv(path, index=False)
    return nd, len(add)


def _add_subset(param_name, key_col, key, subset):
    """Append one (key, subset, 1, ...) row if not already present."""
    path = TAG_PATH(param_name)
    d = pd.read_csv(path)
    if ((d[key_col] == key) & (d["Subset"] == subset)).any():
        return 0, 0
    d = d.rename(columns={"Unnamed: 3": ""})
    new = pd.DataFrame([{key_col: key, "Subset": subset, "Value": 1, "": "",
                         "Unit": "Binary", "Source": "not relevant",
                         "Updated at": DATE, "Updated by": WHO}])
    new = new[d.columns]
    out = pd.concat([d, new], ignore_index=True)
    if apply:
        out.to_csv(path, index=False)
    return 0, 1


# ---------- main ----------
def main():
    fel = read_fel()
    pot = read_offshore_potential()

    # 1) Per-region direct: min = Low cumulative; max = Central cumulative up to and
    #    incl. 2033, then High cumulative from 2034 on (offshore ramps too fast if
    #    High is allowed near-term, so cap at Central and only open the High headroom
    #    later).
    min_rows, max_rows = [], []
    for label, model_region in DIRECT.items():
        low = cumulative(fel.get(("Low Case", label), {}))
        central = cumulative(fel.get(("Central Case", label), {}))
        high = cumulative(fel.get(("High Case", label), {}))
        omax = offshore_max(central, high)
        for y in YEARS:
            min_rows.append((model_region, REP_TECH, y, low[y]))
            max_rows.append((model_region, REP_TECH, y, omax[y]))

    # 2) Not directly mentioned (Other_Offshore_Regions + Canada): use restool
    #    per-type offshore potential flat across years.
    nonmentioned = OTHER_OFFSHORE_REGIONS + ["Canada"]
    pot_rows = []
    for region in nonmentioned:
        caps = pot.get(region, {})
        for tech in OFFSHORE_TECHS:
            cap = round(caps.get(tech, 0.0), 3)
            if cap <= 0:
                continue
            for y in YEARS:
                pot_rows.append((region, tech, y, cap))

    # 3) Drop existing offshore rows for these regions/techs before append
    direct_regions = set(DIRECT.values())
    nonmentioned_set = set(nonmentioned)
    r_min = _rewrite_cap(
        "Par_TotalAnnualMinCapacity",
        lambda d: d["Region"].isin(direct_regions) & d["Technology"].isin({REP_TECH}),
        min_rows,
        "SLA Offshore Wind Scenarios (Low Case, cumulative)",
    )
    r_max_direct = _rewrite_cap(
        "Par_TotalAnnualMaxCapacity",
        lambda d: ((d["Region"].isin(direct_regions) & d["Technology"].isin({REP_TECH}))
                   | (d["Region"].isin(nonmentioned_set) & d["Technology"].isin(set(OFFSHORE_TECHS)))),
        max_rows + pot_rows,
        "SLA Offshore Wind Scenarios (High Case, cumulative) + NA_restool wind potential for non-mentioned",
    )

    # 4) Tag subsets
    def _accum(calls):
        a, b = 0, 0
        for x, y in calls:
            a += x; b += y
        return a, b
    s1 = _accum(_add_subset("Par_TagTechnologyToSubsets", "Technology", t, "OffshoreWind")
                for t in OFFSHORE_TECHS)
    s2 = _accum(_add_subset("Par_TagRegionToSubsets", "Region", r, "Other_Offshore_Regions")
                for r in OTHER_OFFSHORE_REGIONS)

    # 5) Group caps for OffshoreWind x Other_Offshore_Regions (max = Central <=2033,
    #    High >2033, same near-term throttle as the per-region direct bounds)
    other_low = cumulative(fel.get(("Low Case", "Other"), {}))
    other_central = cumulative(fel.get(("Central Case", "Other"), {}))
    other_high = cumulative(fel.get(("High Case", "Other"), {}))
    other_max = offshore_max(other_central, other_high)
    g_min = _rewrite_group("Par_GroupTotalAnnualMinCapacity",
                           "OffshoreWind", "Other_Offshore_Regions",
                           other_low,
                           "SLA Offshore Wind Scenarios (Low Case, cumulative, 'Other')")
    g_max = _rewrite_group("Par_GroupTotalAnnualMaxCapacity",
                           "OffshoreWind", "Other_Offshore_Regions",
                           other_max,
                           "SLA Offshore Wind Scenarios (Central<=2035 / High>2035, cumulative, 'Other')")

    print(f"\n{'APPLIED' if apply else 'DRY-RUN'}:")
    print(f"  TotalAnnualMinCap (4 direct regions x {REP_TECH}): -{r_min[0]}/+{r_min[1]}")
    print(f"  TotalAnnualMaxCap (direct + nonmentioned x 3 offshore techs): "
          f"-{r_max_direct[0]}/+{r_max_direct[1]}")
    print(f"  TagTechnologyToSubsets OffshoreWind:   +{s1[1]}")
    print(f"  TagRegionToSubsets Other_Offshore_Regions:  +{s2[1]}")
    print(f"  GroupTotalAnnualMinCap Other_Offshore_Regions: -{g_min[0]}/+{g_min[1]}")
    print(f"  GroupTotalAnnualMaxCap Other_Offshore_Regions: -{g_max[0]}/+{g_max[1]}")
    print(f"\n  Cumulative samples (GW):")
    for label in ("CAISO", "PJM", "Other"):
        low = cumulative(fel.get(("Low Case", label), {}))
        central = cumulative(fel.get(("Central Case", label), {}))
        high = cumulative(fel.get(("High Case", label), {}))
        print(f"    {label:6s} cum GW | min(Low) 2030={low[2030]:.2f} 2040={low[2040]:.2f}"
              f" | max=Central<=2033 (2030={central[2030]:.2f} 2033={central[2033]:.2f})"
              f" then High>2033 (2034={high[2034]:.2f} 2040={high[2040]:.2f})")
    if not apply:
        print("\n  (use --apply to write)")


if __name__ == "__main__":
    main()
