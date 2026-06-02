# -*- coding: utf-8 -*-
"""Integrate NA_restool TIMESERIES into the GENeSYS-MOD data CSVs.

Overwrites the North-America region columns (9 US ISOs + Canada) in each
`Data/Timeseries/TS_<TECH>/TS_<TECH>.csv` with the values produced by the
restool. Both `2018_northamerica_*` (9 ISOs) and `2018_canada_*` files are
merged into the same target. Includes the dedicated TS_PV_ROOFTOP profile
used by the NA rooftop PV techs.

Run independently of the potentials updater (`add_na_restool_potentials.py`)
or together via `add_na_restool_full.py`.
"""
import csv
import os

HERE = os.path.dirname(os.path.abspath(__file__))
RESTOOL = os.path.join(HERE, "NA_restool")
TS_DIR  = os.path.join(HERE, "Data", "Timeseries")

NA_US  = ["California", "ERCOT", "MISO", "NewEngland", "NewYork",
          "PJM", "SERC", "SPP", "WECC"]
NA_ALL = NA_US + ["Canada"]

# restool file stem -> target TS folder.
# NB: in the NA power-only data flow Power demand is split into end-use buckets
# (POWER_BUILDINGS_HEAT, _COOLING, BEVS, ...), so the restool heating/cooling
# profiles belong in those NA-specific TS files, NOT in the generic TS_HEAT_LOW
# / TS_COOL_LOW which carry building-side heat demand for the full energy
# system runs.
TS_MAP = {
    "usable_pv_avg":                      "TS_PV_AVG",
    "usable_pv_inf":                      "TS_PV_INF",
    "usable_pv_opt":                      "TS_PV_OPT",
    "usable_pv_rooftop_avg":              "TS_PV_ROOFTOP",
    "usable_wind_onshore_avg":            "TS_WIND_ONSHORE_AVG",
    "usable_wind_onshore_inf":            "TS_WIND_ONSHORE_INF",
    "usable_wind_onshore_opt":            "TS_WIND_ONSHORE_OPT",
    "usable_wind_offshore_deep":          "TS_WIND_OFFSHORE_DEEP",
    "usable_wind_offshore_shallow":       "TS_WIND_OFFSHORE_SHALLOW",
    "usable_wind_offshore_transitional":  "TS_WIND_OFFSHORE",
    "heating":                            "TS_POWER_BUILDINGS_HEAT",
    "cooling":                            "TS_POWER_BUILDINGS_COOLING",
}

# Reset NA columns in these TS files back to 0 (earlier versions of this script
# mis-placed heating/cooling data into them; the move above leaves stale NA
# values that must be zeroed so a downstream re-conversion picks them up empty).
RESET_NA_COLS = ["TS_HEAT_LOW", "TS_COOL_LOW"]

# Special: copy NA columns of source -> NA columns of target (no restool file)
COPY_NA_COLS = [
    ("TS_MOBILITY_PSNG", "TS_POWER_BEVS"),  # power-only NA: BEV charging follows
                                            # the existing passenger-mobility profile
]


def read_ts_csv(path):
    with open(path, "r", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    return rows[0], rows[1:]


def load_na_columns(stem):
    """Merge 2018_northamerica_<stem>.csv + 2018_canada_<stem>.csv. Heating/
    cooling use the swapped pattern 2018_<stem>_northamerica/canada.csv."""
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
            out = {}
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


def reset_na_cols(target_folder, value="0"):
    """Set every NA region column to `value` in the target TS CSV."""
    path = os.path.join(TS_DIR, target_folder, f"{target_folder}.csv")
    if not os.path.exists(path):
        print(f"  SKIP reset {target_folder}: missing")
        return
    with open(path, "r", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    header = rows[1]
    col_idx = {n: i for i, n in enumerate(header)}
    na_cols = [r for r in NA_ALL if r in col_idx]
    if not na_cols:
        print(f"  SKIP reset {target_folder}: no NA cols")
        return
    for data_row in rows[2:]:
        for r in na_cols:
            data_row[col_idx[r]] = value
    with open(path, "w", encoding="utf-8", newline="") as f:
        csv.writer(f).writerows(rows)
    print(f"  reset {target_folder}: NA cols zeroed ({len(na_cols)} cols)")


def copy_na_cols(src_folder, dst_folder):
    """Copy NA region columns from src TS CSV to dst TS CSV."""
    src_path = os.path.join(TS_DIR, src_folder, f"{src_folder}.csv")
    dst_path = os.path.join(TS_DIR, dst_folder, f"{dst_folder}.csv")
    if not os.path.exists(src_path) or not os.path.exists(dst_path):
        print(f"  SKIP copy {src_folder}->{dst_folder}: missing endpoints")
        return
    with open(src_path, "r", encoding="utf-8") as f:
        src_rows = list(csv.reader(f))
    with open(dst_path, "r", encoding="utf-8") as f:
        dst_rows = list(csv.reader(f))
    src_hdr, dst_hdr = src_rows[1], dst_rows[1]
    src_idx = {n: i for i, n in enumerate(src_hdr)}
    dst_idx = {n: i for i, n in enumerate(dst_hdr)}
    na_cols = [r for r in NA_ALL if r in src_idx and r in dst_idx]
    if not na_cols:
        print(f"  SKIP copy {src_folder}->{dst_folder}: no shared NA cols")
        return
    for i, dst_row in enumerate(dst_rows[2:], start=2):
        src_row = src_rows[i]
        for r in na_cols:
            dst_row[dst_idx[r]] = src_row[src_idx[r]]
    with open(dst_path, "w", encoding="utf-8", newline="") as f:
        csv.writer(f).writerows(dst_rows)
    print(f"  copy {src_folder}->{dst_folder}: NA cols copied ({len(na_cols)} cols)")


def main():
    print("=== Timeseries (NA_restool) ===")
    for stem, target in TS_MAP.items():
        na_data = load_na_columns(stem)
        if na_data:
            update_ts_file(target, na_data)
    for target in RESET_NA_COLS:
        reset_na_cols(target)
    for src, dst in COPY_NA_COLS:
        copy_na_cols(src, dst)


if __name__ == "__main__":
    main()
    print("\nDone.")
