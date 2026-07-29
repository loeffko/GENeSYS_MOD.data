# LCOE Model FEL26 v1.4 — Issues & Improvement List

**File reviewed:** `260618 LCOE_Model_FEL26_v1.4.xlsx` (v1.4, dated 2026-06-18)
**Review date:** 2026-07-23
**Context:** The file's cost data (planned CAPEX, Fixed OPEX, WACC, US gas
path) has been imported into the GENeSYS-MOD data pipeline (source label
"FEL2026 LCOE Model file V1.4, dated 2026-06-18"). The items below were found
during that import; items marked **[blocked import]** caused us to skip the
affected data, so fixing them unlocks a more complete import later.

The overall methodology is sound: the LCOE formula documentation matches the
implementation, arithmetic reproduces (spot-checked CRF, fuel-cost and
coal-price conversions), units are consistently EUR real-2023, and several
blocks are well-sourced (WACC backup with NREL ATB / EIA / IRENA / Lazard
links, WoodMac capacity factors, DESNZ coal, EIA AEO 2026 US coal, S&P/EEX
CO2). The issues are fixable data and configuration errors, not structural
problems.

---

## 1. Errors that corrupt current results

1. **Stray 0.5 CAPEX multipliers are live in 2025/2026** (`CAPEX_Config`
   rows 23–40: "All regions" SMR, Solar PV, Wind Onshore, Wind Offshore, SOFC
   and all Denmark technologies). Real CAPEX for e.g. All-regions Wind
   Onshore runs 1672 → **854 → 817** → 1612 €/kW across 2024–2027 — an
   obvious test leftover that halves wind/PV capex exactly in the years most
   comparisons use. *We ignored all multipliers except the PV-utility
   learning curve during import.* **[blocked import for 2025/26 "real" CAPEX]**

2. **Nuclear "real/planned" multiplier double-counts market escalation**
   (×3.0 USA / ×2.75 All-regions on planned 7.6–8.1 k€/kW): real CAPEX
   becomes **22.2–22.8 k€/kW (2024)** and the calculated USA nuclear LCOE
   (296–303 €/MWh) is ~3× the file's own USA benchmark LCOE (95.6 €/MWh).
   Even Vogtle came in around 13.7 k€/kW. Either the planned CAPEX should be
   overnight cost with the multiplier representing financing/escalation
   (then ~1.5–1.8), or the multiplier should go. **[blocked import — nuclear
   not imported at all; the model keeps its deliberate 10 000 €/kW
   assumption]**

3. **CCS configuration is internally inconsistent:**
   - CCS WACC (0.045 for gas CCGT/OCGT w/CCS) is *below* the unabated WACC
     (0.065/0.075) and contradicts the file's own `WACC Backup` sheet
     (gas-CCS 0.085–0.09, coal-CCS 0.095–0.10).
   - No CCS CAPEX adder outside Germany: USA/All-regions "With CCS" CAPEX =
     unabated (2150/1100 €/kW).
   - "With CCS" emission factors for OCGT, Coal and SOFC equal the unabated
     values (0.535 / 0.9385 / 0.336 t/MWh) — capture has zero effect; only
     CCGT has a reduced factor (0.175).
   **[blocked import — no CCS data imported]**

4. **Coal LCOE never computes**: coal (and oil, geothermal) efficiency is
   blank in `Efficiency_Config`, so fuel costs and "LCOE (calculated)" are
   blank for every coal row in `Calculation_Wide`. The `Customized_LCOE`
   sheet reports coal 174.5 €/MWh with fuel price 0 and efficiency 1 —
   fuel-excluded, which the label does not say.

5. **Recip-engine efficiency 0.64 is a CCGT copy** (real recip engines
   ~0.42–0.48 LHV). CAPEX/FOM (3125 / 29) look right and were imported;
   the efficiency was not.

6. **`Gas price` sheet, DE Macro 2040 = `#REF!`** (the 2040 EU gas price is
   broken; `Source_Input_Wide` carries 30 €/MWh instead). Also the
   "CAPEX Gas" backup block has a broken OCGT ramp (91 → 730 €/kW over
   2033–2040 with 2024–2032 empty).

7. **Label/mapping bugs:** CO2-cost rows of emitting technologies carry the
   source "Non-emitting technology" while holding 65.6–135.3 €/t; the
   SOFC EU/US summary tables map values to wrong technology names (e.g. the
   value labelled "Gas OCGT 161" is the Recip Engine, "Coal 145.4" is SOFC
   Bloom); offshore-wind benchmark LCOE Germany 2024 = 0.125 €/MWh and the
   PV Resid/Comm benchmark is a −1 sentinel.

## 2. Missing inputs (34 % of the input matrix)

- **1,728 of 5,082 rows are "Input required"** — 75–90 per country; each USA
  ISO subregion (CAISO/ERCOT/MISO/NYISO/PJM) is an ~empty shell (90 missing
  rows each) although the region rows exist.
- Fully missing technologies: **Oil (all inputs, all regions), Hydro River,
  Hydro Pump-storage, SMR** (only CF = 0.85 "Same as Nuclear"), the "Solar
  PV" placeholder row. **BESS does not exist in the model at all** (only a
  WACC-backup row) — the single biggest gap for power-system use.
- Missing KPIs: wind Variable OPEX, coal Variable OPEX, coal/oil/geothermal
  efficiencies, oil emission factors.
- `Formula_Audit` has three open items with no status: "Check Jeffries",
  "CAPEX OCGT", "Add CO2 based on efficiency (as in 1.1 model)".

## 3. Source hardening

Informal sources that should be replaced with citable references:
"Sebastian, June 25, 2026" (PV + coal WACC), "Per Innovation team" (SOFC),
"Per discussion on June 9, KOL + SLA + RK" (SOFC WACC), "Internet + German
learning curve" (US residential PV CAPEX), "GS" e-mail ranges (CCGT CAPEX),
SE-internal SharePoint links (gas price macro). Empty source cells on
Coal/Geothermal lifetime and Coal-w/CCS WACC.

Mixed vintages in one column set: "IEA WEO 2026 Annex B" (PV, geothermal
benchmark) next to "IEA WEO 2025 Annex B" (coal, geothermal costs); the
`Opex` backup says USA CCGT FOM 50→40 €/kW/yr while `Source_Input_Wide` uses
32 flat; `CAPEX PV Backup` carries EIA 680.6 €/kW vs the 930 used — worth an
explicit decision note per tech.

## 4. Questions from the model-side comparison (no file change needed, but
worth an answer)

- **US CO2 price = 0** is wrong for California (CARB, ~28 USD/t), the RGGI
  states (NY/NE, auction 72 cleared 38.6 USD/t in Jun-2026) and Canada
  (OBPS ~CAD 95). Our dispatch layer prices these; the LCOE file prices no
  US carbon anywhere. Intentional simplification?
- **Geothermal 13.4–19.3 k€/kW (IEA WEO Annex B)** describes a different
  asset class than conventional/EGS geothermal (2.6–9.3 k€/kW in our data,
  consistent with DEA and EGS literature). Which asset is the file's
  geothermal row supposed to represent?
- **SOFC 1670 €/kW ("Assumption for SE' SOFC")** vs the Bloom installed-cost
  basis we carry (≈6 000 €/kW 2025, sourced 2026-07-04): 3.6× apart, and the
  OPEX structure is opposite (LCOE: all-variable 13.1 €/MWh; ours: fixed
  140 €/kW/yr). Needs a joint decision on which SOFC is "the" SOFC.
- CCGT efficiency 0.64 flat is new-plant LHV best-in-class; a fleet-average
  (0.55–0.59, improving over time) prices realistic dispatch. Fine for
  device-level LCOE, misleading if the file is read as fleet economics.

## 5. What was imported into GENeSYS-MOD (for reference)

| Block | Scope | Notes |
|---|---|---|
| Planned CAPEX | CCGT, OCGT, recip engines, coal, PV utility (× learning multiplier), PV rooftop, onshore wind, offshore wind | US column → NA regions; "All regions" column → EU (World rows). Offshore anchored on the Transitional class, depth spread preserved. |
| Fixed OPEX | same technology set | |
| WACC | per-technology, incl. nuclear/SMR/EGS/SOFC | US and EU columns respectively; CCS WACCs skipped (issue 3) |
| US gas price | "Fuel costs" series (HH macro, 11.9 → 10.2 €/MWh th) | now drives the investment model; dispatch year-multiplier retired |
| Not imported | nuclear & SMR CAPEX/FOM, geothermal, SOFC costs, all CCS, oil/hydro/storage, VOM, efficiencies, EU fuel prices | reasons in sections 1–2 |
