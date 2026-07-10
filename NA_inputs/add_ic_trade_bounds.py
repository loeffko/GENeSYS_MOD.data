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
# Per-corridor cap on AnnualMax expansion pace. The *buildable* interregional pace is the
# binding realism limit, not the NTP cost-optimal High ceiling: Princeton REPEAT puts the
# realistic-accelerated HV pace at ~2.3%/yr, DOE/NTP put the 2035-clean *need* at +2..5x.
# Cap each corridor's AnnualMax growth at IC_GROWTH_RATE/yr off its existing capacity
# (corridor = max of both directions); the IC High value stays the hard ceiling. New
# (0-capacity) corridors get NEW_CORRIDOR_SEED so a fresh tie can still grow modestly.
IC_GROWTH_RATE = 0.04
# sensitivity override:  --growth 0.025  |  --growth none (no pace cap; the IC
# High ceiling and existing/commissioned floors still apply)
if "--growth" in sys.argv:
    _g = sys.argv[sys.argv.index("--growth") + 1]
    IC_GROWTH_RATE = None if _g.lower() == "none" else float(_g)        # 4%/yr per corridor (3% grew the grid too slowly, 5% a tad much):
                             # above Princeton's ~2.3%/yr realistic-accelerated pace, within the
                             # DOE/NTP +2..5x 2035-clean need band.
NEW_CORRIDOR_SEED = 2.0      # GW base for 0-capacity corridors so new ties aren't blocked
# --group-cap-mult <m>: also write Par_GroupAnnualMaxTradeCapacity rows — an
# AGGREGATE interconnection budget over the NorthAmerica region subset (TrC4):
# the sum of directed NA Power pair capacities grows linearly from the
# installed 2025 sum to m x that sum at 2040. Per-corridor %-pace caps throttle
# exactly the corridors an expansion scenario is about (grid_high at 4.7%/yr
# per corridor realized barely above base); a budget lets the optimiser pick
# the corridors. Start year exempt (TrC2a pins it).
GROUP_CAP_MULT = (float(sys.argv[sys.argv.index("--group-cap-mult") + 1])
                  if "--group-cap-mult" in sys.argv else None)
GROUP_CAP_SUBSET = "NorthAmerica"   # region subset (Par_TagRegionToSubsets)
GROUP_COLS = ["RegionSubset", "Fuel", "Year", "Value", "", "Unit", "Source", "Updated at", "Updated by"]
DATE, WHO = "2026-06-25", "Konstantin Loffler <kl@wip.tu-berlin.de>"

BOUND_COLS = ["Region", "Region.1", "Fuel", "Year", "Value", "", "Unit", "Source", "Updated at", "Updated by"]
COST_COLS = ["Region", "Region2", "Fuel", "Value", "", "Unit", "Source", "Updated at", "Updated by"]


TC = os.path.join(PARAMS, "Par_TradeCapacity", "Par_TradeCapacity.csv")


def read_existing_tradecapacity():
    """{(region, region2): 2025 GW} for NA Power pairs from Par_TradeCapacity.
    These are *installed* capacities; TotalTradeCapacity cannot retire (NewTradeCapacity
    >= 0), so the IC bounds (which are reliability-limited transfer capability and can be
    below the installed value) must be reconciled against them — see bound_rows."""
    if not os.path.exists(TC):
        return {}
    df = pd.read_csv(TC)
    key2 = "Region.1" if "Region.1" in df.columns else "Region2"
    out = {}
    for _, r in df.iterrows():
        if r["Region"] in NA and r[key2] in NA and str(r["Fuel"]) == "Power" and str(r["Year"]) == "2025":
            out[(r["Region"], r[key2])] = float(r["Value"])
    return out


CTC = os.path.join(PARAMS, "Par_CommissionedTradeCapacity", "Par_CommissionedTradeCapacity.csv")


def read_commissioned():
    """{(region, region2): {year: GW}} of exogenous Commissioned trade additions.
    These add to TotalTradeCapacity in TrC2b, so the ceiling must clear
    existing + cumulative Commissioned, not just the 2025 existing value."""
    if not os.path.exists(CTC):
        return {}
    df = pd.read_csv(CTC)
    key2 = "Region.1" if "Region.1" in df.columns else "Region2"
    out = {}
    for _, r in df.iterrows():
        if r["Region"] in NA and r[key2] in NA and str(r["Fuel"]) == "Power":
            try:
                y = int(float(str(r["Year"])))
            except (ValueError, TypeError):
                continue
            out.setdefault((r["Region"], r[key2]), {})[y] = float(r["Value"])
    return out


def bound_rows(df, case, source, existing, commissioned, mode):
    """Interpolated annual GW rows for one case, directional (region_from->region_to).

    Clamped against the existing installed capacity so the bounds never contradict the
    un-retirable start-year TradeCapacity:
      mode="max": ceiling = max(IC, existing + cumulative Commissioned) and
                  non-decreasing year-on-year (the model cannot drop below what is
                  already built or exogenously commissioned).
      mode="min": floor = min(IC, existing) so it never forces growth above the existing
                  capacity (which, with the symmetric-expansion constraint TrC6, could make
                  the opposite direction infeasible).
    """
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
        ex = existing.get((a, b), 0.0)
        comm = commissioned.get((a, b), {})
        # pace base = this corridor's own existing capacity (directional, matching the
        # model's directional TradeCapacity); 0-capacity (new) directed ties use a seed.
        corridor_base = ex if ex > 0 else NEW_CORRIDOR_SEED
        vals = np.interp(YEARS, MILES, miles_mw) / 1000.0     # MW -> GW
        run = 0.0
        cumcomm = 0.0
        for y, v in zip(YEARS, vals):
            cumcomm += comm.get(y, 0.0)
            if mode == "max":
                if IC_GROWTH_RATE is not None:
                    pace = corridor_base * (1.0 + IC_GROWTH_RATE) ** (y - 2025)  # buildable pace
                    v = min(v, pace)            # cap the IC High ceiling at the realistic pace
                v = max(v, ex + cumcomm, run)   # but never below existing+commissioned; non-decreasing
                run = v
            else:
                v = min(v, ex)                  # floor never forces growth above existing
            rows.append({"Region": a, "Region.1": b, "Fuel": "Power", "Year": int(y),
                         "Value": round(float(v), 6), "": "", "Unit": "GW",
                         "Source": source, "Updated at": DATE, "Updated by": WHO})
    return rows


SCENARIO_SUBDIR = sys.argv[sys.argv.index("--scenario-subdir") + 1] if "--scenario-subdir" in sys.argv else None


def write_param(param, new_rows, key2, cols):
    d = os.path.join(PARAMS, param)
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, param + ".csv")
    if SCENARIO_SUBDIR:
        # scenario mode: base CSV untouched; rows go to Par_X/<subdir>/ and the
        # conversion upserts them over the base (full NA row set -> no leakage)
        outdir = os.path.join(d, SCENARIO_SUBDIR)
        path = os.path.join(outdir, param + ".csv")
        out = pd.DataFrame(new_rows)[cols]
        if apply:
            os.makedirs(outdir, exist_ok=True)
            out.to_csv(path, index=False, lineterminator="\n")
        return 0, len(new_rows), path
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
    existing = read_existing_tradecapacity()
    commissioned = read_commissioned()
    maxr = bound_rows(df, "High", "IC transfer capability, High/NTP ceiling (MW/1000), floored at existing+commissioned", existing, commissioned, "max")
    minr = bound_rows(df, "Low",  "IC transfer capability, Low floor (MW/1000), capped at existing", existing, commissioned, "min")
    pairs = sorted({(r["Region"], r["Region.1"]) for r in maxr})
    cost_rows = [{"Region": a, "Region2": b, "Fuel": "Power", "Value": GROWTH_COST, "": "",
                  "Unit": "M€/GWkm", "Source": "Saadi et al. (2018) 10.1039/C7EE01987D",
                  "Updated at": DATE, "Updated by": WHO} for (a, b) in pairs]

    results = [
        ("Par_AnnualMaxTradeCapacity", write_param("Par_AnnualMaxTradeCapacity", maxr, "Region.1", BOUND_COLS)),
        ("Par_AnnualMinTradeCapacity", write_param("Par_AnnualMinTradeCapacity", minr, "Region.1", BOUND_COLS)),
        ("Par_TradeCapacityGrowthCosts", write_param("Par_TradeCapacityGrowthCosts", cost_rows, "Region2", COST_COLS)),
    ]
    if GROUP_CAP_MULT is not None:
        if not SCENARIO_SUBDIR:
            sys.exit("--group-cap-mult is a scenario construct: pass --scenario-subdir")
        s0 = sum(existing.values())          # installed 2025, sum of directed pairs
        grp = [{"RegionSubset": GROUP_CAP_SUBSET, "Fuel": "Power", "Year": y,
                "Value": round(s0 * (1.0 + (GROUP_CAP_MULT - 1.0) * (y - 2025) / 15.0), 3),
                "": "", "Unit": "GW (sum of directed pairs)",
                "Source": f"aggregate IC budget: linear to {GROUP_CAP_MULT}x installed 2025 at 2040",
                "Updated at": DATE, "Updated by": WHO} for y in YEARS if y > 2025]
        results.append(("Par_GroupAnnualMaxTradeCapacity",
                        write_param("Par_GroupAnnualMaxTradeCapacity", grp, "Fuel", GROUP_COLS)))
        print(f"group cap: {GROUP_CAP_SUBSET} Power {s0:.1f} GW (2025, directed sum) "
              f"-> {s0 * GROUP_CAP_MULT:.1f} GW (2040)")
    for name, (nd, na_, path) in results:
        print(f"{name:28s}: -{nd} old NA-Power / +{na_} new")
    print(f"\n{len(pairs)} directed NA pairs; years {YEARS[0]}..{YEARS[-1]} (interpolated from {MILES}).")
    print("APPLIED." if apply else "DRY-RUN — use --apply to write.")


if __name__ == "__main__":
    main()
