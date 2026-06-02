# -*- coding: utf-8 -*-
"""Integrate NA_restool outputs into the GENeSYS-MOD data CSVs.

1) Timeseries: overwrite the North-America region columns (9 US ISOs + Canada)
   in each TS_<TECH>.csv with the values produced by the restool. Both
   `2018_northamerica_*` (9 ISOs) and `2018_canada_*` files are merged.

2) Potentials: replace the 2035+ rows of Par_TotalAnnualMaxCapacity for each
   NA region × renewable tech with the restool potential. 2018-2030 rows are
   preserved (gradual ramp). The restool potential per region is treated as
   the upper deployment bound for each variant of PV / Wind separately.
"""
import csv
import os
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
RESTOOL = os.path.join(HERE, "NA_restool")
TS_DIR  = os.path.join(HERE, "Data", "Timeseries")
MAXCAP_CSV = os.path.join(HERE, "Data", "Parameters",
                          "Par_TotalAnnualMaxCapacity",
                          "Par_TotalAnnualMaxCapacity.csv")

NA_US      = ["California", "ERCOT", "MISO", "NewEngland", "NewYork",
              "PJM", "SERC", "SPP", "WECC"]
NA_ALL     = NA_US + ["Canada"]
FUTURE_YRS = [2035, 2040, 2045, 2050]
KEEP_YRS   = [2018, 2025, 2030]   # preserved unchanged

# restool file stem -> target TS folder
TS_MAP = {
    "usable_pv_avg":                      "TS_PV_AVG",
    "usable_pv_inf":                      "TS_PV_INF",
    "usable_pv_opt":                      "TS_PV_OPT",
    "usable_wind_onshore_avg":            "TS_WIND_ONSHORE_AVG",
    "usable_wind_onshore_inf":            "TS_WIND_ONSHORE_INF",
    "usable_wind_onshore_opt":            "TS_WIND_ONSHORE_OPT",
    "usable_wind_offshore_deep":          "TS_WIND_OFFSHORE_DEEP",
    "usable_wind_offshore_shallow":       "TS_WIND_OFFSHORE_SHALLOW",
    "usable_wind_offshore_transitional":  "TS_WIND_OFFSHORE",
    # heat/cool live in HEAT_LOW / COOL_LOW (closest existing TS).
    "heating":                            "TS_HEAT_LOW",
    "cooling":                            "TS_COOL_LOW",
    # rooftop_avg: no dedicated TS — rooftop tech in this model is area-based
}

# Potentials CSV column -> list of model techs that should share that potential
POTENTIAL_MAP = {
    "PV Capacity [GW]":      ["P_PV_Utility_Avg", "P_PV_Utility_Inf",
                              "P_PV_Utility_Opt", "P_PV_Utility_Tracking"],
    "Wind Capacity [GW]":    ["P_Wind_Onshore_Avg", "P_Wind_Onshore_Inf",
                              "P_Wind_Onshore_Opt"],
    "Rooftop Capacity [GW]": ["A_Rooftop_Commercial", "A_Rooftop_Residential"],
}

STAMP = "2026-06-02"
AUTHOR = "Konstantin Loffler <kl@wip.tu-berlin.de>"
SOURCE = "GENeSYS-MOD.tools NA_restool"


# ---------------------------- timeseries -----------------------------------

def read_ts_csv(path):
    """Return (header_row, data_rows_as_lists). NA TS files have one header row."""
    with open(path, "r", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    return rows[0], rows[1:]


def load_na_columns(stem):
    """Merge 2018_northamerica_<stem>.csv + 2018_canada_<stem>.csv. Different
    stems for heating/cooling: 2018_<stem>_northamerica.csv / _canada.csv."""
    # find file naming
    candidates = [
        (os.path.join(RESTOOL, f"2018_northamerica_{stem}.csv"),
         os.path.join(RESTOOL, f"2018_canada_{stem}.csv")),
        (os.path.join(RESTOOL, f"2018_{stem}_northamerica.csv"),
         os.path.join(RESTOOL, f"2018_{stem}_canada.csv")),
    ]
    for us_path, ca_path in candidates:
        if os.path.exists(us_path) and os.path.exists(ca_path):
            us_hdr, us_rows = read_ts_csv(us_path)
            ca_hdr, ca_rows = read_ts_csv(ca_path)
            # Build per-hour, per-region dict
            out = {}  # hour_index (1..8760) -> {region: value}
            for i, row in enumerate(us_rows):
                hr = i + 1
                d = out.setdefault(hr, {})
                for col_idx, col_name in enumerate(us_hdr):
                    if col_name in NA_US:
                        d[col_name] = row[col_idx]
            for i, row in enumerate(ca_rows):
                hr = i + 1
                d = out.setdefault(hr, {})
                for col_idx, col_name in enumerate(ca_hdr):
                    if col_name == "Canada":
                        d[col_name] = row[col_idx]
            return out
    print(f"  WARN: no restool file found for stem '{stem}'")
    return None


def update_ts_file(target_folder, na_data):
    path = os.path.join(TS_DIR, target_folder, f"{target_folder}.csv")
    if not os.path.exists(path):
        print(f"  SKIP {target_folder}: target CSV missing")
        return
    with open(path, "r", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    # rows[0] = source line, rows[1] = header (HOUR, region...), rows[2:] = data
    header = rows[1]
    col_idx = {name: idx for idx, name in enumerate(header)}
    na_cols_present = [r for r in NA_ALL if r in col_idx]
    if not na_cols_present:
        print(f"  SKIP {target_folder}: no NA cols in header")
        return
    n_updated = 0
    for data_row in rows[2:]:
        try:
            hr = int(data_row[0])
        except (ValueError, IndexError):
            continue
        if hr not in na_data:
            continue
        for r in na_cols_present:
            if r in na_data[hr]:
                data_row[col_idx[r]] = na_data[hr][r]
        n_updated += 1
    with open(path, "w", encoding="utf-8", newline="") as f:
        csv.writer(f).writerows(rows)
    print(f"  {target_folder}: updated {n_updated} rows × {len(na_cols_present)} cols")


def do_timeseries():
    print("=== Timeseries ===")
    for stem, target in TS_MAP.items():
        na_data = load_na_columns(stem)
        if na_data:
            update_ts_file(target, na_data)


# ---------------------------- potentials -----------------------------------

def read_potentials():
    """Returns {region: {column_name: float_value}}."""
    out = {}
    for fn in ("northamerica_potentials_combined.csv", "canada_potentials_combined.csv"):
        path = os.path.join(RESTOOL, fn)
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                r = row["region"]
                out[r] = {k: float(v) for k, v in row.items() if k != "region"}
    return out


def do_potentials():
    print("\n=== TotalAnnualMaxCapacity (renewables, 2035+) ===")
    pots = read_potentials()
    # Read existing CSV
    with open(MAXCAP_CSV, "r", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    header = rows[0]
    # Build set of (region, tech) we will rewrite
    targets = set()
    for col, techs in POTENTIAL_MAP.items():
        for t in techs:
            for r in NA_ALL:
                targets.add((r, t))
    # Drop existing rows whose (region, tech, year) match our target with year in FUTURE_YRS or 'All'
    kept = [header]
    dropped = 0
    for row in rows[1:]:
        if len(row) < 4:
            kept.append(row); continue
        rgn, tech, year, val = row[0], row[1], row[2], row[3]
        if (rgn, tech) in targets and (year == "All" or year in {str(y) for y in FUTURE_YRS} or year in {str(y) for y in KEEP_YRS}):
            # if "All": split into two epochs (preserve old value for KEEP_YRS, replace for FUTURE_YRS)
            if year == "All":
                try:
                    old_val = float(val)
                except ValueError:
                    old_val = None
                if old_val is not None:
                    for y in KEEP_YRS:
                        kept.append([rgn, tech, str(y), str(old_val), "", "GW",
                                     f"preserved from prior 'All' entry",
                                     STAMP, AUTHOR])
                dropped += 1
                continue
            # explicit year row inside our target set: drop (will rewrite below or preserve via KEEP_YRS)
            if year in {str(y) for y in FUTURE_YRS}:
                dropped += 1
                continue
            # year in KEEP_YRS: keep as is
            kept.append(row)
        else:
            kept.append(row)
    # Append new FUTURE_YRS rows
    added = 0
    for col, techs in POTENTIAL_MAP.items():
        for r in NA_ALL:
            if r not in pots:
                continue
            if col not in pots[r]:
                continue
            cap = round(pots[r][col], 3)
            for t in techs:
                for y in FUTURE_YRS:
                    kept.append([r, t, str(y), str(cap), "", "GW", SOURCE, STAMP, AUTHOR])
                    added += 1
    # Write back
    with open(MAXCAP_CSV, "w", encoding="utf-8", newline="") as f:
        csv.writer(f).writerows(kept)
    print(f"  dropped {dropped} existing rows, added {added} new rows (regions×techs×{len(FUTURE_YRS)} years)")


if __name__ == "__main__":
    do_timeseries()
    do_potentials()
    print("\nDone.")
