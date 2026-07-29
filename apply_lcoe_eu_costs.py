# -*- coding: utf-8 -*-
"""One-time EU cost overwrite from the FEL2026 LCOE model (v1.4, 2026-06-18).

Overwrites the base World rows (the EU defaults, inherited by every EU
country — ready for the coming country-level EU version) in Par_CapitalCost,
Par_FixedCost with the LCOE model's 'All regions' planned values, and fills
Par_TechnologyDiscountRate with the LCOE per-technology WACCs (EU column).

Rules:
  - years 2025-2040: LCOE yearly values (PV utility x learning multiplier);
  - years 2045-2060: prior decline continued as a ratio on the new 2040 value
    (old_y / old_2040 x new_2040) — LCOE horizon ends 2040;
  - years <= 2021: untouched (historic vintages);
  - offshore wind: LCOE single series anchored on P_Wind_Offshore_Transitional,
    Shallow/Deep scaled by the pre-existing depth-cost ratio per year
    (Fixed OPEX uniform across depths, as in the LCOE file).

NOT overwritten (documented in LCOE_Model_v1.4_issues_2026-07-23.md):
  Nuclear + SMR (LCOE 'real/planned' multiplier double-count unresolved; the
  deliberate 10000 EUR/kW uprate of 2026-06 stands), Geothermal/EGS
  (different asset class in LCOE), SOFC (repo has newer Bloom-sourced data,
  2026-07-04), CCS variants (LCOE has no CCS capex adder + inverted CCS
  WACCs), Gas Engines (US-only sheet), Oil / Hydro / storage / VOM /
  efficiencies / EU fuel prices (missing or scenario-level in LCOE).

Usage: python apply_lcoe_eu_costs.py [--apply]
"""
import os
import sys
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "NA_inputs"))
import lcoe_reader

PARDIR = os.path.join(HERE, "Data", "Parameters")
LCOE_XLSX = os.path.join(HERE, "NA_inputs", "260618 LCOE_Model_FEL26_v1.4.xlsx")
APPLY = "--apply" in sys.argv
YEARS = list(range(2025, 2041))
CONT_YEARS = [2045, 2050, 2055, 2060]
TODAY = "2026-07-23"
WHO = "Konstantin Loffler <kl@wip.tu-berlin.de>"
SRC = lcoe_reader.SOURCE_LABEL

WACC_EU = {
    "P_Gas_CCGT": 0.065, "P_Gas_OCGT": 0.075,
    "P_Coal_Hardcoal": 0.085, "P_Coal_Lignite": 0.085,
    "P_Nuclear": 0.085, "P_Nuclear_SMR": 0.085,
    "P_PV_Utility_Opt": 0.05, "P_PV_Utility_Avg": 0.05, "P_PV_Utility_Inf": 0.05,
    "P_PV_Rooftop_Commercial": 0.05, "P_PV_Rooftop_Residential": 0.05,
    "P_Wind_Onshore_Opt": 0.055, "P_Wind_Onshore_Avg": 0.055, "P_Wind_Onshore_Inf": 0.055,
    "P_Wind_Offshore_Shallow": 0.055, "P_Wind_Offshore_Transitional": 0.055,
    "P_Wind_Offshore_Deep": 0.055,
    "P_Geothermal": 0.07, "P_EGS_R1": 0.07, "P_EGS_R2": 0.07,
    "P_EGS_R3": 0.07, "P_EGS_R4": 0.07, "P_SOFC": 0.07,
}

TECH_MAP_CAPEX = {}   # model tech -> (lcoe tech, note, pv_mult?)
for t in ("P_PV_Utility_Opt", "P_PV_Utility_Avg", "P_PV_Utility_Inf"):
    TECH_MAP_CAPEX[t] = ("PV: Utility scale", "planned x PV learning multiplier", True)
TECH_MAP_CAPEX.update({
    "P_Gas_CCGT": ("Gas CCGT", "", False),
    "P_Gas_OCGT": ("Gas OCGT", "", False),
    "P_Coal_Hardcoal": ("Coal", "LCOE 'Coal' applied to both coal techs", False),
    "P_Coal_Lignite": ("Coal", "LCOE 'Coal' applied to both coal techs", False),
    "P_PV_Rooftop_Commercial": ("PV: Residential/Commercial", "", False),
    "P_Wind_Onshore_Opt": ("Wind Onshore", "", False),
    "P_Wind_Onshore_Avg": ("Wind Onshore", "", False),
    "P_Wind_Onshore_Inf": ("Wind Onshore", "", False),
})
OFFSHORE = ("P_Wind_Offshore_Shallow", "P_Wind_Offshore_Transitional",
            "P_Wind_Offshore_Deep")


def load_csv(par):
    p = os.path.join(PARDIR, par, par + ".csv")
    raw_header = open(p, encoding="utf-8-sig").readline().rstrip("\n").rstrip("\r")
    df = pd.read_csv(p, dtype=str, keep_default_na=False)
    return df, p, raw_header


def save_csv(df, p, raw_header):
    import io
    out = io.StringIO()
    df.to_csv(out, index=False, header=False, lineterminator="\n")
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write(raw_header + "\n" + out.getvalue())


def world_series(df, tech):
    sub = df[(df.Region == "World") & (df.Technology == tech)]
    s = {int(r.Year): float(r.Value) for r in sub.itertuples()
         if str(r.Year).isdigit() and r.Value not in ("", "nan")}
    known = sorted(s)
    def at(y):
        if y in s: return s[y]
        lo = [k for k in known if k < y]; hi = [k for k in known if k > y]
        if lo and hi:
            a, b = lo[-1], hi[0]
            return s[a] + (s[b]-s[a])*(y-a)/(b-a)
        return s[lo[-1]] if lo else (s[hi[0]] if hi else None)
    return s, at


def overwrite(df, tech, newvals, note, stats):
    """Set World rows 2025-2040 to newvals; ratio-continue 2045-2060."""
    s, _ = world_series(df, tech)
    if not s:
        stats.append(f"  ! {tech}: no World rows found, skipped")
        return
    old2040 = s.get(2040)
    m_all = (df.Region == "World") & (df.Technology == tech)
    n = 0
    for idx in df[m_all].index:
        ystr = df.at[idx, "Year"]
        if not str(ystr).isdigit():
            continue
        y = int(ystr)
        if 2025 <= y <= 2040:
            df.at[idx, "Value"] = f"{newvals[y]:.6g}"
            df.at[idx, "Source"] = SRC + (f" ({note})" if note else "")
            df.at[idx, "Updated at"] = TODAY
            df.at[idx, "Updated by"] = WHO
            n += 1
        elif y in CONT_YEARS and old2040:
            cont = newvals[2040] * s.get(y, old2040) / old2040
            df.at[idx, "Value"] = f"{cont:.6g}"
            df.at[idx, "Source"] = (SRC + "; post-2040 extrapolated via prior "
                                    "decline ratio (LCOE horizon ends 2040)")
            df.at[idx, "Updated at"] = TODAY
            df.at[idx, "Updated by"] = WHO
            n += 1
    stats.append(f"  {tech}: {n} World rows overwritten"
                 + (f" ({note})" if note else ""))


def run_costfile(par, kpi, data, stats):
    df, p, hdr = load_csv(par)
    S = lambda tech: lcoe_reader.series(data, "All regions", tech, kpi, YEARS)
    pvmult = lcoe_reader.pv_learning(data, "All regions", YEARS)
    for tech, (ltech, note, use_mult) in TECH_MAP_CAPEX.items():
        vals = S(ltech)
        if vals is None:
            stats.append(f"  ! {tech}: LCOE series missing, skipped")
            continue
        if use_mult:
            if kpi == "CAPEX":
                vals = {y: vals[y] * pvmult[y] for y in YEARS}
            else:
                note = ""
        overwrite(df, tech, vals, note, stats)
    off = S("Wind Offshore")
    if kpi == "CAPEX":
        _, trans_at = world_series(df, "P_Wind_Offshore_Transitional")
        overwrite(df, "P_Wind_Offshore_Transitional", off, "", stats)
        for t in ("P_Wind_Offshore_Shallow", "P_Wind_Offshore_Deep"):
            _, t_at = world_series(df, t)
            vals = {y: off[y] * t_at(y) / trans_at(y) for y in YEARS}
            overwrite(df, t, vals, "Transitional anchor x base depth ratio", stats)
    else:
        for t in OFFSHORE:
            overwrite(df, t, off, "uniform across depth classes", stats)
    if APPLY:
        save_csv(df, p, hdr)


def run_wacc(stats):
    par = "Par_TechnologyDiscountRate"
    df, p, hdr = load_csv(par)
    # fix the mislabeled unit on the existing default row as well
    df.loc[df.Unit == "Percent", "Unit"] = "Fraction"
    rows = [{"Region": "World", "Technology": t, "Value": f"{v:g}",
             "Unit": "Fraction", "Source": SRC + " (EU WACC column)",
             "Updated at": TODAY, "Updated by": WHO}
            for t, v in sorted(WACC_EU.items())]
    add = pd.DataFrame(rows)
    for c in df.columns:
        if c not in add.columns:
            add[c] = ""
    add = add[df.columns.tolist()]
    keys = set(map(tuple, add[["Region", "Technology"]].values.tolist()))
    keep = ~df[["Region", "Technology"]].apply(tuple, axis=1).isin(keys)
    df = pd.concat([df[keep], add], ignore_index=True)
    stats.append(f"  Par_TechnologyDiscountRate: +{len(rows)} World per-tech WACC rows "
                 "(specific rows override the World,All,0.05 default)")
    if APPLY:
        save_csv(df, p, hdr)


def main():
    data = lcoe_reader.load(LCOE_XLSX)
    stats = []
    stats.append("Par_CapitalCost:")
    run_costfile("Par_CapitalCost", "CAPEX", data, stats)
    stats.append("Par_FixedCost:")
    run_costfile("Par_FixedCost", "Fixed OPEX", data, stats)
    run_wacc(stats)
    print("\n".join(stats))
    print("APPLIED" if APPLY else "DRY-RUN (use --apply)")


if __name__ == "__main__":
    main()
