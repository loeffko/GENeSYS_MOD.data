"""Rebuild the North-American trade routes in Par_TradeRoute.csv so that only
GEOGRAPHICALLY ADJACENT region pairs have a route, with the great-circle distance (km)
between region centroids as the Value (Fuel == 'All' rows -- the inter-node distance the
trade equations use).

The previous dummy topology contained non-adjacent pairs (e.g. California-NewYork); this
script DROPS all existing NA-NA 'All' rows and writes fresh directed rows (both
directions) only for the adjacency list below. ETS rows and all EU rows are untouched.

Centroids are approximate ISO/pool load-area centers (lat, lon). Adjust if needed.

Usage:  python NA_inputs/add_trade_distances.py            # dry-run, prints adjacency+matrix
        python NA_inputs/add_trade_distances.py --apply
"""
import os, sys, math
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_REPO = os.path.normpath(os.path.join(HERE, ".."))
CSV = os.path.join(DATA_REPO, "Data", "Parameters", "Par_TradeRoute", "Par_TradeRoute.csv")
apply = "--apply" in sys.argv

CENTROIDS = {
    "California": (37.0, -119.5),
    "WECC":       (41.0, -112.0),
    "SPP":        (38.5,  -97.5),
    "MISO":       (41.5,  -90.5),
    "ERCOT":      (31.0,  -99.0),
    "SERC":       (34.5,  -85.5),
    "PJM":        (39.8,  -80.0),
    "NewYork":    (42.9,  -75.5),
    "NewEngland": (43.7,  -71.5),
    "Canada":     (47.0,  -80.0),
}
NA = list(CENTROIDS)

# Undirected geographically-adjacent pairs (shared footprint border).
ADJACENCY = [
    ("California", "WECC"),
    ("WECC", "SPP"), ("WECC", "MISO"), ("WECC", "ERCOT"), ("WECC", "Canada"),
    ("SPP", "ERCOT"), ("SPP", "MISO"), ("SPP", "SERC"),
    ("MISO", "ERCOT"), ("MISO", "SERC"), ("MISO", "PJM"), ("MISO", "Canada"),
    ("SERC", "PJM"),
    ("PJM", "NewYork"), ("PJM", "Canada"),
    ("NewYork", "NewEngland"), ("NewYork", "Canada"),
    ("NewEngland", "Canada"),
]


def haversine(a, b):
    R = 6371.0
    lat1, lon1 = map(math.radians, CENTROIDS[a])
    lat2, lon2 = map(math.radians, CENTROIDS[b])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return round(2 * R * math.asin(math.sqrt(h)))


def main():
    df = pd.read_csv(CSV)
    df = df.rename(columns={"Unnamed: 4": ""})

    # drop ALL existing NA-NA 'All' rows (rebuild from adjacency)
    drop = df["Region"].isin(NA) & df["Region.1"].isin(NA) & (df["Fuel"] == "All")
    n_drop = int(drop.sum())
    df = df[~drop]

    # build fresh directed rows for adjacent pairs (both directions)
    new = []
    for a, b in ADJACENCY:
        d = haversine(a, b)
        for x, y in ((a, b), (b, a)):
            row = {c: "" for c in df.columns}
            row.update({"Region": x, "Region.1": y, "Fuel": "All", "Value": d,
                        "Unit": "km", "Source": "great-circle between region centroids",
                        "Updated at": "2026-05-28",
                        "Updated by": "Konstantin Loffler <kl@wip.tu-berlin.de>"})
            new.append(row)
    if apply:
        df = pd.concat([df, pd.DataFrame(new)], ignore_index=True)
        df.to_csv(CSV, index=False)

    # report
    print("Adjacency (undirected) + distance km:")
    for a, b in ADJACENCY:
        print(f"  {a:11s} <-> {b:11s} {haversine(a,b):>5d}")
    print(f"\n{'APPLIED' if apply else 'DRY-RUN'}: dropped {n_drop} old NA 'All' rows, "
          f"{'added' if apply else 'would add'} {len(new)} directed rows "
          f"({len(ADJACENCY)} adjacent pairs x2).")
    if not apply:
        print("(use --apply to write)")


if __name__ == "__main__":
    main()
