# -*- coding: utf-8 -*-
"""US-market cost data from the FEL2026 LCOE model -> NA regional parameter rows.

Writes per-NA-region rows (never region World, so the EU base data is
untouched) for years 2025-2040 into:
  - Par_CapitalCost      (CAPEX, MEUR/GW == EUR/kW)
  - Par_FixedCost        (Fixed OPEX, MEUR/GW/yr == EUR/kW/yr)
  - Par_TechnologyDiscountRate  (WACC, fraction)
  - Par_VariableCost     (Z_Import_Gas Henry-Hub year path, MEUR/PJ — aligns
                          the INVEST-side gas price with the dispatch layer;
                          the dispatch year-multiplier is retired to 1.0)

Technology mapping (LCOE tech -> model techs):
  Gas CCGT   -> P_Gas_CCGT            Coal -> P_Coal_Hardcoal, P_Coal_Lignite
  Gas OCGT   -> P_Gas_OCGT            PV: Utility scale (x learning mult)
  Recip engines (Customized sheet)         -> P_PV_Utility_Opt/Avg/Inf
             -> P_Gas_Engines         PV: Residential/Commercial
  Wind Onshore -> P_Wind_Onshore_*         -> P_PV_Rooftop_Commercial
  Wind Offshore -> anchored on P_Wind_Offshore_Transitional; Shallow/Deep
                   scaled by the base-CSV depth ratio per year (FOM uniform)

NOT imported (documented in LCOE_Model_v1.4_issues_2026-07-23.md and
DATA_REVIEW_2026-07-23.md): Nuclear/SMR (multiplier double-count unresolved;
deliberate 10000 uprate of 2026-06 stands), Geothermal (different asset
class than EGS), SOFC (repo carries a newer Bloom-sourced row set,
2026-07-04), Gas Steam / Oil / Hydro / storage (no LCOE data). WACC proxies:
P_Gas_CCGT_Residual & P_Gas_Steam = CCGT 0.065; P_Gas_Engines = OCGT 0.075
(the Customized-sheet 0.095 is a scenario-playground cell). Canada gets the
same US-market rows (regional fuel/market basis is handled in the dispatch
layer).

Usage: python NA_inputs/add_lcoe_costs.py [--apply] [--scenario-subdir NAME]
"""
import os
import sys
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lcoe_reader

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, ".."))
PARDIR = os.path.join(REPO, "Data", "Parameters")
LCOE_XLSX = os.path.join(HERE, "260618 LCOE_Model_FEL26_v1.4.xlsx")

APPLY = "--apply" in sys.argv
SUBDIR = None
if "--scenario-subdir" in sys.argv:
    SUBDIR = sys.argv[sys.argv.index("--scenario-subdir") + 1]

NA_REGIONS = ["California", "WECC", "ERCOT", "SPP", "MISO", "SERC", "PJM",
              "NewYork", "NewEngland", "Canada"]
YEARS = list(range(2025, 2041))
TODAY = "2026-07-23"
WHO = "Konstantin Loffler <kl@wip.tu-berlin.de>"
SRC = lcoe_reader.SOURCE_LABEL

# Recip-engine values live only on the Customized_LCOE SOFC US sheet.
ENGINE_CAPEX, ENGINE_FOM = 3125.0, 29.0

WACC_US = {
    "P_Gas_CCGT": 0.065, "P_Gas_CCGT_Residual": 0.065, "P_Gas_Steam": 0.065,
    "P_Gas_OCGT": 0.075, "P_Gas_Engines": 0.075,
    "P_Coal_Hardcoal": 0.085, "P_Coal_Lignite": 0.085,
    "P_Nuclear": 0.085, "P_Nuclear_SMR": 0.085,
    "P_PV_Utility_Opt": 0.05, "P_PV_Utility_Avg": 0.05, "P_PV_Utility_Inf": 0.05,
    "P_PV_Rooftop_Commercial": 0.05,
    "P_Wind_Onshore_Opt": 0.055, "P_Wind_Onshore_Avg": 0.055, "P_Wind_Onshore_Inf": 0.055,
    "P_Wind_Offshore_Shallow": 0.07, "P_Wind_Offshore_Transitional": 0.07,
    "P_Wind_Offshore_Deep": 0.07,
    "P_EGS_R1": 0.07, "P_EGS_R2": 0.07, "P_EGS_R3": 0.07, "P_EGS_R4": 0.07,
    "P_SOFC": 0.07,
}
WACC_NOTE = {
    "P_Gas_CCGT_Residual": "CCGT proxy", "P_Gas_Steam": "CCGT proxy",
    "P_Gas_Engines": "OCGT proxy",
    "P_EGS_R1": "LCOE Geothermal WACC (costs not imported)",
    "P_EGS_R2": "LCOE Geothermal WACC (costs not imported)",
    "P_EGS_R3": "LCOE Geothermal WACC (costs not imported)",
    "P_EGS_R4": "LCOE Geothermal WACC (costs not imported)",
}


def _csv_path(par):
    if SUBDIR:
        d = os.path.join(PARDIR, par, SUBDIR)
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, par + ".csv")
    return os.path.join(PARDIR, par, par + ".csv")


def _load(par):
    p = _csv_path(par)
    if os.path.exists(p):
        return pd.read_csv(p, dtype=str, keep_default_na=False)
    base = pd.read_csv(os.path.join(PARDIR, par, par + ".csv"),
                       dtype=str, keep_default_na=False)
    return base.iloc[0:0].copy()


def _save(df, par):
    p = _csv_path(par)
    hdr = [("" if c.startswith("Unnamed") else c) for c in df.columns]
    df.to_csv(p, index=False, header=hdr, lineterminator="\n")


def upsert(df, rows, keycols):
    add = pd.DataFrame(rows)
    for c in df.columns:
        if c not in add.columns:
            add[c] = ""
    add = add[df.columns.tolist()]
    keys = set(map(tuple, add[keycols].values.tolist()))
    keep = ~df[keycols].apply(tuple, axis=1).isin(keys)
    return pd.concat([df[keep], add], ignore_index=True), int((~keep).sum())


def cost_rows(tech, vals, unit, note=""):
    src = SRC + (f" ({note})" if note else "")
    return [{"Region": r, "Technology": tech, "Year": str(y),
             "Value": f"{vals[y]:.6g}", "Unit": unit, "Source": src,
             "Updated at": TODAY, "Updated by": WHO}
            for r in NA_REGIONS for y in YEARS]


def main():
    data = lcoe_reader.load(LCOE_XLSX)
    S = lambda tech, kpi: lcoe_reader.series(data, "USA", tech, kpi, YEARS)
    pvmult = lcoe_reader.pv_learning(data, "USA", YEARS)

    # ---------- CAPEX ----------
    capex = {}
    capex["P_Gas_CCGT"] = (S("Gas CCGT", "CAPEX"), "")
    capex["P_Gas_OCGT"] = (S("Gas OCGT", "CAPEX"), "")
    capex["P_Gas_Engines"] = ({y: ENGINE_CAPEX for y in YEARS},
                              "Recip engines, Customized_LCOE SOFC US sheet")
    for t in ("P_Coal_Hardcoal", "P_Coal_Lignite"):
        capex[t] = (S("Coal", "CAPEX"), "LCOE 'Coal' applied to both coal techs")
    pv = S("PV: Utility scale", "CAPEX")
    pv = {y: pv[y] * pvmult[y] for y in YEARS}
    for t in ("P_PV_Utility_Opt", "P_PV_Utility_Avg", "P_PV_Utility_Inf"):
        capex[t] = (pv, "planned x PV learning multiplier")
    capex["P_PV_Rooftop_Commercial"] = (S("PV: Residential/Commercial", "CAPEX"), "")
    onsh = S("Wind Onshore", "CAPEX")
    for t in ("P_Wind_Onshore_Opt", "P_Wind_Onshore_Avg", "P_Wind_Onshore_Inf"):
        capex[t] = (onsh, "")
    # offshore: anchor Transitional, keep the base depth-cost structure
    off = S("Wind Offshore", "CAPEX")
    base_cc = pd.read_csv(os.path.join(PARDIR, "Par_CapitalCost", "Par_CapitalCost.csv"),
                          dtype=str, keep_default_na=False)
    base_cc = base_cc[base_cc.Region == "World"]
    def base_series(tech):
        sub = base_cc[base_cc.Technology == tech]
        s = {int(r.Year): float(r.Value) for r in sub.itertuples()
             if str(r.Year).isdigit() and r.Value}
        known = sorted(s)
        def at(y):
            if y in s: return s[y]
            lo = [k for k in known if k < y]; hi = [k for k in known if k > y]
            if lo and hi:
                a, b = lo[-1], hi[0]
                return s[a] + (s[b]-s[a])*(y-a)/(b-a)
            return s[lo[-1]] if lo else s[hi[0]]
        return {y: at(y) for y in YEARS}
    trans = base_series("P_Wind_Offshore_Transitional")
    capex["P_Wind_Offshore_Transitional"] = (off, "")
    for t in ("P_Wind_Offshore_Shallow", "P_Wind_Offshore_Deep"):
        ratio = base_series(t)
        capex[t] = ({y: off[y] * ratio[y] / trans[y] for y in YEARS},
                    "Transitional anchor x base depth ratio")

    # ---------- Fixed OPEX ----------
    fom = {}
    fom["P_Gas_CCGT"] = (S("Gas CCGT", "Fixed OPEX"), "")
    fom["P_Gas_OCGT"] = (S("Gas OCGT", "Fixed OPEX"), "")
    fom["P_Gas_Engines"] = ({y: ENGINE_FOM for y in YEARS},
                            "Recip engines, Customized_LCOE SOFC US sheet")
    for t in ("P_Coal_Hardcoal", "P_Coal_Lignite"):
        fom[t] = (S("Coal", "Fixed OPEX"), "LCOE 'Coal' applied to both coal techs")
    for t in ("P_PV_Utility_Opt", "P_PV_Utility_Avg", "P_PV_Utility_Inf"):
        fom[t] = (S("PV: Utility scale", "Fixed OPEX"), "")
    fom["P_PV_Rooftop_Commercial"] = (S("PV: Residential/Commercial", "Fixed OPEX"), "")
    for t in ("P_Wind_Onshore_Opt", "P_Wind_Onshore_Avg", "P_Wind_Onshore_Inf"):
        fom[t] = (S("Wind Onshore", "Fixed OPEX"), "")
    for t in ("P_Wind_Offshore_Shallow", "P_Wind_Offshore_Transitional",
              "P_Wind_Offshore_Deep"):
        fom[t] = (S("Wind Offshore", "Fixed OPEX"), "uniform across depth classes")

    # ---------- Henry-Hub gas year path (invest side) ----------
    # LCOE US gas 'Fuel costs' EUR/MWh(th) -> MEUR/PJ ( /3.6 )
    gas = S("Gas CCGT", "Fuel costs")
    gas_rows = [{"Region": r, "Technology": "Z_Import_Gas",
                 "Mode_of_operation": "1", "Year": str(y),
                 "Value": f"{gas[y]/3.6:.6g}", "Unit": "MEUR/PJ",
                 "Source": SRC + " (US gas macro = HH forward path; invest side "
                           "aligned with dispatch, dispatch year-multiplier retired)",
                 "Updated at": TODAY, "Updated by": WHO}
                for r in NA_REGIONS for y in YEARS]

    # ---------- WACC ----------
    wacc_rows = [{"Region": r, "Technology": t, "Value": f"{v:g}",
                  "Unit": "Fraction",
                  "Source": SRC + (f" ({WACC_NOTE[t]})" if t in WACC_NOTE else ""),
                  "Updated at": TODAY, "Updated by": WHO}
                 for r in NA_REGIONS for t, v in sorted(WACC_US.items())]

    plan = [("Par_CapitalCost", capex, "MEUR/GW", ["Region", "Technology", "Year"]),
            ("Par_FixedCost", fom, "MEUR/GW", ["Region", "Technology", "Year"])]
    total = 0
    for par, table, unit, keys in plan:
        rows = []
        for t, (vals, note) in sorted(table.items()):
            rows += cost_rows(t, vals, unit, note)
        df = _load(par)
        df, replaced = upsert(df, rows, keys)
        total += len(rows)
        print(f"{par}: +{len(rows)} rows ({replaced} replaced) "
              f"-> {_csv_path(par) if SUBDIR else 'base CSV'}")
        if APPLY:
            _save(df, par)
    df = _load("Par_VariableCost")
    df, replaced = upsert(df, gas_rows, ["Region", "Technology", "Mode_of_operation", "Year"])
    print(f"Par_VariableCost: +{len(gas_rows)} Z_Import_Gas HH rows ({replaced} replaced)")
    if APPLY:
        _save(df, "Par_VariableCost")
    df = _load("Par_TechnologyDiscountRate")
    df, replaced = upsert(df, wacc_rows, ["Region", "Technology"])
    print(f"Par_TechnologyDiscountRate: +{len(wacc_rows)} WACC rows ({replaced} replaced)")
    if APPLY:
        _save(df, "Par_TechnologyDiscountRate")
    print(("APPLIED" if APPLY else "DRY-RUN") +
          f" — {total + len(gas_rows) + len(wacc_rows)} rows, "
          f"scenario-subdir={SUBDIR or '(base)'}")


if __name__ == "__main__":
    main()
