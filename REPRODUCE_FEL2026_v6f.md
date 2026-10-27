# Reproducing the FEL 2026 base run v6f (final 2026 iteration)

Run label: `fel2026_base_49_2015_v6f` (North America, 49-hour timeslices, weather year 2015).

## Data

- Branch `release/fel2026-v6f` = tag `run/fel2026_v6e-v6f` = commit `81f4576`: the v6 freeze (`v6-freeze`, a00d5d9)
  plus the base fixes that were applied in the freeze worktree before the run (biogas mode, rooftop build-rate cap,
  gas-steam floor, ramping / storage / cost corrections). A clean conversion of this commit reproduces
  `RegularParameters_NorthAmerica_v6f.xlsx` and `Timeseries_NorthAmerica_2015.xlsx` sheet for sheet (checked 2026-10-23).
- Conversion (from `Conversion Script/`, Python 3.11+, `pip install -r requirements.txt`):

      python -c "from functions.function_import import master_function; master_function('Set_filter_file_NorthAmerica.xlsx','excel','long','both','NorthAmerica',False,'California', weather_year=2015)"
      python script_northamerica_allfuels.py

  Outputs in `Output/output_excel/`: `RegularParameters_NorthAmerica.xlsx` (rename to `..._v6f.xlsx`),
  `Timeseries_NorthAmerica_2015.xlsx`, `RegularParameters_NorthAmerica_allFuels.xlsx` (rename to `..._allFuels_v6.xlsx`).
  Copy them to the model's `InputData/`.

## Model

- Code repository `GENeSYSMOD.jl_SE`, tag `run/fel2026_v6e-v6f` (commit 2cdeb52 on `dev/se`, the last commit before
  the run; later commits on `dev/se` are analysis scripts and the timeseries fallback and do not change the LP).
- Driver: the run used the settings in `_s14/run_base_v6f.jl` (archived under `debug_scripts/_s14/` locally):
  `genesysmod(; set_new_res_capacity=0.1, elmod_daystep=2, elmod_hourstep=1, year=2025, switch_power_only_mode=1,
  data_file="RegularParameters_NorthAmerica_v6f", hourly_data_file="Timeseries_NorthAmerica_2015",
  allfuels_data_file="RegularParameters_NorthAmerica_allFuels_v6", switch_investLimit=1, switch_ccs=1, switch_ramping=1,
  E2P_ratio_deviation_factor=1.1, switch_weighted_emissions=1, switch_intertemporal=0, switch_base_year_bounds=0,
  switch_peaking_capacity=1, set_peaking_slack=0, set_peaking_minrun_share=0, set_peaking_res_cf=0.5,
  set_peaking_startyear=2025, switch_peaking_with_storages=1, switch_peaking_with_trade=1, switch_peaking_minrun=0,
  elmod_starthour=8, elmod_dunkelflaute=0, model_region="north_america", data_base_region="California",
  solver=Gurobi.Optimizer, DNLPsolver=Ipopt.Optimizer, threads=6)`.
  Every switch of the run is also stored in the results database (`output_switches`, scenario `fel2026_base_49_2015_v6f`).

## Successors

- v6e (`RegularParameters_NorthAmerica_v6e.xlsx`): the same state minus the rooftop build-rate cap and the gas-steam
  floor; never a separate commit.
- v7 / v7b (tags `run/fel2026_v7`, `run/fel2026_v7b` on `se_northamerica`): LCOE v1.4 cost import and later data review;
  basis of the next set of runs, not comparable to v6f.
- The climate-adaptation set (`dev/fel-x-su-climate-adaptation`, tag `run/fel2026_climate_v1`) builds on the v6f state.
