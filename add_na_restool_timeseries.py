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

# restool file stem -> target TS folder
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
    # heat/cool live in HEAT_LOW / COOL_LOW (closest existing TS).
    "heating":                            "TS_HEAT_LOW",
    "cooling":                            "TS_COOL_LOW",
}


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


def main():
    print("=== Timeseries (NA_restool) ===")
    for stem, target in TS_MAP.items():
        na_data = load_na_columns(stem)
        if na_data:
            update_ts_file(target, na_data)


if __name__ == "__main__":
    main()
    print("\nDone.")
