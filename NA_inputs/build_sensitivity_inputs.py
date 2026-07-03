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
    "dc_high":   dict(fel="base_fel_dc_high v260703.xlsx", max_upscale=True),
    "recession": dict(fel="fel_recession_v260703.xlsx"),
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
    print(f"\n=== {sens} ===", flush=True)
    fel = cfg["fel"]
    run(["NA_inputs/convert_fel_to_demand.py", "--fel", fel], DATA_REPO)
    bounds = ["NA_inputs/add_capacity_bounds.py", "--apply", "--fel", fel]
    if cfg.get("max_upscale"):
        bounds.append("--max-upscale")
    if cfg.get("funnel"):
        bounds += ["--funnel", cfg["funnel"]]
    run(bounds, DATA_REPO)
    ic = ["NA_inputs/add_ic_trade_bounds.py", "--apply"]
    if cfg.get("ic_growth"):
        ic += ["--growth", cfg["ic_growth"]]
    run(ic, DATA_REPO)
    run(["script_northamerica.py"], CONV)            # params + base TS (cheap, reuses filter)
    src = os.path.join(OUT, "RegularParameters_NorthAmerica.xlsx")
    name = "RegularParameters_NorthAmerica.xlsx" if sens == "base" \
        else f"RegularParameters_NorthAmerica_{sens}.xlsx"
    dst = os.path.join(OUT, name)
    if sens != "base":
        shutil.copyfile(src, dst)
    shutil.copyfile(dst, os.path.join(INPUTDATA, name))
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
    if "base" not in ordered:
        print("\nNOTE: 'base' not rebuilt - shared CSVs are left in the LAST "
              "sensitivity's state; run with 'base' (or no args) to restore.")
    print("\ndone")


if __name__ == "__main__":
    main()
