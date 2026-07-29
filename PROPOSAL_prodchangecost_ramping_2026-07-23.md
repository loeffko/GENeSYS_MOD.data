# Proposal — Par_ProductionChangeCost re-sourcing + HB/HLI/HMHI/HHI ramping factors

Research 2026-07-23 (six literature sweeps; PDFs in `Data/Sources/`, registered
in `Overview_Sources.csv`). Values below are PROPOSED — not yet applied.

## A. What the research established

1. **Heritage**: the current 20/50/100/200 €/MWh pattern is the dynELMOD
   `Cload` construction (Gerbaulet & Lorenz 2017, DIW DD88): EUR per MWh
   applied to `g_up + g_down`, deliberately set "slightly higher than in a
   unit commitment model" to proxy start costs the LP cannot see. Sourced to
   Schröder et al. 2013 (DIW DD68) → Kumar et al. 2012 (NREL/SR-5500-55433).
   The specific values match no printed table in any of these.
2. **Wear-only anchors** (Kumar 2012, $2011, lower bounds, per MW of swing —
   dividing the per-event cost by typical swing depth): gas CC ~3.2, aero CT
   ~3.2, frame CT ~5.9, gas steam ~6.0, coal ~7–10. Start costs (hot/cold,
   $/MW): CC 35/79, frame CT 32/103, gas steam 36/75, coal 54–94/104–147 —
   the upper envelope the LP mark-up proxies.
3. **Unsupported current entries**: nuclear 200 (NEA 2011 + EDF fleet data:
   wear is small — EDF's itemized flexible-ops maintenance ≈ 2–3 €/MWh of
   swing; the big literature numbers are lost load factor, not wear);
   oil/biomass 100 (DEA: biomass cycling ≈ coal-like; oil steam ≈ gas steam);
   hydro 50 (literature prices per START, $200–900; water opportunity cost is
   endogenous in the model); engines 20 (DEA start cost 0 €/MW; Wärtsilä
   LTSAs bill running hours, not starts).
4. **Missing rows** (dispatchable techs currently cycling for FREE):
   P_Gas_Steam, P_H2_OCGT, CHP_WasteToEnergy, CHP_Hydrogen_FuelCell.
5. **Resolution caveat**: the parameter multiplies per-timeslice energy
   deltas. Values below are stated per MWh of swing at HOURLY dispatch. At
   the NA investment resolution (49-h slices) one MW of level change carries
   49 h of energy, so per-MW-swing the charge is 49×— defensible as a proxy
   for unmodeled intra-block cycling, but it must stay a documented
   convention (dynELMOD had the same property).

## B. Proposed Par_ProductionChangeCost

Unit fix included: column says "M€" → "M€/PJ". Conversion: €/MWh-swing ×
0.277778 = M€/PJ. Convention kept: wear cost ×~3 mark-up as start-cost proxy
(dynELMOD logic, now explicit in Assumptions.txt).

| Tech group | now €/MWh | proposed €/MWh | proposed M€/PJ | basis |
|---|--:|--:|--:|---|
| P_Gas_CCGT, _Residual, P_Gas_CCS, CHP_Gas_CCGT_* | 20 | **10** | 2.778 | Kumar wear ~3.2 + start 35–79 $/MW |
| P_Gas_OCGT, P_H2_OCGT (new row) | 20/— | **10** | 2.778 | frame-CT wear ~5.9; DEA OCGT start 43 €/MW |
| P_Gas_Engines | 20 | **2** | 0.556 | DEA start 0; hours-based maintenance |
| P_Gas_Steam (new row) | — | **15** | 4.167 | gas-steam wear ~6.0, starts 36–75 |
| P_Coal_Hardcoal (+CCS, CHP) | 50 | **25** | 6.944 | wear 7–10, starts 54–147; Borrero 2023: real-world ≥ engineering |
| P_Coal_Lignite (+CCS, CHP) | 50 | **30** | 8.333 | thick-walled, DD68 lignite start 2× hardcoal (Ehlers/PJM) |
| P_Biomass (+CCS, CHP_Biomass_Solid*) | 100 | **25** | 6.944 | DEA: coal→biomass rebuild "start-up costs will not change much" |
| CHP_WasteToEnergy (new row) | — | **30** | 8.333 | DEA WtE grate: 70% min load, 8 h warm start |
| P_Oil, CHP_Oil | 100 | **15** | 4.167 | oil steam ≈ gas steam class |
| HB/HLI_Oil_Boiler | 100 | **0** | 0 | burner-modulated boiler — no cycling wear (drop rows) |
| P_Nuclear, P_Nuclear_SMR | 200 | **20** | 5.556 | EDF itemized wear 2–3 €/MWh-swing + ops burden + start-fuel proxy (DP1540 all-in cold ~250 €/MW); NEA: ageing "within design margins" |
| P_Hydro_Reservoir | 50 | **5** | 1.389 | wear is per-start and small; water value endogenous |
| CHP_Hydrogen_FuelCell (new row) | — | **2** | 0.556 | electrochemical, no thermal cycling wear |
| HHI_BF_BOF, _CCS, Bio_BF_BOF | 100 | **100** (keep) | 27.778 | continuous process, day-scale rescheduling only (Feta 2018) — deterrent consistent with 0.05 ramp |
| HHI_DRI_EAF, _CCS, H2DRI_EAF | 100 | **30** | 8.333 | shaft-furnace modulation τ≈1.27 h; H2/HBI buffers (Ji 2026, Vogl 2018) |
| HHI_Scrap_EAF | 100 | **10** | 2.778 | batch, reserve-prequalified (Paulus & Borggrefe 2011) |
| HHI_Molten_Electrolysis | 100 | **100** (keep) | 27.778 | continuous 1600 °C; smelter analogy (judgment) |
| HB_*/HLI_* boilers (rest), HMHI_* | 0 | **0** (keep) | 0 | no cycling wear at boiler level |

## C. Proposed RampingUp/DownFactor (the 29 stale rows; symmetric)

Convention as power side: fraction of capacity per hour, literature halved;
0 = deliberately unconstrained (relabel from "Needs Update").

| Tech | now | proposed | basis |
|---|--:|--:|---|
| HB_* (all 7: gas/oil/H2/electric/coal/lignite/biomass) | 0 | **0** (relabel) | DEA: boilers full range ≤ minutes (gas warm start 6 min, electrode 100%/min, biomass 10%/min) |
| HLI_Gas/H2/Oil_Boiler, Direct_Electric, Biomass | 0 | **0** (relabel) | same |
| HLI_Hardcoal / HLI_Lignite | 0 | **0.45 / 0.30** | alignment with power-side coal (judgment; DEA-only reading would leave 0) |
| HMHI_Gas, _Gas_CCS, _Oil, _Steam_Electric | 0 | **0** (relabel) | burner/electrode modulation; kiln inertia is process-side |
| HMHI_HardCoal, _HardCoal_CCS | 0 | **0.45** | chain-grate/PF 1–5 %/min class, halved |
| HMHI_Biomass | 0 | **0.45** | grate ≈ coal class |
| HHI_BF_BOF, _CCS, Bio_BF_BOF | 0.1 | **0.05** | Tata IJmuiden: hourly modulation "not realistic"; banking = days (Feta 2018) |
| HHI_DRI_EAF, _CCS, H2DRI_EAF | 0.1 | **0.20** | τ = 1.27 h first-order → ~55%/h realized, halved ~0.25 → 0.20 |
| HHI_Scrap_EAF | 0.1 | **1.0** | batch; full range within the hour (explicit 1.0 documents intent) |
| HHI_Molten_Electrolysis | 0.1 | **0.10** (keep, relabel) | smelter-analogy ±25%/h band, halved (judgment) |

## D. On apply (per repo convention)

- `Par_ProductionChangeCost/Assumptions.txt`: dynELMOD-heritage construction,
  wear ×3 start-proxy mark-up, €/MWh-swing × 0.277778 → M€/PJ, currency
  bases (Kumar $2011, DEA €2015, EDF €2025 — treated as ±rounding, values
  rounded to 5s), hourly-swing basis + 49-h-slice caveat, engineering-
  judgment entries flagged (WtE, fuel cell, MOE, BF-BOF deterrent).
- `Par_RampingUpFactor/Assumptions.txt` + `DownFactor`: DEA v0017 "secondary
  regulation %/min" basis, halving convention, 0 = deliberately
  unconstrained, judgment entries flagged (HLI coal alignment, MOE).
- Sources already filed: Kumar2012, Schroeder2013 (DD68), GerbauletLorenz2017
  (DD88), Lew2013 (WWSIS2), Agora2017, SchillPahleGambardella2016 (DP1540),
  OECD-NEA2011, DEA catalogue v0009 PDF. Steel/DR papers are paywalled/web —
  cited by URL in Assumptions.txt, no PDFs to file.
