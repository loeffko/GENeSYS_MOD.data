"""Build weather-year timeseries CSVs for the data conversion from the GIS &
Timeseries Tool's usable-coordinate capacity-factor output.

For each renewable TS family it reads
  <tools>/output/<year>/<year>_{northamerica,canada}_usable_<suffix>.csv
(columns: time + per-region CF), combines the US pools + Canada, drops Feb 29 in
leap years to align to the model's 8760 hours, assigns HOUR = 1..8760, and writes
  Data/Timeseries/TS_<NAME>/<year>/<year>_TS_<NAME>.csv
in the base TS format (row 0 = source line, row 1 = HOUR + region header). The data
conversion run with weather_year=<year> then merges these per region over the base
TS files (regions absent from a weather-year file fall back to the base).

Usage:  python NA_inputs/make_weather_year_ts.py 2012
"""
import os, sys
import pandas as pd

YEAR = sys.argv[1] if len(sys.argv) > 1 else "2012"
HERE = os.path.dirname(os.path.abspath(__file__))
DATA_REPO = os.path.normpath(os.path.join(HERE, ".."))
TOOLS_OUT = r"C:\Users\testbed\Documents\GENeSYSMOD.tools_SE\GIS_&_Timeseries_Tool\output"
TSDIR = os.path.join(DATA_REPO, "Data", "Timeseries")
SRC = os.path.join(TOOLS_OUT, YEAR)

# data-repo TS folder  <-  tool usable-CF suffix
MAP = {
    "TS_PV_OPT":               "pv_opt",
    "TS_PV_AVG":               "pv_avg",
    "TS_PV_INF":               "pv_inf",
    "TS_PV_ROOFTOP":           "pv_rooftop_avg",        # rooftop tech = single, use the avg-orientation variant
    "TS_WIND_ONSHORE_OPT":     "wind_onshore_opt",
    "TS_WIND_ONSHORE_AVG":     "wind_onshore_avg",
    "TS_WIND_ONSHORE_INF":     "wind_onshore_inf",
    "TS_WIND_OFFSHORE":        "wind_offshore_transitional",
    "TS_WIND_OFFSHORE_SHALLOW":"wind_offshore_shallow",
    "TS_WIND_OFFSHORE_DEEP":   "wind_offshore_deep",
}
HEADER0 = f"Source: GIS_&_Timeseries_Tool weather year {YEAR}; usable coordinates"


def load(suffix):
    na = pd.read_csv(os.path.join(SRC, f"{YEAR}_northamerica_usable_{suffix}.csv"))
    ca = pd.read_csv(os.path.join(SRC, f"{YEAR}_canada_usable_{suffix}.csv"))
    df = na.merge(ca, on="time", how="inner")
    df["time"] = pd.to_datetime(df["time"])
    df = df[~((df.time.dt.month == 2) & (df.time.dt.day == 29))]   # drop leap day -> 8760
    df = df.sort_values("time").reset_index(drop=True)
    assert len(df) == 8760, f"{suffix}: {len(df)} rows after leap-trim (expected 8760)"
    df.insert(0, "HOUR", range(1, len(df) + 1))
    return df.drop(columns=["time"])


def main():
    for tsfolder, suffix in MAP.items():
        df = load(suffix)
        outdir = os.path.join(TSDIR, tsfolder, YEAR)
        os.makedirs(outdir, exist_ok=True)
        path = os.path.join(outdir, f"{YEAR}_{tsfolder}.csv")
        with open(path, "w", newline="") as f:
            f.write(HEADER0 + "," * (df.shape[1] - 1) + "\n")
            df.to_csv(f, index=False)
        regs = [c for c in df.columns if c != "HOUR"]
        print(f"{tsfolder:26s} <- {suffix:28s} {df.shape[0]}h x {len(regs)} regions")
    print("done")


if __name__ == "__main__":
    main()
