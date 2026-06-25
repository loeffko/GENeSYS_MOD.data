"""Load NA interregional transfer-capability projections
(NA_inputs/US IC capacity/outputs/transfer_capability_long.csv) into absolute
trade-capacity bounds the model reads as new parameters:

  Par_AnnualMinTradeCapacity  <- Low case   (floor)
  Par_AnnualMaxTradeCapacity  <- High case  (ceiling)

The model constraints TrCMin/TrCMax then let TotalTradeCapacity move within
[Low, High] per directed pair and year; the Central case is a reference, not enforced.

Also populates Par_TradeCapacityGrowthCosts for the NA Power pairs so the endogenous
expansion carries a cost. In the model the trade-expansion cost is
  NewCapacity[GW] * TradeCapacityGrowthCosts[M€/GWkm] * TradeRoute[km],
and the NA inter-node distances already live in Par_TradeRoute (add_trade_distances.py).

Units / conventions:
  - IC ttc_mw is MW; model trade capacity is GW  -> divide by 1000. Fuel = 'Power'.
  - Milestone years 2025/2030/2035/2040 are linearly interpolated to every modelled
    year 2025..2040 (create_daa does not interpolate; a gap year would force the
    capacity bound to 0).
  - Directional: region_from -> region_to is stored separately (A->B != B->A).
  - The start year (2025) is pinned by TrC2a to Par_TradeCapacity, and TrCMin/TrCMax
    only bind for year > start, so the 2025 bound rows are harmless.

Idempotent: existing NA-NA 'Power' rows are removed from each target file before
appending. EU / MiddleEarth rows are untouched.

Run:  python NA_inputs/add_ic_trade_bounds.py            # dry-run
      python NA_inputs/add_ic_trade_bounds.py --apply
"""
import os, sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_REPO = os.path.normpath(os.path.join(HERE, ".."))
IC = os.path.join(HERE, "US IC capacity", "outputs", "transfer_capability_long.csv")
PARAMS = os.path.join(DATA_REPO, "Data", "Parameters")
apply = "--apply" in sys.argv

# IC node name -> model region name
NODE_MAP = {"CAISO": "California", "WECC": "WECC", "SPP": "SPP", "MISO": "MISO",
            "ERCOT": "ERCOT", "SERC": "SERC", "PJM": "PJM", "NYISO": "NewYork",
            "ISO-NE": "NewEngland", "Canada": "Canada"}
NA = set(NODE_MAP.values())
MILES = [2025, 2030, 2035, 2040]
YEARS = list(range(2025, 2041))                 # modelled years (annual)
GROWTH_COST = 0.444626714                        # M€/GWkm, Saadi et al. (2018) 10.1039/C7EE01987D
DATE, WHO = "2026-06-25", "Konstantin Loffler <kl@wip.tu-berlin.de>"

BOUND_COLS = ["Region", "Region.1", "Fuel", "Year", "Value", "", "Unit", "Source", "Updated at", "Updated by"]
COST_COLS = ["Region", "Region2", "Fuel", "Value", "", "Unit", "Source", "Updated at", "Updated by"]


def bound_rows(df, case, source):
    """Interpolated annual GW rows for one case, directional (region_from->region_to)."""
    rows = []
    sub = df[df["case"] == case]
    for (rf, rt), g in sub.groupby(["region_from", "region_to"]):
        a, b = NODE_MAP.get(rf), NODE_MAP.get(rt)
        if a is None or b is None:
            continue
        s = g.set_index("year")["ttc_mw"]
        miles_mw = [float(s.get(y, np.nan)) for y in MILES]
        if any(np.isnan(miles_mw)):
            continue
        vals = np.interp(YEARS, MILES, miles_mw) / 1000.0     # MW -> GW
        for y, v in zip(YEARS, vals):
            rows.append({"Region": a, "Region.1": b, "Fuel": "Power", "Year": int(y),
                         "Value": round(float(v), 6), "": "", "Unit": "GW",
                         "Source": source, "Updated at": DATE, "Updated by": WHO})
    return rows


def write_param(param, new_rows, key2, cols):
    d = os.path.join(PARAMS, param)
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, param + ".csv")
    if os.path.exists(path):
        old = pd.read_csv(path)
        old = old.rename(columns={c: "" for c in old.columns if str(c).startswith("Unnamed")})
        drop = old["Region"].isin(NA) & old[key2].isin(NA) & (old["Fuel"] == "Power")
        nd = int(drop.sum())
        old = old[~drop]
        for c in cols:
            if c not in old.columns:
                old[c] = ""
        out = pd.concat([old[cols], pd.DataFrame(new_rows)[cols]], ignore_index=True)
    else:
        nd = 0
        out = pd.DataFrame(new_rows)[cols]
    if apply:
        out.to_csv(path, index=False)
    return nd, len(new_rows), path


def main():
    if not os.path.exists(IC):
        sys.exit("IC file not found: " + IC)
    df = pd.read_csv(IC)
    maxr = bound_rows(df, "High", "IC transfer capability, High/NTP ceiling (MW/1000)")
    minr = bound_rows(df, "Low",  "IC transfer capability, Low floor (MW/1000)")
    pairs = sorted({(r["Region"], r["Region.1"]) for r in maxr})
    cost_rows = [{"Region": a, "Region2": b, "Fuel": "Power", "Value": GROWTH_COST, "": "",
                  "Unit": "M€/GWkm", "Source": "Saadi et al. (2018) 10.1039/C7EE01987D",
                  "Updated at": DATE, "Updated by": WHO} for (a, b) in pairs]

    results = [
        ("Par_AnnualMaxTradeCapacity", write_param("Par_AnnualMaxTradeCapacity", maxr, "Region.1", BOUND_COLS)),
        ("Par_AnnualMinTradeCapacity", write_param("Par_AnnualMinTradeCapacity", minr, "Region.1", BOUND_COLS)),
        ("Par_TradeCapacityGrowthCosts", write_param("Par_TradeCapacityGrowthCosts", cost_rows, "Region2", COST_COLS)),
    ]
    for name, (nd, na_, path) in results:
        print(f"{name:28s}: -{nd} old NA-Power / +{na_} new")
    print(f"\n{len(pairs)} directed NA pairs; years {YEARS[0]}..{YEARS[-1]} (interpolated from {MILES}).")
    print("APPLIED." if apply else "DRY-RUN — use --apply to write.")


if __name__ == "__main__":
    main()
