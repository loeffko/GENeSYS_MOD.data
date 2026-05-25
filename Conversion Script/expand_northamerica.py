# -*- coding: utf-8 -*-
"""
expand_northamerica.py
----------------------
Driver script: adds a placeholder North America region set (9 US regions +
Canada) and individual model years 2025-2040 to the GENeSYS-MOD data set, then
reconfigures Set_filter_file.xlsx for a North America run.

Placeholder data is copied 1:1 from ten central-European countries (see
REGION_MAP) and tagged in the Source column as "dummy data - empty entry".
Missing years are linearly interpolated between existing data points.

Run from the "Conversion Script" directory:

    python expand_northamerica.py

All edits are in-place in the (git-tracked) GENeSYS_MOD.data repo, so they can
be reviewed with `git diff` and reverted with `git checkout` if needed.

To extend later (new technologies/fuels/etc.) reuse functions/expand_data.py:
`duplicate_member_in_df(df, "Technology", source_tech, new_tech)` and friends.
"""

import os
import shutil
from functions.expand_data import (
    expand_all_parameters,
    append_set_entries,
    timeseries_csv_paths,
    add_timeseries_columns,
    append_selection_rows,
    update_selection_sheet,
)

# ----------------------------------------------------------------------
# Configuration  (edit here to retarget the tool)
# ----------------------------------------------------------------------

# new_region -> source country to copy placeholder data from (1:1 / bijection)
REGION_MAP = {
    "California":  "DE",
    "WECC":        "FR",
    "SPP":         "NL",
    "MISO":        "BE",
    "ERCOT":       "AT",
    "SERC":        "CZ",
    "PJM":         "CH",
    "NewYork":     "PL",
    "NewEngland":  "IT",
    "Canada":      "ES",
}

# every individual year of the modelled horizon
TARGET_YEARS = list(range(2025, 2041))          # 2025 ... 2040 inclusive

# years left enabled in the filter file: base year + full 2025-2040 horizon
BASE_YEAR = 2018
ENABLED_YEARS = [BASE_YEAR] + TARGET_YEARS

# regions left enabled in the filter file (World must stay enabled)
ENABLED_REGIONS = ["World"] + list(REGION_MAP.keys())

# Power-only preset for the North America model: only these fuels / technologies /
# storages stay enabled in Set_filter_file_NorthAmerica.xlsx; every other member is
# set to 0. Transport, heat, industry, resources, transformation and fuel imports are
# dropped. Thermal plants are KEPT and simply run without an input fuel (their input
# fuels are filtered out). Emissions (currently fuel-input-side) drop to zero - rework
# on the output side when emission limits are needed.
POWER_FUELS = ["Power"]

POWER_STORAGES = ["S_Battery_Li-Ion", "S_Battery_Redox", "S_CAES", "S_PHS"]

POWER_TECHNOLOGIES = [
    # Power generation (P_*)
    "P_Biomass", "P_Biomass_CCS", "P_Coal_Hardcoal", "P_Coal_Hardcoal_CCS",
    "P_Coal_Lignite", "P_Coal_Lignite_CCS", "P_CSP", "P_Gas_CCGT", "P_Gas_CCS",
    "P_Gas_Engines", "P_Gas_OCGT", "P_Geothermal", "P_H2_OCGT",
    "P_Hydro_Reservoir", "P_Hydro_RoR", "P_Nuclear", "P_Ocean", "P_Oil",
    "P_PV_Rooftop_Commercial", "P_PV_Rooftop_Residential", "P_PV_Utility_Avg",
    "P_PV_Utility_Inf", "P_PV_Utility_Opt", "P_PV_Utility_Tracking",
    "P_Wind_Offshore_Deep", "P_Wind_Offshore_Shallow",
    "P_Wind_Offshore_Transitional", "P_Wind_Onshore_Avg", "P_Wind_Onshore_Inf",
    "P_Wind_Onshore_Opt",
    # Combined heat & power (kept; heat output filtered out -> power only)
    "CHP_Biomass_Solid", "CHP_Biomass_Solid_CCS", "CHP_Coal_Hardcoal",
    "CHP_Coal_Hardcoal_CCS", "CHP_Coal_Lignite", "CHP_Coal_Lignite_CCS",
    "CHP_Gas_CCGT_Biogas", "CHP_Gas_CCGT_Biogas_CCS", "CHP_Gas_CCGT_Natural",
    "CHP_Gas_CCGT_Natural_CCS", "CHP_Gas_CCGT_SynGas", "CHP_Hydrogen_FuelCell",
    "CHP_Oil", "CHP_WasteToEnergy",
    # Power storage charge/discharge technologies
    "D_Battery_Li-Ion", "D_Battery_Redox", "D_CAES", "D_PHS",
]


# ----------------------------------------------------------------------
# Paths
# ----------------------------------------------------------------------
HERE = os.path.dirname(os.path.abspath(__file__))
DATA_REPO = os.path.normpath(os.path.join(HERE, ".."))
PARAMETERS_DIR = os.path.join(DATA_REPO, "Data", "Parameters")
SETS_DIR = os.path.join(PARAMETERS_DIR, "00_Sets&Tags")
TIMESERIES_DIR = os.path.join(DATA_REPO, "Data", "Timeseries")

# Universal filter file (all choices present) and the North America preset.
UNIVERSAL_FILTER = os.path.join(HERE, "Set_filter_file.xlsx")
NA_FILTER = os.path.join(HERE, "Set_filter_file_NorthAmerica.xlsx")


def main():
    print("GENeSYS-MOD data expansion: North America")
    print("=" * 60)

    # 1) Sets ----------------------------------------------------------
    print("\n[1/5] Updating Sets ...")
    new_regions = append_set_entries(
        os.path.join(SETS_DIR, "Sets_Region.csv"), REGION_MAP.keys())
    print(f"  Sets_Region.csv : added {len(new_regions)} regions")
    new_years = append_set_entries(
        os.path.join(SETS_DIR, "Sets_Year.csv"), TARGET_YEARS)
    print(f"  Sets_Year.csv   : added {len(new_years)} years")

    # Scenario marker: lets the conversion tool accept scenario 'NorthAmerica'.
    # North America data lives in the base Par_*.csv files - no overrides - so
    # a single empty marker folder is enough for validate_input() to pass.
    marker_dir = os.path.join(PARAMETERS_DIR, "Par_CapitalCost", "NorthAmerica")
    os.makedirs(marker_dir, exist_ok=True)
    marker = os.path.join(marker_dir, "dummy.txt")
    if not os.path.exists(marker):
        with open(marker, "w", encoding="utf-8") as f:
            f.write("Placeholder: 'NorthAmerica' scenario uses the base "
                    "Par_*.csv data; no scenario-specific overrides.\n")
    print("  NorthAmerica scenario marker ensured")

    # 2) Parameter CSVs: add regions, then interpolate years -----------
    print("\n[2/5] Adding regions to parameter CSVs ...")
    expand_all_parameters(PARAMETERS_DIR, region_map=REGION_MAP)

    print("\n[3/5] Interpolating years in parameter CSVs ...")
    expand_all_parameters(PARAMETERS_DIR, target_years=TARGET_YEARS)

    # 3) Timeseries ----------------------------------------------------
    print("\n[4/5] Adding regions to timeseries CSVs ...")
    for ts in timeseries_csv_paths(TIMESERIES_DIR):
        added = add_timeseries_columns(ts, REGION_MAP)
        print(f"  {os.path.basename(ts):28s} added {len(added)} region columns")

    # 4) Filter files --------------------------------------------------
    print("\n[5/5] Building filter files ...")
    # Universal file: keep every choice present, leave selections untouched.
    append_selection_rows(UNIVERSAL_FILTER, "Region_selection", REGION_MAP.keys())
    append_selection_rows(UNIVERSAL_FILTER, "Year_selection", TARGET_YEARS)
    print(f"  {os.path.basename(UNIVERSAL_FILTER)} : new regions/years added (selections untouched)")

    # North America preset: copy the universal file, then preselect.
    shutil.copyfile(UNIVERSAL_FILTER, NA_FILTER)
    update_selection_sheet(NA_FILTER, "Region_selection",
                           enabled=ENABLED_REGIONS,
                           add_rows=list(REGION_MAP.keys()))
    update_selection_sheet(NA_FILTER, "Year_selection",
                           enabled=ENABLED_YEARS,
                           add_rows=TARGET_YEARS)
    print(f"  {os.path.basename(NA_FILTER)} : regions {ENABLED_REGIONS}")
    print(f"  {os.path.basename(NA_FILTER)} : years {sorted(ENABLED_YEARS)}")

    # Power-only preset: keep only power fuels / generation+CHP+storage techs;
    # every other Fuel/Technology/Storage member is set to 0.
    update_selection_sheet(NA_FILTER, "Fuel_selection",       enabled=POWER_FUELS)
    update_selection_sheet(NA_FILTER, "Technology_selection", enabled=POWER_TECHNOLOGIES)
    update_selection_sheet(NA_FILTER, "Storage_selection",    enabled=POWER_STORAGES)
    print(f"  {os.path.basename(NA_FILTER)} : power-only (fuels={len(POWER_FUELS)}, "
          f"techs={len(POWER_TECHNOLOGIES)}, storages={len(POWER_STORAGES)})")

    print("\nDone. Review with `git diff` in the GENeSYS_MOD.data repo.")


if __name__ == "__main__":
    main()
