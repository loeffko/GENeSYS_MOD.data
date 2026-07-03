"""Regionalize the INVESTMENT model's gas VariableCost from the dispatch fuel
config (single source of truth: Data/Dispatch/Par_DispatchFuelCostFactor.csv,
the researched hub-basis multipliers vs Henry Hub).

The base VariableCost rows are World-inherited (one price everywhere), which
prices Canadian gas ~4-5x AECO: Canadian CCGTs were built (funnel floor) but
ran at CF ~0.2 while the CER expects 80-110 TWh of gas generation. This script
writes per-region VariableCost rows for the gas techs as
    World value x annual fuel factor
for the regions listed on the command line (default: Canada only - the US
factors are milder and change the whole US price structure; enable explicitly
with e.g. --regions Canada ERCOT NewEngland ... when wanted).

Approximation: the factor is applied to the WHOLE VariableCost (fuel + VOM);
VOM is a small share (~10%) of a gas plant's VC, so the error is ~2-3%.

Idempotent. Run:  python NA_inputs/add_regional_fuel_costs.py [--apply]
                  [--regions Canada ...]
"""
import os
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_REPO = os.path.normpath(os.path.join(HERE, ".."))
VC = os.path.join(DATA_REPO, "Data", "Parameters", "Par_VariableCost", "Par_VariableCost.csv")
FF = os.path.join(DATA_REPO, "Data", "Dispatch", "Par_DispatchFuelCostFactor.csv")
GAS_TECHS = ["P_Gas_CCGT", "P_Gas_CCGT_Residual", "P_Gas_OCGT", "P_Gas_Steam", "P_Gas_Engines"]
apply = "--apply" in sys.argv
regions = sys.argv[sys.argv.index("--regions") + 1:] if "--regions" in sys.argv else ["Canada"]
regions = [r for r in regions if not r.startswith("--")] or ["Canada"]
DATE, WHO = "2026-07-03", "Konstantin Loffler <kl@wip.tu-berlin.de>"


def annual_gas_factor(region):
    """Volume-weighted annual gas factor from the dispatch config (months rows
    weighted by month count; the all-year row covers the remaining months)."""
    ff = pd.read_csv(FF)
    ff.columns = ["" if str(c).startswith("Unnamed") else c for c in ff.columns]
    rows = ff[(ff.Region == region) & (ff.Fuel == "Gas")]
    if rows.empty:
        return None
    monthly, covered = 0.0, 0
    default = None
    for _, r in rows.iterrows():
        m = str(r.get("Months", "") or "")
        if m.strip():
            n = len([x for x in m.split(",") if x.strip()])
            monthly += float(r.Value) * n
            covered += n
        else:
            default = float(r.Value)
    if default is None:
        return monthly / covered if covered else None
    return (monthly + default * (12 - covered)) / 12.0


def main():
    vc = pd.read_csv(VC)
    vc.columns = ["" if str(c).startswith("Unnamed") else c for c in vc.columns]
    world = vc[(vc.Region == "World") & (vc.Technology.isin(GAS_TECHS))]
    out_rows = []
    for region in regions:
        f = annual_gas_factor(region)
        if f is None:
            print(f"  {region}: no gas factor in {os.path.basename(FF)} - skipped")
            continue
        vc = vc[~((vc.Region == region) & (vc.Technology.isin(GAS_TECHS)))]  # idempotent
        for _, r in world.iterrows():
            row = r.copy()
            row["Region"] = region
            row["Value"] = round(float(r.Value) * f, 6)
            row["Source"] = (f"World VariableCost x {f:.3f} regional gas basis "
                             f"(Par_DispatchFuelCostFactor {region}/Gas, annual avg)")
            row["Updated at"] = DATE
            row["Updated by"] = WHO
            out_rows.append(row)
        print(f"  {region}: gas factor {f:.3f} -> {len(world)} VariableCost rows")
    if out_rows:
        vc = pd.concat([vc, pd.DataFrame(out_rows)], ignore_index=True)
        if apply:
            vc.to_csv(VC, index=False, lineterminator="\n")
    print("APPLIED" if apply else "DRY-RUN (use --apply)")


if __name__ == "__main__":
    main()
