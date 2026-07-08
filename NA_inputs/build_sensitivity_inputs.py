"""Build the RegularParameters input workbooks for every NA sensitivity.

For each sensitivity this sequentially (the parameter CSVs are shared state):
  1. writes the sensitivity demand   (convert_fel_to_demand --fel <file>)
  2. rebuilds the capacity funnels   (add_capacity_bounds --apply [--fel ...]
                                      [--max-upscale] [--funnel economic])
  3. rebuilds the IC trade bounds    (add_ic_trade_bounds --apply [--growth ...])
  4. converts (power-only filter, parameters_only)
  5. renames the output to RegularParameters_NorthAmerica_<sens>.xlsx
     (the 'base' sensitivity keeps the plain name) and copies it to the model
     repo's InputData.

Run order ends with 'base', so the shared CSVs are left in the base state.
The allFuels workbook and the Timeseries_NorthAmerica_<weatheryear> files are
demand-independent and shared across sensitivities (built separately).

Sensitivities:
  base       base FEL demand, 4%/yr IC growth
  dc_low     low data-center demand FEL
  dc_high    high data-center demand FEL; ratios > 1 RAISE the funnel max
  dc_high_limitless
             dc_high demand, build limits mostly gone: gas cap 100 GW/yr, EGS
             4 GW/yr, funnel max x2 (PV/onshore/BESS), P_SOFC enabled 3->9 GW/yr
  recession  recession-demand FEL
  economic   base demand; funnel widens strongly after 2030 (min x0.75, max x1.5)
  grid_low   base demand; IC growth capped at 2.5%/yr
  grid_high  base demand; no IC %-pace cap (IC High ceiling still applies)

Usage:  python NA_inputs/build_sensitivity_inputs.py [sens ...]   (default: all)
"""
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_REPO = os.path.normpath(os.path.join(HERE, ".."))
CONV = os.path.join(DATA_REPO, "Conversion Script")
OUT = os.path.join(DATA_REPO, "Output", "output_excel")
INPUTDATA = r"C:\Users\testbed\Documents\GENeSYSMOD.jl_SE\InputData"
PY = sys.executable
BASE_FEL = "base_fel_v260707_v2.xlsx"

US_REGIONS = ["California", "WECC", "SPP", "MISO", "ERCOT", "SERC", "PJM",
              "NewYork", "NewEngland"]
YEARS = list(range(2025, 2041))

# SOFC national FTM addition cap (GW/yr). Today's ~3 GW/yr (Bloom) is almost all
# behind-the-meter and NOT this cap: FTM starts at 0 (2025/26), 1.5 in 2027,
# 3 in 2028, then ramps to 9 by 2035 (multi-vendor: FuelCell Energy,
# Doosan/Ceres, Mitsubishi) - on top of the continuing BTM chain.
SOFC_FTM_START = {2025: 0.0, 2026: 0.0, 2027: 1.5, 2028: 3.0}
SOFC_CAP_2028, SOFC_CAP_2035 = 3.0, 9.0
def sofc_cap(y):
    if y in SOFC_FTM_START:
        return SOFC_FTM_START[y]
    return round(SOFC_CAP_2028 + (SOFC_CAP_2035 - SOFC_CAP_2028)
                 * max(0.0, min(1.0, (y - 2028) / 7.0)), 2)

SENS = {   # order matters: 'base' LAST so shared CSVs end in the base state
    "dc_low":    dict(fel="base_fel_dc_low_v260707_v2.xlsx"),
    "dc_high":   dict(fel="base_fel_dc_high_v260707_v2.xlsx", max_upscale=True,
                      ic_growth="0.06",          # demand boom accelerates grid (base 4%)
                      gas_group_cap_scale=1.2,   # GasPlants/USA 65 -> 78 GW/yr (~2035 demand ratio)
                      group_caps={"SOFC": {y: sofc_cap(y) for y in YEARS}},
                      open_sofc=True,
                      filter_file="Set_filter_file_NorthAmerica_dc_high.xlsx"),
    # dc_high demand with the build limits mostly gone: gas cap 100 GW/yr, EGS
    # cap 4 GW/yr, funnel max x2 for PV/onshore/BESS in ERCOT only (elsewhere
    # the demand shift re-routes gas builds), SOFC enabled, loosened model
    # pacing (set_investment_limit=3, set_new_res_capacity=0.2 + ERCOT 0.3 in
    # test/sensitivities/common.jl SENS_MODEL_KWARGS).
    "dc_high_limitless": dict(fel="base_fel_dc_high_v260707_v2.xlsx", max_upscale=True,
                      ic_growth="0.06", max_boost="2.0", max_boost_regions="ERCOT",
                      group_caps={"GasPlants": {y: 100.0 for y in YEARS if y > 2030},
                                  "EGS":       {y: 4.0 for y in YEARS},
                                  "SOFC":      {y: sofc_cap(y) for y in YEARS}},
                      open_sofc=True,
                      # own filter file: P_SOFC selected in the dc_high family
                      # only, the main NA filter keeps it deselected
                      filter_file="Set_filter_file_NorthAmerica_dc_high_limitless.xlsx"),
    # dc_high without the SOFC option: same demand/funnels/caps, but P_SOFC is
    # deselected in its filter file - tests whether the (BTM-reduced) boom can
    # be served by the conventional expansion alone.
    "dc_high_no_sofc": dict(fel="base_fel_dc_high_v260707_v2.xlsx", max_upscale=True,
                      ic_growth="0.06",
                      gas_group_cap_scale=1.2,
                      filter_file="Set_filter_file_NorthAmerica_dc_high_no_sofc.xlsx"),
    "recession": dict(fel="fel_recession_v260707_v2.xlsx", gas_min_floor="0"),
    # BESS sensitivities: base demand/funnels; battery E2P duration and/or
    # Li-Ion cost paths overridden via their scenario subfolders
    # (Par_StorageE2PRatio, Par_CapitalCost, Par_CapitalCostStorage).
    # BTM facilities grid-connect with a 4-year lag: capacity joins as pinned
    # residual (SOFC: res=min=max) / funnel bumps, matching BTM demand joins
    # Power_DataCenter (NA_inputs/add_btm_lag.py). Own filter: P_SOFC enabled.
    "btm_lag": dict(fel=BASE_FEL, btm_lag=True,
                    filter_file="Set_filter_file_NorthAmerica_btm_lag.xlsx"),
    "bess_e2p_6h":      dict(fel=BASE_FEL),
    "bess_e2p_8h":      dict(fel=BASE_FEL),
    "bess_cost_low":    dict(fel=BASE_FEL),
    "bess_cost_low_6h": dict(fel=BASE_FEL),
    "bess_cost_low_8h": dict(fel=BASE_FEL),
    "economic":  dict(fel=BASE_FEL, funnel="economic"),
    "grid_low":  dict(fel=BASE_FEL, ic_growth="0.025"),
    "grid_high": dict(fel=BASE_FEL, ic_growth="none"),
    "base":      dict(fel=BASE_FEL),
}


def run(args, cwd):
    r = subprocess.run([PY] + args, cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"FAILED: {' '.join(args)}\n{r.stdout[-1500:]}\n{r.stderr[-1500:]}")


def build(sens, cfg):
    """Non-base sensitivities write ONLY into the conversion's scenario
    subfolders (Par_X/NorthAmerica_<sens>/Par_X.csv, upserted over the base at
    conversion time) - the base CSVs are never touched. 'base' refreshes the
    base CSVs + workbook exactly as before."""
    print(f"{chr(10)}=== {sens} ===", flush=True)
    fel = cfg["fel"]
    scen = "NorthAmerica" if sens == "base" else f"NorthAmerica_{sens}"
    sub = [] if sens == "base" else ["--scenario-subdir", scen]
    run(["NA_inputs/convert_fel_to_demand.py", "--fel", fel] + sub, DATA_REPO)
    bounds = ["NA_inputs/add_capacity_bounds.py", "--apply", "--fel", fel] + sub
    if cfg.get("max_upscale"):
        bounds.append("--max-upscale")
    if cfg.get("funnel"):
        bounds += ["--funnel", cfg["funnel"]]
    if cfg.get("gas_min_floor") is not None:
        bounds += ["--gas-min-floor", cfg["gas_min_floor"]]
    if cfg.get("max_boost"):
        bounds += ["--max-boost", cfg["max_boost"]]
    if cfg.get("max_boost_regions"):
        bounds += ["--max-boost-regions", cfg["max_boost_regions"]]
    run(bounds, DATA_REPO)
    if cfg.get("btm_lag"):
        run(["NA_inputs/add_btm_lag.py", "--apply"] + sub, DATA_REPO)
    ic = ["NA_inputs/add_ic_trade_bounds.py", "--apply"] + sub
    if cfg.get("ic_growth"):
        ic += ["--growth", cfg["ic_growth"]]
    run(ic, DATA_REPO)
    if cfg.get("gas_group_cap_scale") or cfg.get("group_caps"):
        # group new-capacity cap overrides as a scenario-subfolder upsert row set
        import pandas as _pd
        gp = os.path.join(DATA_REPO, "Data", "Parameters",
                          "Par_GroupTotalAnnualMaxNewCap", "Par_GroupTotalAnnualMaxNewCap.csv")
        g = _pd.read_csv(gp)
        g.columns = ["" if str(c).startswith("Unnamed") else c for c in g.columns]
        parts = []
        if cfg.get("gas_group_cap_scale"):
            # scale only AFTER 2030: near-term turbine supply is already locked
            # in, a demand boom cannot buy more deliveries before then. Omitting
            # the <=2030 rows keeps the base schedule via the upsert.
            m = (g.TechnologySubset == "GasPlants") & (g.RegionSubset == "USA") & (g.Year > 2030)
            scaled = g[m].copy()
            scaled["Value"] = (scaled["Value"] * float(cfg["gas_group_cap_scale"])).round(1)
            scaled["Source"] = f"GasPlants cap x {cfg['gas_group_cap_scale']} post-2030 (demand-scaled, {sens})"
            parts.append(scaled)
        if cfg.get("group_caps"):
            recs = [{"TechnologySubset": ts, "RegionSubset": "USA", "Year": y,
                     "Value": v, "": "", "Unit": "GW",
                     "Source": f"{ts} annual-additions cap ({sens})",
                     "Updated at": "2026-07-04",
                     "Updated by": "Konstantin Loffler <kl@wip.tu-berlin.de>"}
                    for ts, yv in cfg["group_caps"].items() for y, v in sorted(yv.items())]
            parts.append(_pd.DataFrame(recs)[g.columns])
        rows = _pd.concat(parts, ignore_index=True)
        outdir = os.path.join(os.path.dirname(gp), scen)
        os.makedirs(outdir, exist_ok=True)
        rows.to_csv(os.path.join(outdir, os.path.basename(gp)), index=False, lineterminator="\n")
    if cfg.get("open_sofc"):
        # P_SOFC is forbidden in the base data (World max = 0.001 GW dead-cap);
        # open it for the US regions here with an explicit 999999 no-limit
        # sentinel - the SOFC group addition cap governs. NOT 0: the model's
        # raw-max-0 -> 999999 rule (genesysmod_bounds) only covers the fossil/
        # CHP/transport subsets, so a 0 would hard-block the tech. Canada has
        # no rows and stays blocked by that same rule.
        import pandas as _pd
        mc = os.path.join(DATA_REPO, "Data", "Parameters",
                          "Par_TotalAnnualMaxCapacity", "Par_TotalAnnualMaxCapacity.csv")
        outdir = os.path.join(os.path.dirname(mc), scen)
        path = os.path.join(outdir, os.path.basename(mc))
        d = _pd.read_csv(path)   # written by add_capacity_bounds just above
        d.columns = ["" if str(c).startswith("Unnamed") else c for c in d.columns]
        # REPLACE the unmanaged-tech FORBID_EPS rows for the US regions (Canada
        # keeps its forbid row); appending would leave duplicate (r,t,y) rows
        # and the model's create_daa would keep whichever comes last.
        d = d[~((d.Technology == "P_SOFC") & d.Region.isin(US_REGIONS))]
        recs = [{"Region": r, "Technology": "P_SOFC", "Year": y, "Value": 999999.0,
                 "": "", "Unit": "GW",
                 "Source": f"SOFC opened for {sens}; group addition cap governs",
                 "Updated at": "2026-07-04",
                 "Updated by": "Konstantin Loffler <kl@wip.tu-berlin.de>"}
                for r in US_REGIONS for y in YEARS]
        out = _pd.concat([d, _pd.DataFrame(recs)[d.columns]], ignore_index=True)
        out.to_csv(path, index=False, lineterminator="\n")
    if sens == "base":
        run(["script_northamerica.py"], CONV)      # params + base timeseries
        name = "RegularParameters_NorthAmerica.xlsx"
    else:
        # conversion with the scenario option applies the subfolder upserts and
        # names the output RegularParameters_<scenario_option>.xlsx directly;
        # a sensitivity may bring its own filter file (different set selection)
        filt = cfg.get("filter_file", "Set_filter_file_NorthAmerica.xlsx")
        code = ("from functions.function_import import master_function;"
                f"master_function('{filt}','excel','long',"
                f"'parameters_only','{scen}',False,'California')")
        run(["-c", code], CONV)
        name = f"RegularParameters_{scen}.xlsx"
    shutil.copyfile(os.path.join(OUT, name), os.path.join(INPUTDATA, name))
    print(f"  -> {name} (built + copied to InputData)", flush=True)


def main():
    wanted = sys.argv[1:] or list(SENS)
    ordered = [s for s in SENS if s in wanted]     # keep 'base' last
    unknown = set(wanted) - set(SENS)
    if unknown:
        sys.exit(f"unknown sensitivities: {unknown} (have: {list(SENS)})")
    if "base" in wanted and ordered[-1] != "base":
        ordered.remove("base"); ordered.append("base")
    for sens in ordered:
        build(sens, SENS[sens])

    print("\ndone")


if __name__ == "__main__":
    main()
