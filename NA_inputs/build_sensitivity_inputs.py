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
BASE_FEL = "base_fel_v260702_v2.xlsx"

SENS = {   # order matters: 'base' LAST so shared CSVs end in the base state
    "dc_low":    dict(fel="base_fel_dc_low v260703.xlsx"),
    "dc_high":   dict(fel="base_fel_dc_high v260703.xlsx", max_upscale=True,
                      ic_growth="0.06",          # demand boom accelerates grid (base 4%)
                      gas_group_cap_scale=1.2),  # GasPlants/USA 65 -> 78 GW/yr (~2035 demand ratio)
    "recession": dict(fel="fel_recession_v260703.xlsx", gas_min_floor="0"),
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
    run(bounds, DATA_REPO)
    ic = ["NA_inputs/add_ic_trade_bounds.py", "--apply"] + sub
    if cfg.get("ic_growth"):
        ic += ["--growth", cfg["ic_growth"]]
    run(ic, DATA_REPO)
    if cfg.get("gas_group_cap_scale"):
        # demand-scaled GasPlants/USA cap as a scenario-subfolder upsert row set
        import pandas as _pd
        gp = os.path.join(DATA_REPO, "Data", "Parameters",
                          "Par_GroupTotalAnnualMaxNewCap", "Par_GroupTotalAnnualMaxNewCap.csv")
        g = _pd.read_csv(gp)
        g.columns = ["" if str(c).startswith("Unnamed") else c for c in g.columns]
        m = (g.TechnologySubset == "GasPlants") & (g.RegionSubset == "USA")
        rows = g[m].copy()
        rows["Value"] = (rows["Value"] * float(cfg["gas_group_cap_scale"])).round(1)
        rows["Source"] = f"GasPlants cap x {cfg['gas_group_cap_scale']} (demand-scaled, {sens})"
        outdir = os.path.join(os.path.dirname(gp), scen)
        os.makedirs(outdir, exist_ok=True)
        rows.to_csv(os.path.join(outdir, os.path.basename(gp)), index=False, lineterminator="\n")
    if sens == "base":
        run(["script_northamerica.py"], CONV)      # params + base timeseries
        name = "RegularParameters_NorthAmerica.xlsx"
    else:
        # conversion with the scenario option applies the subfolder upserts and
        # names the output RegularParameters_<scenario_option>.xlsx directly
        code = ("from functions.function_import import master_function;"
                f"master_function('Set_filter_file_NorthAmerica.xlsx','excel','long',"
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
