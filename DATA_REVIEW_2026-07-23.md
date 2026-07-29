# Data Review — 2026-07-23

Full sweep of the data repository (base parameter CSVs, dispatch CSVs, NA
workbook, source registry) plus reconciliation against the LCOE cost model
(`NA_inputs/260618 LCOE_Model_FEL26_v1.4.xlsx`) for NA and EU. Ten review
agents + manual re-verification of every high-impact conflict claim (the
automated verify pass hit the session limit; items marked ✔ were re-verified
by hand against the files/code, items marked (agent) rest on a single
reviewer pass).

Scope note: on this machine the plain `NorthAmerica/` overlay folders contain
only `dummy.txt` (real NA base overlays live on the data machine). NA numbers
were therefore audited in the built workbook
(`GENeSYSMOD.jl_SE/InputData/RegularParameters_NorthAmerica.xlsx`) and the
generated `NorthAmerica_<sensitivity>` overlay CSVs, which are real here.

---

## 1. VERIFIED CONFLICTS — data/code is wrong

### 1.1 Dispatch gas-price double-count (code × data interaction) ✔
`Par_DispatchFuelPriceYear.csv` multipliers are documented as "× of embedded
13.32 EUR/MWh(th)", but `genesysmod_dispatch_fullyear.jl` applies them to the
**dispatch year's own** VariableCost (`basecost = vc(r,d)@y0 × fuelmult ×
fuelyear`), and the workbook's embedded gas is year-varying
(`Z_Import_Gas` 3.70 → 4.80 (2030–35) → 4.40 (2040) MEUR/PJ = 13.32 → 17.28 →
15.84 €/MWh(th)). Effective dispatch gas:
| Year | intended (HH) | actual | error |
|---|---|---|---|
| 2025 | 11.90 | 13.32×0.8934 = 11.90 | ✔ correct |
| 2030 | 10.20 | 17.28×0.7658 = **13.23** | **+30%** |
| 2040 | 10.20 | 15.84×0.7658 = **12.13** | **+19%** |
**Affects every v6 dispatch result for 2030/2040** (incl. the 16 crosses).
Scenario *comparisons* stand (all share the error); absolute price levels for
2030/2040 are too high wherever gas is marginal. The multiplier also scales
the VOM part of VC (second-order). Fix options: (a) flatten `Z_Import_Gas` to
3.70 across years and let the multiplier carry the whole path, or (b) make
multipliers relative to each year's embedded price. (a) is safer — one change,
dispatch-only, matches the documented semantics; but (a) also changes the
investment model's gas path, see 2.1.

### 1.2 Nuclear fuel cost never reaches the model ✔
`genesysmod_precompute_powerOnly.jl` prices fuel via `Z_Import_<fuel>` with
`FUEL_ALIAS` for gas/LNG/H2 — but fuel `Nuclear` has no alias and no
`Z_Import_Nuclear` exists (the workbook carries `R_Nuclear`, 0.722 MEUR/PJ =
2.6 €/MWh(th)); `upstream_vc` returns 0. Confirmed in the run dump: P_Nuclear
VC = 1.9167 MEUR/PJ = workbook VOM, no fuel added. Nuclear SRMC ≈ 6.9 €/MWh
instead of ≈ 13.5 (LCOE model: 7 VOM + 6.45 fuel). Modest result impact
(nuclear is must-run at 0.92 and rarely marginal) but wrong. Fix: add
`"Nuclear" => "Nuclear"` handling (or `UPSTREAM_TECH["Nuclear"] =
("R_Nuclear", 0.0)`).

### 1.3 US PTC bid adders apply to Canada ✔
`Par_DispatchBidAdder.csv` leaves Region blank on all wind/nuclear rows;
blank → `World` wildcard → **Canadian** wind bids −33 €/MWh (US PTC) and
Canadian nuclear −14. Canada's clean-electricity ITC is investment-based, not
per-MWh. Fix: explicit US-region rows (9 regions × techs) instead of blank.

### 1.4 P_Oil capex 10× too high ✔
`Par_CapitalCost.csv`: P_Oil = 9357.679918 MEUR/GW all years — the exact
digit string of P_Gas_CCGT's 935.767992 shifted one decimal. DEA source
(diesel engine farm) says ~860–900 €/kW. P_Oil FixedCost 9.36 (0.1% of capex)
corroborates. Should be ≈ 936.

### 1.5 P_Nuclear_SMR duplicate keys with CONFLICTING values ✔
`Par_CapitalCost.csv`: 46 SMR rows on 23 unique (Region,Year) keys — one set
at 6000, one at 10000 MEUR/GW. Which reaches the model depends on conversion
upsert order; the NA workbook ended up with **10000 flat 2025–2040**, locking
SMR out everywhere. `Par_FixedCost` has the same 46/23 duplication. Decide the
value (and give SMR its own trajectory — currently a P_Nuclear copy),
de-duplicate.

### 1.6 Blank Value cells (the "Redox flood" signature) ✔
Year-2021 blanks that `create_daa` turns into 0: `Par_CapitalCost` 12 rows
(incl. `D_Battery_Redox` — exactly the pattern that caused the NA Redox
flood), `Par_FixedCost` 17 rows, `Par_VariableCost` 2. Plus
`Par_TotalAnnualMaxCapacity`: **48 rows SPP × offshore wind with empty Value**
(SLA source) — blank in a bounds file is undefined behavior; SPP is landlocked
so the intent is presumably 0, but it must be explicit.

### 1.7 Duplicate/conflicting bound rows ✔
`Par_TotalAnnualMaxCapacity` `GR,D_PHS,All`: 0.125 (no source) vs 5.453
(E3M/Greek NECP) — delete the unsourced row. Verbatim duplicates (same value,
upsert hazard): `Canada,P_Biomass` 7× per year in Min+MaxCapacity (112 rows
each); 720 duplicated keys in `Par_TotalAnnualMaxActivity`; `Z_Import_LNG`
AF duplicated for 13 regions; SMR ramping row duplicated.

### 1.8 Trailing-space keys ✔
`Par_SpecifiedAnnualDemand`: 960 rows fuel `"Heat_Low_Industrial "` (trailing
space) vs 392 clean — 40 regions carry both spellings split by year.
`Par_ResidualCapacity`: 25 rows `"HD_Geothermal "`. If conversion doesn't
strip whitespace these rows land on nonexistent fuels/techs.

### 1.9 Interpolation/step artifacts in EU-legacy costs ✔(spot)
`HMHI_Steam_Electric` FOM: 1.056 (2030) → **0.000849 (2040)** → 0.477 (2045)
→ 0.952 (2050) — broken 2040 anchor (likely 0.849). Start-year steps from
partial re-sourcing: CCGT capex 600 (2018/20) → 935.8 (2021); Hydro_RoR FOM
76.8 → 8.9; OCGT FOM 20.7 → 8.4 (2025); HLI_H2_Boiler 650 → 56.7.
CHP mode-2 efficiencies >100% (WasteToEnergy 103%, CHP_Biomass_Solid 101%) —
full electric + full heat stacked in one mode. X_SOEC_Electrolysis
OperationalLife = 3 y (stack life, not plant) inflates its annuity ~7×.
(EU-side techs — no NA impact, but wrong.)

### 1.10 Dispatch data notes (agent, plausible — decide)
- `Par_DispatchVoLL.csv` writes US-source USD values 1:1 as EUR (MISO 10000,
  ERCOT 5000) while `Par_DispatchCO2Price.csv` converts at 0.9 — VoLL/ORDC
  ~11% high vs the repo convention. Convention decision, then align.
- PTC base −33 €/MWh derives from "$30/MWh"; published IRA PTC 2025 is
  27.5 USD → −31 €/MWh (~7% deep on every wind row). Offshore wind gets the
  PTC adder although US offshore predominantly elects the ITC (no per-MWh
  bid depression) — undocumented assumption.
- REFUTED: the reviewer's claim that `Par_DispatchFuelPriceYear.csv` mis-years
  the path — file matches the projection exactly (11.9/12.8/11.2/9.5/9.5,
  10.2 flat from 2030). No change.

### 1.11 Sentinels that survived the conditioning sweep (agent-verified counts)
`P_SOFC` = 999999 GW in all 9 US pools × 2025–2040 (144 rows) labeled with the
guardrail source string — contradicts the ramped SOFC GroupMaxNewCap and the
BigM cleanup; `Par_AnnualMaxNewCapacity` World,All = 999999;
`Par_AnnualEmissionLimit`/`Par_ModelPeriodEmissionLimit` = 999999 **Gt**
(6 orders of magnitude of BigM post Mt→Gt). NA workbook carries 8,960
999999-rows in AnnualMaxNewCapacity alone.

### 1.12 NA rows that are EU copies labeled dummy (agent)
`Par_ModelPeriodActivityMaxLimit`: `NewYork,R_Coal_Hardcoal` = 574,432 PJ (the
Poland value verbatim), `California,R_Coal_Lignite` = 541,500 PJ (the Germany
value) + 9 more "dummy data - empty entry" rows. `Par_TotalAnnualMaxActivity`:
1,324 NA-pool rows sourced "dummy data - empty entry" with real-looking
EU-copied values — **verify the real NA overlay on the data machine overrides
every one of these**. `Par_RegionalCCSLimit`: 10 NA rows marked dummy.

---

## 2. LCOE MODEL ↔ MODEL DATA (NA)

Units line up (MEUR/GW ≡ €/kW; both EUR — LCOE file is EUR real-2023).

### Aligned ✔
- Gas price 2025: dispatch 11.90 vs LCOE US Macro 11.92 €/MWh(th).
- Coal fuel: 7.92 vs 7.53–7.81 (+2–5%). OCGT efficiency 0.43 = LCOE 0.43.
- Nuclear VOM 6.90 vs 7; OCGT VOM 5.62 vs 6; nuclear eff 0.33 vs 0.31.
- Model regional/monthly gas basis + regional CO2 prices are *richer* than the
  LCOE file (which prices US CO2 = 0 — wrong for CA/RGGI/Canada; model wins).

### Open conflicts — decision needed
**2.1 Investment-model gas 2030+ is still the EU APS path**: Z_Import_Gas
17.28 €/MWh(th) 2030–35, 15.84 2040 vs the HH projection 10.2 — +55–70%. Was
the deliberate "dispatch-only for now" decision; the invest fleets were chosen
under this. Fixing 1.1 via option (a) would Americanize invest too — one
decision covering both.

**2.2 CAPEX: model (DEA/EU-Ref sources) sits far below the LCOE file's US
values** (€/kW, LCOE-US vs model, 2030): CCGT 2150 vs 883 (−59%); engines
3125 vs 950; coal 2352 vs 1650; PV utility 930 vs 380 (−59%; LCOE's own EIA
backup says 680); onshore wind 1531 vs 1150; offshore 4700 vs 3222;
geothermal 13,390 vs EGS tiers 4355–9329. Fixed OPEX same direction (OCGT
−65%, coal −55%, offshore −63…78%). Part is vintage (EUR-2023 US market vs
EU catalogues), but CCGT ×2.4 and PV ×2 exceed any deflator. **No US-market
capex source exists anywhere in the model data.** Needs an explicit
decision: adopt LCOE-US capex (as NA overlay CSVs on the data machine),
or document why DEA/EU stands.

**2.3 WACC**: model flat 5% for everything vs LCOE 5–8.5% tech-specific
(nuclear 8.5, CCGT 6.5, OCGT 7.5, offshore 7). At 8.5 vs 5% nuclear's
annualized capex differs ~+45% — the model structurally favors capital-heavy
techs relative to the LCOE frame. `Par_TechnologyDiscountRate` exists with
exactly 1 row — the mechanism is there, never filled.

**2.4 Structural**: LCOE has SOFC (1670 €/kW; model SOFC only via 999999
sentinel caps, no cost rows in NA) and no BESS/Oil/Hydro/SMR data (SMR = CF
only). CCGT VOM: model 4.57 vs LCOE 2 €/MWh; CCGT eff 0.56–0.58 vs 0.64
(LCOE aggressive fleet-average; partially offsetting in SRMC).

---

## 3. LCOE MODEL ↔ EU DATA (prep for country-level EU version)

Matches: OCGT capex within 4%, nuclear VOM/fuel/eff, SOFC efficiency, rooftop
PV 2030+.

Deltas an overwrite would apply (2030, LCOE vs current World rows): CCGT +25%,
coal +36%, onshore wind +36%, offshore +46%, PV utility +79%, rooftop
commercial +45%; FOM up drastically (OCGT ×2.7, coal ×5, wind ×3–4); CCGT VOM
−56%; CCGT efficiency → 0.64; gas fuel ~30 €/MWh flat vs the declining EU
path (+73% at 2030 — scenario disagreement, belongs in a scenario overlay,
not base).

**Do NOT overwrite from LCOE (broken/incompatible on the LCOE side):**
- Geothermal 19.3 k€/kW (different asset class than the 2.6 k conventional).
- Gas CCS: no capex adder (=unabated), capture 52% vs EU 92%, CCS WACC
  *below* unabated — inconsistent tech definition.
- Nuclear: planned (7–8 k) vs "real" (14–22 k, the file's own ×3 double-count)
  unresolved; EU's 10,000 was deliberately set 06/2026 between the two.
- SOFC 1670 vs EU's Bloom-sourced 6000 — 3.6× apart, opposite OPEX structure.
- Coal/oil/geothermal efficiencies, wind/coal VOM, Oil, Hydro, SMR, storage:
  "Input required" in LCOE — keep existing EU values.

Import prerequisite either way: bring LCOE WACCs along with LCOE capex
(2.3), or relative competitiveness shifts inside the import.

---

## 4. LCOE FILE INTERNAL ISSUES (feed back to file owners)

- **Stray 0.5 CAPEX multipliers live in 2025/26** (CAPEX_Config rows 23–40:
  All-regions SMR/PV/wind + all Denmark) — halves wind/PV real capex exactly
  in the years any 2025 comparison uses.
- Nuclear ×3.0/2.75 "real/planned" multiplier double-count → 22.2–22.8 k€/kW,
  LCOE 296–303 €/MWh vs the file's own US benchmark 95.6.
- CCS: WACC inversion (CCS below unabated, contradicts its own WACC Backup),
  no capex adder outside Germany, unabated emission factors on OCGT/coal/SOFC
  w/CCS rows.
- Coal LCOE never computes (efficiency blank); DE gas Macro 2040 = #REF!;
  Recip-engine efficiency 0.64 copied from CCGT; benchmark outliers (offshore
  DE 2024 = 0.125 €/MWh); SOFC summary tables mis-map tech names.
- 1,728/5,082 rows (34%) "Input required"; USA ISO subregions are empty
  shells; informal sources ("Sebastian, June 25", "Per Innovation team",
  "Internet + German learning curve") need hardening.

---

## 5. TODOS — sources & staleness (ranked)

Master table in the sweep (per-parameter): weakest-sourced parameters:
1. Par_ProductionChangeCost — 56/56 rows "Needs Update" (2023).
2. Par_RampingUp/DownFactor — 29/60 "Needs Update" each (industry/heat rows).
3. Par_ProductionGrowthLimit — 71% bare "Assumption".
4. Par_RegionalBaseYearProduction — 55% unsourced/dummy (+1 fully blank line).
5. Par_GrowthRateTradeCapacity — 47% dummy/assumption.
6. Par_TradeCapacityGrowthCosts — 41% (+ 2,214 rows with mojibake unit
   `Mâ‚¬/GW`, missing /km, 2.5–4.8× off the sourced cost basis; 1,466
   cross-continent NA↔EU dummy links; 186 self-pairs).
7. Par_SpecifiedAnnualDemand — 2,162 empty + 1,560 dummy-with-values rows;
   four mobility unit spellings (Mtkm rows that are actually Gtkm).
8. Par_EmissionActivityRatio — all CCS capture rates unsourced.
9. Par_ModalSplitByFuel — 3,620 dummy-flagged rows, 2,583 load-bearing.
10. Par_ResidualCapacity — 32% self-referential ("model run") + 661 "needs
    update"; 25 trailing-space keys.
Cost files: ~250–280 empty-Source rows each (EU-legacy vintage, "Updated at"
empty for ~1/3 of rows); entire 2055/2060 horizon = "same as 2050 for now"
(~250 rows/file).

Registry (`Overview_Sources.csv` / `Data/Sources/`): only 12 of 67 parameters
covered (2 name typos: `Par_TotalAnnualMaxAcitivity`, `Par_EmissionPenalty`;
4 `.xlxs` extension typos); 10 referenced files missing from Data/Sources, 10
on-disk files never referenced; `Overview_GENeSYS-MOD.csv` still says
Megatonnes for the Gt-converted emission parameters.

Misc: discount-rate/growth-limit Unit column says "Percent" for fraction
values; `Par_DistrictHeatSplit` unit says PJ for fractions;
`Par_StorageE2PRatio` S_Gas_Methane = 1 h (seasonal storage, implausible);
`Par_CapacityFactor` base CSV is header-only (CF entirely from timeseries —
confirm intentional); EmissionContentPerFuel has no rows for
Gas_Bio/Synth/H2/Biofuel (safe today via EAR=0, a trap for new techs);
Canada absent from Par_DispatchORDC + ReserveReq (intentional?); dispatch
TechClass doesn't map P_Biomass/CCS/H2 techs (fine at 2025 capacity ≈ 0,
undocumented); NY RGGI 2025 CO2 price (20 €) already below the Jun-2026
auction (38.6 USD); stale pre-v6 `input_*` dump in genesysmod_db.duckdb —
re-dump before anyone audits v6 inputs from the DB.

---

## 6. CONFIRMED FINE

- Dispatch CSVs: MinActivity exactly as designed (0.92/0.5/0.4/0.2/0.15,
  SOM/MMU-sourced); ORDC widths sum to 1, every step < regional VoLL, ERCOT
  inner 4500; StorageBins milestones sum to 1 and reproduce 1.5/2.55/3.5 h;
  CostBins fleet-mean multiplier ≈ 1.000 for every class; FuelPriceYear
  arithmetic exact vs 13.32 base; FuelCostFactor seasonal math checks (NE
  winter 2.4 → 1.31 annual); VoLL regional structure right (MISO 10000 top,
  ERCOT post-Uri 5000 — reviewer's "ERCOT should be max" expectation was
  outdated); CO2Price only in priced regions, correctly converted; all 11
  files fully sourced, region/tech names all valid.
- NA workbook v6 assumptions all landed: coal AF 0.45 (Canada 0.365), biomass
  11.2 GW + AF 0.5 + feasible activity floors (85% of ceiling), offshore
  minimum trajectories (NY 7.6/NE 5.6/PJM 7.0 GW 2040, Low-case ≤2030, zero
  2025), E2P path 1.5→3.5 h yearly-interpolated, EGS 4 tiers, gas 4-way split,
  residuals 2025 within ±7% of Benchmarks/ on every fuel (>15% rule: pass).
- Base CSV hygiene: units consistent per file; no negative costs; Min≤Max
  holds on all 3,072 capacity-bound pairs; group min≤max coherent (EGS,
  offshore); trade routes fully symmetric (1,344 rows); loss factors sane;
  NA IC bounds symmetric and complete (672 rows, Max≥Min everywhere);
  E2P overlays hit exactly 6.0/8.0 h at 2040; grid_high/low overlays carry
  the sensitivity in AnnualMaxTradeCapacity as designed.
- Emission units post Mt→Gt conversion verified (Gt/PJ values correct: gas
  5.58e-05, hardcoal 9.39e-05, lignite 1.108e-04); EmissionActivityRatio
  internally consistent (BECCS −0.88, DAC −1.0); LULUCF negative rows
  legitimate.
- Tech→fuel mappings clean across all 122 techs; thermal efficiencies in
  sane bands; COP>1 rows legitimate heat pumps; AF ∈ (0,1] everywhere, no
  thermal tech at 1.0.
- LCOE file: methodology internally consistent (formula audit reproduces),
  units clean EUR-2023, strong source blocks (WACC Backup/NREL-ATB, WoodMac
  CF, DESNZ coal, EIA AEO 2026, S&P/EEX CO2).
