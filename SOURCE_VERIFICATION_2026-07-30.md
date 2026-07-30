# Source Verification Campaign — 2026-07-30

Row-by-row verification of sourced CSV values against their cited source
documents. 16 per-source checker agents; bundles = anchor-year rows
(interpolations excluded), sampled at 160/source where larger; excluded as
verified-by-construction: this week's LCOE/cycling/trade imports and the
repo-internal funnel pipeline. ~1,600 rows directly checked, representing
~34k sourced rows.

## Verdict by source group

| Group | Rows | Result |
|---|---|---|
| US Pools + PMK (NA residuals/minima/demand) | 160 | ✅ 160/160 — pipeline re-run read-only, bit-for-bit reproduction + raw-cell checks |
| IC transfer capabilities (NA trade bounds) | 160 | ✅ 160/160 — formula re-implemented, exact; note: 47/85 Max rows are pace-capped (4%/yr), not raw NTP ceilings — source string understates this |
| TradeRoute distances | 160 | ✅ 160/160 geographic sanity (no further BE-NO-class bugs) |
| SLA offshore ceilings | 84 | ✅ 84/84 vs workbook |
| Coal price + coal AF basis | 58 | ✅ 58/58 — FX arithmetic exact; EIA fleet CF 42.1/42.5% verified; 0.45 documented headroom |
| DEA efficiencies/costs | 160 | ⚠ 109 match; **P_Oil capex was still wrong** (fixed → 361.5); storage rows cite the 2024 catalogue but match the older one; 2 low-confidence unreconciled |
| ENTSO-E capacities (EU residuals) | 160 | ⚠ 85 match; PV "mismatches" are mostly the resource-class split artifact (see §3); real flags: FR P_Oil 6.2 vs ~2.9 GW, CH reservoir vs pumped split |
| WindEurope (EU wind residuals) | 160 | ⚠ real bugs: **RO offshore 0.632 GW in 2020 (Romania has zero offshore)**, SI offshore 6 MW (none exists); CZ +42%/PL −20% onshore 2020 (2018 anchor held flat); year-basis citation gap |
| UNFCCC CRT (exogenous emissions) | 120 | ⚠ **GR = UK byte-identical trajectories (row-copy bug; GR inflated ~5-8×)**; rest = derivation opacity (parameter is blended non-modeled sectors, not pure LULUCF — checker's sign-flip claims mostly a benchmark mismatch, but derivation is unreproducible from the citation) |
| TYNDP 2022 (commissioned H2 corridors) | 160 | ⚠ inconsistent: some corridors copy Annex C2 verbatim (conversion ×1.314 exact), 11 corridors zero where Annex C2 is nonzero. Annex C2 disclaims commercial availability, so zeros are defensible — but then the copied rows aren't. Needs one consistent rule |
| Ember (EU interconnector growth rates) | 160 | ❌ **0.016 flat on 122 borders cites a national-grid-km stat from a report that explicitly excludes interconnectors**; Ember's own NTC data implies median ~4.2%/yr — EU interconnector growth likely 2.5-4× too slow |
| EU Transport Pocketbook (modal splits) | 160 | ⚠ air shares partly only reproducible by counting overflown transit (HU); road splits ±5-10%; 77% of rows keyed to years the source cannot contain; citation lacks edition/table |
| Biomass Futures atlas (EU potentials) | 160 | ⚠ paper/cardboard rows 2-8× off the atlas tables (PL 7× low); **geothermal rows cite a biomass-only atlas**; 66% of rows keyed to years the atlas doesn't have |
| EAFO (EV fleet shares) | 150 | ⚠ values are plausibly BEV+PHEV-only but cite the AFO "AF Fleet %" metric that includes LPG/CNG → 7-70× apparent gap in gas-fleet countries; citation fix, values likely intended |
| Beyond Fossil Fuels (coal exit AFs) | 160 | ⚠ **IE stale: Ireland coal-free since 2025-06, model keeps 80% availability through 2029**; dead `IR` region series (not in set) carries the CORRECT data — region-code migration leftover; ES zeroed 2025 vs tracker's 2030 Alcúdia remainder (mainland exit real; minor) |
| Long tail (120-row sample of 438 sources) | 120 | ⚠ 4 finds: lignite VC matches "conventional" row while citing "supercritical" (0.833 vs 1.13); HB_Lignite VC 3× below cited row; FRT_Road_LNG 2040 pulled the 2035 column; NONEU_Balkan demand labeled "no development" but declines 8.6%. ~45 unverifiable (PDF access limits) |

## 1. Fixed immediately

- **P_Oil capex → 361.5 MEUR/GW** (all years; DEA "50 Diesel engine farm"
  0.361547 MEUR/MW flat — the 2026-07-23 decimal-shift fix was itself wrong).

## 2. Proposed fixes (awaiting decision)

1. RO + SI offshore-wind residuals → 0 (phantom capacity; EU-side).
2. IE coal AF: add explicit 2025 zero row (Moneypoint closed 2025-06);
   delete or merge the dead `IR` series (its data is the correct one).
3. GR exogenous emissions: rebuild from the CRT derivation (currently = UK
   row copy, ~5-8× too high); derivation itself needs documenting.
4. FR P_Oil residual 6.2 → ~2.9 GW (RTE/EC), unless mothballed units are
   deliberately counted.
5. Longtail quartet: lignite VC citation-vs-value (pick supercritical 1.13
   or relabel to conventional), HB_Lignite VC 0.147 vs cited 0.436,
   FRT_Road_LNG 2040 off-by-one-year, NONEU_Balkan label.
6. Ember growth rates (EU): decide basis — per-border rates from Ember's
   NTC dataset (median ~4.2%/yr) or a corrected flat value; current 0.016
   with that citation is indefensible.
7. TYNDP commissioned-H2 rule: zeros everywhere (Annex C2 = modeling
   figures, not commitments) or Annex C2 Level-1 everywhere — one rule.
8. CZ/PL onshore-wind 2020 anchors (2018 values held flat): refresh from
   the correct edition.

## 3. Interpretation notes (NOT bugs)

- PV/wind resource classes: `P_PV_Utility_Avg` is one of three utility
  classes (+ rooftop separately); checkers comparing one class against
  national totals over-flag. The class-split shares themselves are a
  documented convention.
- 2025+ rows citing historical statistics are projections anchored on the
  statistic — legitimate, but the Source field should say
  "anchored on <year>, extrapolated" (systematic doc gap across WindEurope/
  Pocketbook/atlas/ENTSO-E groups).
- Exogenous emissions = all non-modeled sectors (agriculture/waste/IPPU/
  LULUCF blended); positive 2025 values are not sign errors.

## 4. Systemic recommendations

1. Source strings for derived rows should name anchor year + derivation
   ("X 2018 anchor, linear retirement", "pace-capped at 4%/yr").
2. Pin live-dashboard sources (EAFO, trackers) with an as-of date.
3. The gas CCGT/OCGT/engine split of EU residuals needs its actual
   (uncited) plant-level source named.
4. DEA storage rows: align citation to the catalogue vintage actually used.
