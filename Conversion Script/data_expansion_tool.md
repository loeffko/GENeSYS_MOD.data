# Data Expansion Tool

A small, reusable toolkit for **adding new regions, years, and other set
members** to the GENeSYS-MOD data set without hand-editing dozens of CSV files.

It was built to create a placeholder **North America** model (9 US regions +
Canada) but is generic: the same functions extend the data set with new
technologies, fuels, storages, etc.

---

## Files

| File | Role |
|------|------|
| `functions/expand_data.py` | Generic, reusable library. No project-specific config. |
| `expand_northamerica.py`   | Driver script. Holds the North America config and runs the full expansion. |
| `data_expansion_tool.md`   | This document. |

---

## What it does

Running `expand_northamerica.py` performs five steps, **in place** on the
(git-tracked) `GENeSYS_MOD.data` repository:

1. **Sets** — appends the new regions to `Data/Parameters/00_Sets&Tags/Sets_Region.csv`
   and the new years to `Sets_Year.csv`.
2. **Regions → parameter CSVs** — for every `Par_*/Par_*.csv`, copies each new
   region's placeholder data from its mapped source country.
3. **Years → parameter CSVs** — adds every missing model year by linear
   interpolation between existing data points.
4. **Regions → timeseries** — adds a column per new region to every wide
   `TS_*/TS_*.csv`, copied from the source region's column.
5. **Filter file** — reconfigures `Set_filter_file.xlsx`: enables the new
   regions (+ `World`) and the modelled years, disables everything else.

---

## How to run

```bash
cd "GENeSYS_MOD.data/Conversion Script"
python expand_northamerica.py
```

Requirements: `pandas`, `numpy`, `openpyxl` (already in `requirements.txt`).

All changes are in place and git-tracked:

```bash
cd ..                       # GENeSYS_MOD.data repo root
git diff --stat             # review what changed
git checkout -- .           # revert everything if needed
```

---

## Configuration

Everything project-specific lives at the top of `expand_northamerica.py`:

```python
REGION_MAP = {              # new_region -> source country to copy from (1:1)
    "California": "DE", "WECC": "FR", "SPP": "NL", "MISO": "BE",
    "ERCOT": "AT", "SERC": "CZ", "PJM": "CH", "NewYork": "PL",
    "NewEngland": "IT", "Canada": "ES",
}
TARGET_YEARS  = list(range(2025, 2041))   # every individual model year
BASE_YEAR     = 2018                      # kept enabled as the start year
```

- `REGION_MAP` must be a **1:1 mapping** (bijection). The trade-pair logic
  relies on it being invertible.
- `ENABLED_YEARS` / `ENABLED_REGIONS` are derived from these constants.

To retarget the tool (different regions, different horizon) edit only these
constants — no other code changes needed.

---

## Behaviour notes

**Source tagging.** Every copied placeholder row has its `Source` column set to
`dummy data - empty entry`. Interpolated rows get `interpolated`. This makes
placeholder/derived data easy to find and replace later.

**World-only parameters.** Many parameters (e.g. `Par_OutputActivityRatio`,
`Par_CapitalCost`) store data only under the `World` region. These get **no new
rows** — new regions inherit `World` automatically through the model's
`inherit_base_world` mechanism, exactly as existing countries do. This is
correct, not a miss.

**Trade parameters** (`Par_TradeCapacity`, `Par_TradeRoute`, …) are indexed by a
region *pair* (`Region`, `Region.1`). The tool copies an ordered pair only when
**both** endpoints are mapped source countries, relabelling both — so the new
regions get an intra-North-America trade graph mirroring the intra-source-
country graph (e.g. `California–ERCOT` is copied from `DE–AT`).

**Year interpolation.** For each parameter index group, a year is added only if
it is missing **and** lies within that group's existing `[min, max]` year
range; values are linearly interpolated (`numpy.interp`). Rows whose `Year` is
the literal `All` are left untouched. Groups with fewer than two numeric points
are skipped.

**Idempotence.** Re-running appends duplicates — the tool is meant to run once
on a clean data state. Use `git checkout` to reset before re-running.

---

## Extending the tool

The library in `functions/expand_data.py` is set-agnostic. To add, for example,
a new technology copied from an existing one:

```python
from functions.expand_data import read_param, write_param, param_csv_paths, \
    duplicate_member_in_df

for csv in param_csv_paths(PARAMETERS_DIR):
    df = read_param(csv)
    df = duplicate_member_in_df(df, "Technology", "Wind_Onshore", "Wind_New")
    write_param(df, csv)
```

The same `duplicate_member_in_df(df, column, source, new)` works for any single
index column — `Fuel`, `Storage`, `Emission`, `Mode_of_operation`, etc. Region
pairs are the only special case, handled by `duplicate_regions_in_df`.

Suggested next step for a fuller tool: a single config-driven driver that reads
a YAML spec (`add_regions`, `add_technologies`, `add_years`, …) and applies all
of it — so future additions need no Python edits at all.

---

## Function reference (`functions/expand_data.py`)

| Function | Purpose |
|----------|---------|
| `param_csv_paths(dir)` | List master `Par_X/Par_X.csv` files (skips scenario subfolders). |
| `read_param` / `write_param` | Text-stable CSV IO. |
| `index_columns(df)` | Index/dimension columns (everything left of `Value`). |
| `region_columns(df)` | Region columns, incl. `Region.1` for trade pairs. |
| `duplicate_member_in_df(df, column, source, new)` | Generic set-member copy. |
| `duplicate_regions_in_df(df, region_map)` | Region copy, trade-pair aware. |
| `interpolate_years_in_df(df, target_years)` | Linear year interpolation. |
| `append_set_entries(csv, entries)` | Append to a `Sets_*.csv`. |
| `timeseries_csv_paths(dir)` | List master `TS_X/TS_X.csv` files. |
| `add_timeseries_columns(csv, region_map)` | Add region columns to wide TS files. |
| `update_selection_sheet(xlsx, sheet, enabled, add_rows)` | Edit a `Set_filter_file.xlsx` selection sheet. |
| `expand_all_parameters(dir, region_map, target_years)` | High-level sweep over all parameter CSVs. |
