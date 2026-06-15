# -*- coding: utf-8 -*-
"""Capacity bounds + RES potentials (merged).

Writes the following NA-side parameters in one pass so guardrail vs. potential
do not overlap:

  Par_ResidualCapacity         : 2025 base * (1 - 0.05*(y-2025)), 2025-2040 —
                                 LINEAR retirement of 5% of the 2025 fleet per
                                 year (constant absolute). P_Nuclear is held
                                 flat (rate 0) — fleet assumed to stay on.
                                 Gas techs additionally get a monotonic
                                 (never-decreasing) TotalAnnualMaxCapacity.
                                 Hydro is the exception: split reservoir/RoR,
                                 residual held FLAT (no retirement) with growth
                                 forced via a strict TotalAnnualMinCapacity (see
                                 the hydro block + Par_ResidualCapacity/
                                 Assumptions.txt). Storage is split into PHS
                                 (fixed existing fleet) + Li-Ion BESS (residual +
                                 min forced to the US Pools storage trajectory,
                                 max open) — block 1d.

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
SRC = os.path.join(HERE, "US Pools - Generation and Capacity.xlsx")
POT_NA = os.path.join(DATA_REPO, "NA_restool", "northamerica_potentials_combined.csv")
POT_CA = os.path.join(DATA_REPO, "NA_restool", "canada_potentials_combined.csv")
PARAM = lambda n: os.path.join(DATA_REPO, "Data", "Parameters", n, n + ".csv")
apply = "--apply" in sys.argv

# Guardrail category -> representative model tech (US Pools dataset,
# "Fuel + Technology" split since the 2026-06 file update).
# "Coal" is handled separately (lignite/hardcoal split below).
# "Storage" is split into PHS + Li-Ion BESS in a dedicated block (1d).
TECH = {"Natural Gas - CCCT":  "P_Gas_CCGT",
        "Natural Gas - SCCT":  "P_Gas_OCGT",
        "Natural Gas - ST":    "P_Gas_Steam",
        "Natural Gas - Other": "P_Gas_Engines",
        "Solar": "P_PV_Utility_Avg",
        "Wind": "P_Wind_Onshore_Avg",
        "Nuclear": "P_Nuclear"}
MODEL_TECHS_GUARDRAIL = set(TECH.values())

# Hydro is split into reservoir + run-of-river and handled in a dedicated block
# (NOT the generic decaying-residual loop): the existing fleet does not retire,
# so ResidualCapacity is FLAT at the 2025 value, and growth to the planned
# trajectory is forced through TotalAnnualMinCapacity (strict to the US Pools
# capacity sheet, with the 2030-2035 trend extrapolated to 2040). Per-region
# run-of-river share — methodology + sources in
# Data/Parameters/Par_ResidualCapacity/Assumptions.txt.
HYDRO_CATEGORY = "Hydro"
HYDRO_TECHS = {"P_Hydro_Reservoir", "P_Hydro_RoR"}
HYDRO_ROR_SHARE = {"NewYork": 0.80, "WECC": 0.60, "MISO": 0.60, "SPP": 0.60,
                   "NewEngland": 0.50, "California": 0.35, "SERC": 0.20,
                   "ERCOT": 0.15, "PJM": 0.10, "Canada": 0.30}
HYDRO_ROR_DEFAULT = 0.40
HYDRO_MAX_HEADROOM = 1.10   # TotalAnnualMaxCapacity = strict sheet min * 1.10

# Storage split: the US Pools "Storage" category lumps pumped hydro + batteries.
# It is split into existing pumped hydro (D_PHS, fixed fleet — there is no new
# US PHS at scale) and battery storage, which is mapped to Li-Ion (essentially
# all deployed US grid batteries today are Li-Ion). The 2025 PHS fleet per
# region (GW, EIA-860 / known plants — see Assumptions.txt); the remainder of
# US Pools "Storage" (and all of its growth) is Li-Ion BESS.
STORAGE_CATEGORY = "Storage"
STORAGE_TECHS = {"D_PHS", "D_Battery_Li-Ion"}
STORAGE_UNCAPPED = 999999   # Li-Ion BESS max left open above the planned floor
PHS_GW_2025 = {"California": 4.0, "SERC": 6.5, "PJM": 5.0, "MISO": 2.6,
               "NewEngland": 1.8, "WECC": 1.5, "NewYork": 1.4,
               "ERCOT": 0.0, "SPP": 0.0}

# Coal split: lignite is mine-mouth only (no interregional market). 2025 GW
# per region from plant-level research (ND fleet ~3.9 in MISO, TX ~4.4 in
# ERCOT incl. San Miguel, Red Hills 0.44 in SERC). Remainder of the US Pools
# "Coal" category is hardcoal. No new coal builds: MaxCapacity follows the
# residual trajectory exactly; all other regions get lignite MaxCapacity 0.
COAL_CATEGORY = "Coal"
LIGNITE_GW_2025 = {"MISO": 3.9, "ERCOT": 4.4, "SERC": 0.44}
SAN_MIGUEL_GW, SAN_MIGUEL_RETIRE_YEAR = 0.41, 2028   # solar+storage conversion
CANADA_LIGNITE_GW = 1.53   # SaskPower life-extension (10/2025), flat to 2040
COAL_TECHS = {"P_Coal_Lignite", "P_Coal_Hardcoal"}

# ---------------------------------------------------------------------------
# Canada: CER "Canada's Energy Future 2026" (canada_power_ef2026.xlsx).
# National primary_fuel capacity trajectory (Current Measures) drives residual
# 2025 + min/max guardrails. The CER has no gas technology split, so the
# "Natural Gas" total is divided by the operating-fleet shares from the GEM
# Global Oil & Gas Plant Tracker (Jan 2026): CC 62 / GT 16 / ST 21.5 /
# IC 0.5 % (gas-fired units; pure-oil units belong to the CER Oil category).
# Solar is split utility/distributed by the CER technology-resolution ratio.
# Canadian hardcoal (NS/NB/AB, ~2.5 GW in 2025) follows the CER decline to 0
# by 2035; SK lignite stays at the SaskPower 1.53 GW flat.
# ---------------------------------------------------------------------------
CANADA_SRC = os.path.join(HERE, "canada_power_ef2026.xlsx")
CANADA_SCENARIO = "Current Measures"
CANADA_GAS_SPLIT = {"P_Gas_CCGT": 0.62, "P_Gas_OCGT": 0.16,
                    "P_Gas_Steam": 0.215, "P_Gas_Engines": 0.005}
CANADA_TECH = {  # CER primary_fuel category -> model tech (gas/solar special)
    "Hydro / Wave / Tidal": "P_Hydro_Reservoir",
    "Uranium": "P_Nuclear",
    "Wind": "P_Wind_Onshore_Avg",
    "Oil": "P_Oil",
    "Biomass / Geothermal": "P_Biomass",
}
CANADA_SOLAR_DISTRIBUTED_SHARE = 0.24   # CER technology res: 1.70/7.15 in 2025
# Doubled funnel vs the US (trajectory deliberately rougher): +/-4% to 2028,
# widening to -20%/+60% at 2035 (hydro +20%), held from there (CER data runs
# through 2040 so no post-2035 extrapolation is needed).
CANADA_MARGIN_NEAR = 0.04
CANADA_MARGIN_2035_MIN = 0.80
CANADA_MARGIN_2035_MAX_DEFAULT = 1.60
CANADA_MARGIN_2035_MAX_PER_TECH = {"P_Hydro_Reservoir": 1.20}

def canada_margins(year, tech=None):
    y = min(year, 2035)
    mx_2035 = CANADA_MARGIN_2035_MAX_PER_TECH.get(tech, CANADA_MARGIN_2035_MAX_DEFAULT)
    if y <= 2028:
        mn, mx = 1 - CANADA_MARGIN_NEAR, 1 + CANADA_MARGIN_NEAR
    else:
        frac = (y - 2028) / (2035 - 2028)
        mn = (1 - CANADA_MARGIN_NEAR) + (CANADA_MARGIN_2035_MIN - (1 - CANADA_MARGIN_NEAR)) * frac
        mx = (1 + CANADA_MARGIN_NEAR) + (mx_2035 - (1 + CANADA_MARGIN_NEAR)) * frac
    if tech == "P_Nuclear":
        mn = 1.0
    return mn, mx

def read_canada_cer():
    """Return ({tech: {year: GW}}, {year: hardcoal_GW}) from the CER workbook."""
    df = pd.read_excel(CANADA_SRC, sheet_name="Capacity")
    df["MW"] = pd.to_numeric(df["MW"], errors="coerce")
    df["Year"] = pd.to_numeric(df["Year"], errors="coerce")
    sel = df[(df["Scenario"] == CANADA_SCENARIO) & (df["Year"].between(2025, 2040))]
    pf = sel[(sel["Resolution"] == "primary_fuel") & (sel["Region_Code"] == "CA")]

    traj = {}
    def series(variable):
        s = pf[pf["Variable"] == variable]
        return {int(y): float(m) / 1000.0 for y, m in zip(s["Year"], s["MW"])}

    for var, tech in CANADA_TECH.items():
        traj[tech] = series(var)
    gas = series("Natural Gas")
    for tech, share in CANADA_GAS_SPLIT.items():
        traj[tech] = {y: v * share for y, v in gas.items()}
    solar = series("Solar")
    traj["P_PV_Utility_Avg"] = {y: v * (1 - CANADA_SOLAR_DISTRIBUTED_SHARE) for y, v in solar.items()}
    traj["P_PV_Rooftop_Commercial"] = {y: v * CANADA_SOLAR_DISTRIBUTED_SHARE for y, v in solar.items()}

    # Hardcoal: technology resolution, provinces ex-SK (SK = lignite), no CCUS
    tech_res = sel[(sel["Resolution"] == "technology") &
                   (sel["Variable"] == "Coal and Coke") &
                   (~sel["Region_Code"].isin(["CA", "SK"]))]
    hardcoal = tech_res.groupby("Year")["MW"].sum() / 1000.0
    hardcoal = {int(y): float(v) for y, v in hardcoal.items()}
    return traj, hardcoal

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

# Full set of techs this script directly writes positive caps for.
ALL_MANAGED_TECHS = MODEL_TECHS_GUARDRAIL | set(ALL_RESTOOL_TECHS) | COAL_TECHS | HYDRO_TECHS | STORAGE_TECHS

# Techs whose caps are owned by other scripts — leave them alone here.
EXTERNAL_OWNERS = {
    # add_offshore_wind_bounds.py
    "P_Wind_Offshore_Deep", "P_Wind_Offshore_Shallow", "P_Wind_Offshore_Transitional",
    # add_egs.py
    "P_EGS_R1", "P_EGS_R2", "P_EGS_R3", "P_EGS_R4",
}

# Every remaining power-producing tech (P_*, CHP_*) gets MaxCap=0 in the NA
# pool regions + Canada. Storage (D_*, S_*), sector-coupling and demand techs
# stay untouched. Rooftop Residential explicitly zeroed (only Commercial is
# allowed to carry the rooftop potential).
TECH_SHEET = lambda: os.path.join(DATA_REPO, "Data", "Parameters", "00_Sets&Tags", "Sets_Technology.csv")

# Retirement: LINEAR, as share of the 2025 base per year (5% of the 2025
# fleet retires each year — constant absolute retirement, not geometric;
# geometric 0.95^y made retirements slow down over time).
RETIRE_RATE_DEFAULT = 0.05
RETIRE_RATE_PER_TECH = {"P_Nuclear": 0.0}

def residual_factor(tech, year):
    rate = RETIRE_RATE_PER_TECH.get(tech, RETIRE_RATE_DEFAULT)
    return max(0.0, 1.0 - rate * (year - 2025))

def hydro_sheet_traj(values_2025_2035):
    """Hydro capacity trajectory: the US Pools sheet 2025-2035 verbatim, with
    2036-2040 linearly extrapolated from the 2030-2035 trend. `values_2025_2035`
    is a {year: GW} dict that must cover 2025..2035."""
    s = dict(values_2025_2035)
    slope = (s[2035] - s.get(2030, s[2035])) / 5.0
    for y in range(2036, 2041):
        s[y] = max(0.0, s[2035] + slope * (y - 2035))
    return s

# Gas technologies: TotalAnnualMaxCapacity must never decrease over the years
# — a dipping cap forces the model to scrap capacity it was allowed (or
# needed) to build earlier, which is infeasible with NewCapacity >= 0.
MONOTONIC_MAX_TECHS = {"P_Gas_CCGT", "P_Gas_OCGT", "P_Gas_Steam", "P_Gas_Engines"}

YEARS = list(range(2025, 2041))
DATE, WHO = "2026-06-04", "Konstantin Loffler <kl@wip.tu-berlin.de>"

# Max-side widening cap at 2035. Default is 1.30 (+30%). Hydro is narrower —
# reservoirs are physically constrained, the funnel should not pretend they can
# triple in capacity.
MAX_WIDEN_2035_DEFAULT = 1.30
MAX_WIDEN_2035_PER_TECH = {"P_Hydro_Reservoir": 1.10}

# Annual MAX growth applied after 2035 for techs WITHOUT a restool potential
# target. PV/Wind interpolate to the restool potential at 2040 (different code
# path) — these rates only apply to thermal + hydro. Without this growth the
# 2036-2040 cap would be flat which contradicts e.g. the Nuclear/USA target
# floor reaching 129.8 GW in 2040.
POST_2035_MAX_GROWTH = {
    "P_Gas_CCGT":         0.05,
    "P_Nuclear":          0.05,
    "P_Hydro_Reservoir":  0.02,
}

# Nuclear/USA target floor (GroupTotalAnnualMinCapacity).
NUCLEAR_USA_GROUP_MIN = {
    2035: 116.0,   2036: 118.3,   2037: 121.43,
    2038: 123.932, 2039: 123.932, 2040: 129.832,
}


def margins(year, tech=None):
    """(min_factor, max_factor) widening from +/-2% (<=2028) to -10%/+max(2035)
    where max(2035) is per-tech (1.30 default, 1.10 for hydro). Year capped at
    2035 here; post-2035 growth is handled separately by POST_2035_MAX_GROWTH."""
    y = min(year, 2035)
    mx_2035 = MAX_WIDEN_2035_PER_TECH.get(tech, MAX_WIDEN_2035_DEFAULT)
    if y <= 2028:
        mn, mx = 0.98, 1.02
    else:
        frac = (y - 2028) / (2035 - 2028)
        mn = 0.98 + (0.90 - 0.98) * frac
        mx = 1.02 + (mx_2035 - 1.02) * frac
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
    # 2026-06 file update: category column renamed to "Fuel + Technology",
    # measure column is unnamed (3rd position).
    df = df.rename(columns={df.columns[1]: "Category", df.columns[2]: "Measure"})
    cap = df[df["Measure"] == "Capacity MW"].copy()
    pot = read_restool_potentials()

    def gw(region, fuel, year):
        sel = cap[(cap["Pool-Regions"] == region) & (cap["Category"] == fuel)]
        if sel.empty or year not in sel.columns:
            return 0.0
        return max(0.0, float(sel.iloc[0][year])) / 1000.0   # MW->GW, clamp >=0

    pool_regions = sorted(cap["Pool-Regions"].unique())
    extra_regions = [r for r in pot.keys() if r not in pool_regions]  # Canada etc.

    res_rows, min_rows, max_rows = [], [], []

    # 1) Guardrail funnel (5 fuel groups x US pool regions). We also accumulate
    #    per (region, year) the "excess" between the rep guardrail trajectory
    #    (max and min) and the rep's share of the per-region restool potential.
    #    Max excess spills into _Opt (up to Opt's headroom). Min excess flows
    #    through _Opt then _Inf so the per-region min requirement stays
    #    satisfiable when the rep alone cannot carry it.
    excess_by_region_rep_year     = {}   # {(region, rep, year): max_excess_GW}
    excess_min_by_region_rep_year = {}   # {(region, rep, year): min_excess_GW}
    for region in pool_regions:
        # Rep's share of total potential (per family). Used to bound rep_cap
        # at the share and to compute excess (= rep guardrail - share).
        rep_share_pot = {}
        for rep, col in GUARDRAIL_REP_TO_RESTOOL_COL.items():
            tot = pot.get(region, {}).get(col)
            rep_share_pot[rep] = (tot * TECH_SHARE.get(rep, 0.0)) if tot is not None else None
        for fuel, tech in TECH.items():
            base = gw(region, fuel, 2025)
            for y in YEARS:
                res_rows.append((region, tech, y, round(base * residual_factor(tech, y), 6)))

            # 2035 funnel anchors for post-2035 interp + min hold
            val_2035 = base if tech == "P_Nuclear" else gw(region, fuel, 2035)
            mn_at_2035, mx_at_2035 = margins(2035, tech)
            max_2035 = val_2035 * mx_at_2035
            min_2035 = val_2035 * mn_at_2035

            target_2040 = rep_share_pot.get(tech)  # rep share x total pot (None if N/A)

            running_max = 0.0   # monotonic floor for MONOTONIC_MAX_TECHS
            for y in range(2026, 2041):
                if y <= 2035:
                    val = base if tech == "P_Nuclear" else gw(region, fuel, y)
                    mn, mx = margins(y, tech)
                    raw_min = val * mn
                    raw_max = val * mx
                else:
                    # min: hold 2035 funnel min (no contraction post-2035)
                    raw_min = min_2035
                    # max: interp 2035 funnel -> 2040 share-of-potential if a
                    # restool target is available; otherwise compound growth
                    # using POST_2035_MAX_GROWTH (thermal/hydro) or hold flat.
                    if target_2040 is not None and target_2040 > 0:
                        frac = (y - 2035) / 5.0
                        raw_max = max_2035 + (target_2040 - max_2035) * frac
                    else:
                        rate = POST_2035_MAX_GROWTH.get(tech, 0.0)
                        raw_max = max_2035 * (1.0 + rate) ** (y - 2035)

                # Cap rep tech at its share of total potential. Excess spills
                # into _Opt (and, for min only, then into _Inf) so the (min ≤
                # max) invariant survives capping by the regional potential.
                share_cap = rep_share_pot.get(tech)
                if share_cap is not None:
                    rep_max = min(raw_max, share_cap)
                    rep_min = min(raw_min, share_cap)
                    excess_by_region_rep_year[(region, tech, y)]     = max(0.0, raw_max - share_cap)
                    excess_min_by_region_rep_year[(region, tech, y)] = max(0.0, raw_min - share_cap)
                else:
                    rep_max = raw_max
                    rep_min = raw_min
                if tech in MONOTONIC_MAX_TECHS:
                    rep_max = max(rep_max, running_max)
                    running_max = rep_max
                min_rows.append((region, tech, y, round(rep_min, 6)))
                max_rows.append((region, tech, y, round(rep_max, 6)))

        # 1b) Coal: split the US Pools "Coal" capacity into lignite (fixed
        #     regional fleet, mine-mouth fuel) and hardcoal (remainder).
        #     No new coal builds in the US: MaxCapacity = residual trajectory.
        #     San Miguel (ERCOT lignite, 0.41 GW) converts to solar+storage.
        coal_base = gw(region, COAL_CATEGORY, 2025)
        lign_base = min(LIGNITE_GW_2025.get(region, 0.0), coal_base)
        hard_base = max(0.0, coal_base - lign_base)
        for tech, base in (("P_Coal_Lignite", lign_base), ("P_Coal_Hardcoal", hard_base)):
            for y in YEARS:
                eff_base = base
                if tech == "P_Coal_Lignite" and region == "ERCOT" and y >= SAN_MIGUEL_RETIRE_YEAR:
                    eff_base = max(0.0, base - SAN_MIGUEL_GW)
                v = round(eff_base * residual_factor(tech, y), 6)
                res_rows.append((region, tech, y, v))
                max_rows.append((region, tech, y, v))   # no new coal builds

        # 1c) Hydro: split into reservoir + run-of-river (per-region RoR share).
        #     Residual is FLAT at the 2025 fleet (hydro does not retire); the
        #     planned growth is forced via TotalAnnualMinCapacity strict to the
        #     US Pools sheet (2030-2035 trend extrapolated to 2040). Max keeps a
        #     small headroom (HYDRO_MAX_HEADROOM) above the strict min.
        h_traj = hydro_sheet_traj({y: gw(region, HYDRO_CATEGORY, y) for y in range(2025, 2036)})
        ror = HYDRO_ROR_SHARE.get(region, HYDRO_ROR_DEFAULT)
        for tech, sh in (("P_Hydro_Reservoir", 1.0 - ror), ("P_Hydro_RoR", ror)):
            for y in YEARS:
                res_rows.append((region, tech, y, round(sh * h_traj[2025], 6)))
                min_rows.append((region, tech, y, round(sh * h_traj[y], 6)))
                max_rows.append((region, tech, y, round(sh * h_traj[y] * HYDRO_MAX_HEADROOM, 6)))

        # 1d) Storage: split US Pools "Storage" into existing pumped hydro (fixed)
        #     + Li-Ion BESS. PHS is held flat at the 2025 fleet (residual = min =
        #     max, no new US PHS). The battery share (Storage - PHS) and all its
        #     growth go to D_Battery_Li-Ion: residual = the 2025 battery fleet
        #     (retiring at the default rate), TotalAnnualMinCapacity forces the
        #     US Pools storage trajectory (2030-2035 trend -> 2040) via the
        #     standard funnel, and the max is left open above that floor.
        s_traj = hydro_sheet_traj({y: gw(region, STORAGE_CATEGORY, y) for y in range(2025, 2036)})
        phs = min(PHS_GW_2025.get(region, 0.0), s_traj[2025])
        bess_2025 = max(0.0, s_traj[2025] - phs)
        for y in YEARS:
            res_rows.append((region, "D_PHS", y, round(phs, 6)))
            min_rows.append((region, "D_PHS", y, round(phs, 6)))
            max_rows.append((region, "D_PHS", y, round(phs, 6)))
            bess = max(0.0, s_traj[y] - phs)
            mn, _ = margins(y)
            res_rows.append((region, "D_Battery_Li-Ion", y, round(bess_2025 * residual_factor("D_Battery_Li-Ion", y), 6)))
            min_rows.append((region, "D_Battery_Li-Ion", y, round(bess * mn, 6)))
            max_rows.append((region, "D_Battery_Li-Ion", y, round(STORAGE_UNCAPPED, 6)))

        # 2) Non-rep restool variants per region. Behaviour:
        #    Max:
        #     - 2025-2035: cap = 0 (do not introduce these variants yet)
        #     - 2036-2040: linear ramp from 0 to (share * total_potential) at 2040
        #     - _Opt additionally absorbs the rep's MAX excess, capped at its
        #       remaining headroom below its own share*pot.
        #    Min:
        #     - The rep's MIN excess flows to _Opt first (bounded by Opt's
        #       max value at year y), then any residual to _Inf (bounded by
        #       Inf's max). So total per-region min is preserved without ever
        #       requiring more than that variant's own max.
        for col, info in RESTOOL_MAP.items():
            pot_val = pot.get(region, {}).get(col, 0.0)
            rep = info["rep"]
            if rep is None:
                # Single variant (Rooftop) — share fraction flat across years
                for variant, share in info["variants"].items():
                    target = pot_val * share
                    for y in YEARS:
                        max_rows.append((region, variant, y, round(target, 6)))
                continue
            opt_tech = next((v for v in info["variants"] if v.endswith("_Opt")), None)
            inf_tech = next((v for v in info["variants"] if v.endswith("_Inf")), None)
            opt_share = info["variants"].get(opt_tech, 0.0)
            inf_share = info["variants"].get(inf_tech, 0.0)
            opt_target = pot_val * opt_share
            inf_target = pot_val * inf_share
            for y in YEARS:
                frac = 0.0 if y <= 2035 else (y - 2035) / 5.0
                opt_base = opt_target * frac
                inf_base = inf_target * frac
                exc_max = excess_by_region_rep_year.get((region, rep, y), 0.0)
                opt_max = opt_base + min(exc_max, max(0.0, opt_target - opt_base))
                inf_max = inf_base
                # Min spillover: Opt -> Inf, each bounded by own max
                exc_min = excess_min_by_region_rep_year.get((region, rep, y), 0.0)
                opt_min = min(exc_min, opt_max)
                inf_min = min(max(0.0, exc_min - opt_min), inf_max)
                if opt_tech is not None:
                    max_rows.append((region, opt_tech, y, round(opt_max, 6)))
                    if opt_min > 0:
                        min_rows.append((region, opt_tech, y, round(opt_min, 6)))
                if inf_tech is not None:
                    max_rows.append((region, inf_tech, y, round(inf_max, 6)))
                    if inf_min > 0:
                        min_rows.append((region, inf_tech, y, round(inf_min, 6)))

    # 3) Canada: CER EF2026 trajectory drives residual 2025 + min/max funnel
    #    (doubled margins vs the US). Restool keeps the _Opt/_Inf upside ramps
    #    2036-2040 on top; the rep variants and rooftop are owned by the CER
    #    block, so they are skipped in the restool loop below.
    canada_techs = set()
    if os.path.exists(CANADA_SRC) and "Canada" in extra_regions:
        traj, ca_hardcoal = read_canada_cer()
        canada_techs = set(traj.keys()) | {"P_Hydro_RoR"}   # RoR also CER-owned
        for tech, ser in sorted(traj.items()):
            base = ser.get(2025, 0.0)
            # Hydro: same treatment as the US pools — flat residual, strict min
            # to the CER trajectory, split reservoir/run-of-river.
            if tech == "P_Hydro_Reservoir":
                ror = HYDRO_ROR_SHARE.get("Canada", HYDRO_ROR_DEFAULT)
                for ht, sh in (("P_Hydro_Reservoir", 1.0 - ror), ("P_Hydro_RoR", ror)):
                    for y in YEARS:
                        val = ser.get(y, base)
                        res_rows.append(("Canada", ht, y, round(sh * base, 6)))
                        min_rows.append(("Canada", ht, y, round(sh * val, 6)))
                        max_rows.append(("Canada", ht, y, round(sh * val * HYDRO_MAX_HEADROOM, 6)))
                continue
            running_max = 0.0
            for y in YEARS:
                res_rows.append(("Canada", tech, y, round(base * residual_factor(tech, y), 6)))
                mn, mx = canada_margins(y, tech)
                val = ser.get(y, base)
                rep_min, rep_max = val * mn, val * mx
                if tech in MONOTONIC_MAX_TECHS:
                    rep_max = max(rep_max, running_max)
                    running_max = rep_max
                min_rows.append(("Canada", tech, y, round(rep_min, 6)))
                max_rows.append(("Canada", tech, y, round(rep_max, 6)))

    # 3a) Other extra regions + Canada upside variants from restool potentials.
    for region in extra_regions:
        for col, info in RESTOOL_MAP.items():
            pot_val = pot.get(region, {}).get(col, 0.0)
            rep = info["rep"]
            for variant, share in info["variants"].items():
                if region == "Canada" and variant in canada_techs:
                    continue   # CER block owns rep + rooftop for Canada
                target = pot_val * share
                for y in YEARS:
                    if variant == rep or rep is None:
                        val = target
                    elif y <= 2035:
                        val = 0.0
                    else:
                        val = target * ((y - 2035) / 5.0)
                    max_rows.append((region, variant, y, round(val, 6)))

    # 3b) Coal in extra regions: SK lignite stays at the SaskPower 1.53 GW
    #     flat (CER shows 1.39 incl. Boundary Dam CCS — same picture).
    #     Hardcoal (NS/NB/AB) follows the CER decline to 0 by ~2035.
    #     MaxCapacity = residual (no new coal builds).
    for region in extra_regions:
        lign = CANADA_LIGNITE_GW if region == "Canada" else 0.0
        for y in YEARS:
            hard = ca_hardcoal.get(y, 0.0) if (region == "Canada" and canada_techs) else 0.0
            res_rows.append((region, "P_Coal_Lignite", y, lign))
            max_rows.append((region, "P_Coal_Lignite", y, lign))
            res_rows.append((region, "P_Coal_Hardcoal", y, round(hard, 6)))
            max_rows.append((region, "P_Coal_Hardcoal", y, round(hard, 6)))

    all_regions = pool_regions + extra_regions

    # 4) Zero-out unmanaged power-producing techs (P_*, CHP_*) for the NA
    #    regions + Canada. Storage (D_*, S_*) and sector-coupling techs are
    #    untouched. Techs covered by sibling scripts (offshore wind, EGS) stay.
    #    Explicit zero for P_PV_Rooftop_Residential (rooftop generation lives
    #    only on P_PV_Rooftop_Commercial in this dataset).
    all_techs = pd.read_csv(TECH_SHEET()).iloc[:, 0].astype(str).tolist()
    zero_techs = sorted(
        t for t in all_techs
        if (t.startswith("P_") or t.startswith("CHP_"))
        and t not in ALL_MANAGED_TECHS
        and t not in EXTERNAL_OWNERS
    )
    zero_rows = []
    for region in all_regions:
        for tech in zero_techs:
            # Canada: techs carried by the CER block (e.g. P_Oil, P_Biomass)
            # are managed there and must not be zeroed.
            if region == "Canada" and tech in canada_techs:
                continue
            for y in YEARS:
                zero_rows.append((region, tech, y, 0.0))
    max_rows.extend(zero_rows)

    all_written_techs = ALL_MANAGED_TECHS | set(zero_techs)

    def write(param, rows, src):
        path = PARAM(param)
        d = pd.read_csv(path)
        d = d.rename(columns={"Unnamed: 4": ""})
        drop = d["Region"].isin(all_regions) & d["Technology"].isin(all_written_techs)
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
               "US Pools gen/cap 2025 base, linear 5%-of-base/yr retirement (Nuclear held flat)")
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
