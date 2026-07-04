# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Project

`GENeSYS_MOD.data` — the input data set for the GENeSYS-MOD energy system
model. It holds per-parameter CSV files and a Python conversion pipeline that
combines them into the Excel files the model (`GENeSYS_MOD.jl`) reads.

## Layout

- `Data/Parameters/Par_X/Par_X.csv` — master CSV for each parameter
  (long format). Scenario subfolders (`Europe_EnVis_*`, `MiddleEarth`, ...)
  hold scenario-specific overrides.
- `Data/Parameters/00_Sets&Tags/` — `Sets_*.csv` (set members) and tag tables.
- `Data/Timeseries/TS_X/TS_X.csv` — wide format: `HOUR` column + one column
  per region. Row 0 is a `Source:` metadata line.
- `Conversion Script/` — Python pipeline (CSV → Excel) and run scripts.
- `Output/output_excel/` — generated `RegularParameters_*.xlsx` /
  `Timeseries_*.xlsx`.

## Conversion pipeline

- Run scripts: `script_eu_envis.py`, `script_middleearth.py`,
  `script_northamerica.py` — each sets a `Set_filter_file*.xlsx`, a
  `scenario_option`, and a `data_base_region`, then calls `master_function`.
- `Set_filter_file.xlsx` is the **universal** filter (every set member present);
  per-region presets (`Set_filter_file_MiddleEarth.xlsx`,
  `Set_filter_file_NorthAmerica.xlsx`) enable a chosen subset.
- **When adding a new set member** (technology, region, fuel, storage, emission,
  mode, sector, ...): besides the parameter CSVs and `Sets_*.csv`, you MUST also
  add a row for it in the matching `*_selection` sheet (`Technology_selection`,
  `Region_selection`, `Fuel_selection`, ...) of EVERY `Set_filter_file*.xlsx` you
  intend to run, with the `... selected` flag = 1. Otherwise `master_function`
  filters the new member OUT of the converted Excel and the model never sees it.
  (Add via openpyxl so the workbook's other sheets are preserved.)
- A `scenario_option` must match an existing scenario subfolder name, or be
  `'None'`. A folder with only a `dummy.txt` marker is enough to register a
  scenario whose data lives entirely in the base CSVs.
- **Scenario/sensitivity data belongs in scenario subfolders, never in edits to
  the base CSVs**: `Par_X/<scenario_option>/Par_X.csv` rows are applied as a
  row-level upsert over the base file (override matching index rows, append
  new ones) when converting with that `scenario_option`, and the output is
  named `RegularParameters_<scenario_option>.xlsx`. The NA sensitivity scripts
  write their outputs there via `--scenario-subdir <name>` (see
  `NA_inputs/build_sensitivity_inputs.py`). Timeseries support the same
  subfolder mechanism plus per-weather-year folders (`TS_X/<year>/`).
- **A scenario can also bring its own filter file**: `master_function`'s first
  argument is the filter-file name, so a scenario needing a different set
  selection (e.g. a tech enabled only there, like P_SOFC in
  `Set_filter_file_NorthAmerica_dc_high_limitless.xlsx`) gets its own
  `Set_filter_file_<...>.xlsx` — never toggle flags in a shared filter file
  back and forth between conversions.

## Data expansion tool

`Conversion Script/functions/expand_data.py` + `expand_northamerica.py` add new
regions / years / set members to the data set. See
`Conversion Script/data_expansion_tool.md` for full docs.

- Generic: `duplicate_member_in_df` works for regions, technologies, fuels, ...
- **Not idempotent** — re-running appends duplicates. Revert with
  `git checkout HEAD -- Data` before re-running.

## Conventions & gotchas

- Parameter CSVs are long-format: `<index cols...>, Value, <blank>, Unit,
  Source, Updated at, Updated by`. Index columns are everything left of `Value`.
- Trade parameters carry two region columns: `Region` and `Region.1`.
- The `Year` column may be a specific year or the literal `All`.
- All CSVs are **UTF-8** with **LF** line endings — preserve both on write
  (`open(..., encoding="utf-8", newline="")`, explicit `lineterminator`).
  Pandas `to_csv` defaults to the OS line ending / locale encoding — do not
  rely on the defaults.
- Files are git-tracked: review changes with `git diff`, revert with
  `git checkout`.

## Relationship to the model

The model repository `GENeSYS_MOD.jl` consumes the Excel files produced here.
Region/year sets, parameter coverage, and naming must stay consistent with
what the model expects.
