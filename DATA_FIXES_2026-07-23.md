# Data Fixes & LCOE Import — applied 2026-07-23

Companion to `DATA_REVIEW_2026-07-23.md` (findings) and
`NA_inputs/LCOE_Model_v1.4_issues_2026-07-23.md` (LCOE-file issues for the
file owners). This file records what was **changed**.

> **Result impact:** capex, fixed O&M, WACC and the investment-side gas price
> all moved. The next NA run generation is **v7** — not comparable to v6.
> The dispatch gas double-count fix alone lowers 2030/2040 dispatch gas from
> 13.23/12.13 to 10.2 €/MWh(th).

## 1. Verified-bug fixes (base parameter CSVs)

| Fix | File(s) | Detail |
|---|---|---|
| P_Oil capex /10 | Par_CapitalCost | 9357.68 → 935.768 MEUR/GW, all years (decimal shift of the CCGT digit string; DEA diesel ~860–900) |
| Duplicate keys dropped | Par_CapitalCost, Par_FixedCost (P_Nuclear_SMR, 23 rows each), Par_TotalAnnualMax/MinCapacity (Canada P_Biomass 7×/yr, 96 each), Par_TotalAnnualMaxActivity (720), Par_AvailabilityFactor (Z_Import_LNG, 13), Par_RampingDownFactor (1) | keep-first; values were era-consistent, no value change |
| Conflicting bound row deleted | Par_TotalAnnualMaxCapacity | `GR,D_PHS,All` 0.125 (unsourced) removed; 5.453 (E3M/Greek NECP) stands |
| Blank Values fixed | Par_CapitalCost (12), Par_FixedCost (17), Par_VariableCost (2): 2021 cells interpolated 2020→2025 (the `create_daa`→0 "Redox flood" class); Par_TotalAnnualMaxCapacity: 48 SPP offshore blanks → explicit 0 (landlocked) | |
| Trailing-space keys stripped | Par_SpecifiedAnnualDemand (960 `"Heat_Low_Industrial "`), Par_ResidualCapacity (25 `"HD_Geothermal "`) | global sweep over Region/Technology/Fuel columns |
| Broken series repaired | Par_FixedCost: HMHI_Steam_Electric 2031–2049 re-interpolated over the broken 2040 anchor (0.000849); CSP source-field quoting fixed (7 rows column shift, 2 rows stray 10th field) | |
| Value typos | Par_OperationalLife: X_SOEC_Electrolysis 3→20 y (stack vs plant life), P_Nuclear/SMR 61→60 y; Par_CapitalCost: HLI_H2_Boiler 2018 650→56.73 | |
| NA dummy EU-copies deleted | Par_ModelPeriodActivityMaxLimit | 11 rows (e.g. `NewYork,R_Coal_Hardcoal` = the Poland value); neutral default = no limit |
| Blank line removed | Par_RegionalBaseYearProduction | 1 all-NaN row |

CHP mode-2 total efficiencies slightly >100 % (WasteToEnergy 103 %,
CHP_Biomass_Solid 101 %) were **left unchanged** — flue-gas condensation
legitimately exceeds 100 % LHV utilization.

## 2. LCOE cost import ("FEL2026 LCOE Model file V1.4, dated 2026-06-18")

- **NA (US column)** — `NA_inputs/add_lcoe_costs.py`, wired into
  `build_sensitivity_inputs.py` (every sensitivity, via `--scenario-subdir`)
  and `run_na_pipeline.py`. Per-NA-region rows, 2025–2040 yearly:
  CAPEX + Fixed OPEX for CCGT (2150→1294 €/kW), OCGT (924), recip engines
  (3125/29, Customized sheet), coal (2352, both coal techs), PV utility
  (930 × learning → 673 by 2040, three classes), PV rooftop commercial
  (2117→908), onshore wind (1563→1418, three classes), offshore wind
  (anchored on Transitional 4571→4040, Shallow/Deep scaled by the base depth
  ratio); WACC rows (CCGT 0.065, OCGT/engines 0.075, coal & nuclear 0.085,
  PV 0.05, onshore 0.055, offshore 0.07, EGS/SOFC 0.07).
- **EU (All-regions column)** — `apply_lcoe_eu_costs.py` (one-time, applied):
  same technology set into the base **World** rows (CCGT 1100→924, OCGT 730,
  coal 2240, PV 679×learning→491, onshore 1707→1459, offshore anchored,
  FOM incl. coal 179 and offshore 132→105); 2045–2060 = prior decline
  continued as a ratio on the new 2040 value; ≤2021 untouched. Ready for the
  country-level EU version (countries inherit World).
- **WACC wiring**: `Par_TechnologyDiscountRate` is now read by the model
  (GENeSYSMOD.jl dataload → settings; 0.05 neutral default; World
  inheritance). Unit label fixed Percent→Fraction.
- **Invest-side gas = Henry Hub**: `Z_Import_Gas` NA rows now carry the LCOE
  US gas macro (= HH forward path) 11.9/12.8/11.2/9.5/9.5/10.2 €/MWh(th)
  2025→2030, flat to 2040 (was the EU APS path 13.32→17.28→15.84).
- **Not imported** (documented in `NA_inputs/LCOE_Model_v1.4_issues_2026-07-23.md`):
  nuclear + SMR (multiplier double-count; the deliberate 10 000 €/kW uprate
  of 2026-06 stands), geothermal (different asset class than EGS), SOFC
  (repo's Bloom-sourced rows of 2026-07-04 are newer), CCS (no adder +
  inverted WACC in LCOE), VOM, efficiencies, EU fuel prices, oil/hydro/
  storage (missing in LCOE).

## 3. Dispatch-layer fixes (`Data/Dispatch/`)

- `Par_DispatchFuelPriceYear.csv`: Gas multipliers retired to 1.0 — the year
  shape now lives in `Z_Import_Gas`. The old combination double-counted the
  year shape (dispatch code multiplies the dispatch-year VC, which already
  embedded a year-varying gas price): effective 2030 gas was 13.23 €/MWh(th)
  instead of the intended 10.2 (+30 %), 2040 12.13 (+19 %). Affects all v6
  dispatch results for 2030/2040 in absolute terms (cross-scenario
  comparisons shared the error).
- `Par_DispatchBidAdder.csv`: blank Region rows (= World wildcard) expanded
  to the 9 explicit US regions — Canadian wind/nuclear no longer receive the
  US PTC/45U; PTC depth corrected −33 → −31 €/MWh (published IRA 27.5
  USD/MWh tax-grossed, was a 30 USD base).
- `Par_DispatchVoLL.csv` + `Par_DispatchORDC.csv`: USD values were written
  1:1 as EUR; converted ×0.9 (repo convention, cf. Par_DispatchCO2Price).
  ERCOT VoLL 5000→4500, MISO 10000→9000; ORDC steps scaled alike (ERCOT
  inner step 4050 < VoLL 4500, ordering preserved).

## 4. Model-code fixes (GENeSYSMOD.jl_SE)

- `genesysmod_precompute_powerOnly.jl`: nuclear fuel cost was silently 0 (the
  `Z_Import_Nuclear` lookup missed); `UPSTREAM_TECH["Nuclear"] =
  ("R_Nuclear", 0.0)` prices uranium at the R_Nuclear VC (~2.6 €/MWh th,
  ≈ +7.9 €/MWh el on nuclear SRMC).
- `Par_TechnologyDiscountRate` wired end-to-end (datastructures, dataload,
  settings): per-technology, per-region WACC from data; flat 0.05 remains
  the neutral default when the sheet is absent.

## 5. Rebuilt artifacts

`RegularParameters_NorthAmerica.xlsx`, `RegularParameters_NorthAmerica_allFuels.xlsx`,
`DispatchData_NorthAmerica.xlsx` rebuilt from the fixed CSVs and copied to the
model repo's InputData. **Sensitivity workbooks
(`RegularParameters_NorthAmerica_<sens>.xlsx`) and the dispatch-variant
workbooks are stale until `build_sensitivity_inputs.py` is re-run** (the LCOE
import is wired in, so a rebuild picks everything up); EU EnVis workbooks
likewise pending a `script_eu_envis.py` re-run.
