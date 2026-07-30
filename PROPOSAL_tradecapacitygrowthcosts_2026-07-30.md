# Proposal — Par_TradeCapacityGrowthCosts overhaul (land/subsea classes, all fuels)

Research 2026-07-30: ACER Unit Investment Cost indicators (2015 gas / 2023 /
2026 editions), MISO Transmission Cost Estimation Guide MTEP24, Härtel et al.
2017 (HVDC cost regression), realized subsea links (NordLink, Viking Link,
NeuConnect), European Hydrogen Backbone 2022, DeSantis 2021 + Saadi 2018
verification, OGJ/EPA US pipeline actuals, biomass logistics literature.
Pair classification from Par_TradeRoute geography (agent-verified).

Decision context: the per-pair structure is KEPT (no collapse to a single
factor per fuel) — land vs subsea drives 2–4× cost differences.

## 0. What the current values turned out to be

- Power 0.864 M€/GWkm (DeSantis, most EU rows) = US 500 kV land-HVDC
  **including converter stations**, loss-adjusted (Black & Veatch/WECC
  basis). Defensible land value.
- Power 0.445 (Saadi, the 42 NA rows) = HVDC **line-only — converters
  excluded** (DeSantis states this explicitly and puts its own line cost
  ~70% higher). Undercounts every real link; coincidentally matches EU AC
  thermal-basis costs.
- Power 2.1425 mojibake rows ("needs update", German pairs) = unsourced,
  unit broken (missing /km).
- Gas 0.0018 M€/PJkm reproduces DeSantis exactly — but that is the cheapest
  cost regression in the literature (Rui et al., 1992–2008 US builds);
  post-2015 actuals (OGJ, ACER 2026) run 3–5× higher.
- H2 0.0049 does NOT reproduce its cited source (DeSantis 36" gives 0.0031);
  back-solves to an undocumented ~1.6× uplift. EHB 2022 large-corridor
  new-build incl. compression is 0.0083.
- Biomass 0.0039: no citable per-km capacity capex exists anywhere; the real
  logistics cost sits in Par_TradeCostFactor. Placeholder is the honest
  choice, now documented.

## 1. Proposed values

**Power — M€/GW/km (EUR ≈ 2024):**

| Class | Value | Basis |
|---|--:|---|
| EU land | **0.86** (keep) | DeSantis land-HVDC incl. converters; consistent with ACER 2026 AC on firm-capacity basis (~0.9) and land-HVDC all-in 0.9–1.3 |
| EU subsea | **1.70** | realized 1.4–2 GW links all-in 1.7–2.8 (NordLink/Viking/NeuConnect); modern 2 GW cable+converter folding 1.3–2.1 at 300–700 km; ACER escalation warning |
| EU mixed | per-pair: DE-DK 1.3 · FI-SE 1.3 · IE-UK 1.7 · ES-FR 1.0 | corridor judgment (documented per pair) |
| NA land | **1.00** (was 0.445) | MISO MTEP24: AC 0.88–1.03 (incl. 30% contingency + AFUDC), long-corridor HVDC all-in 1.2–1.7; Saadi line-only basis corrected |

**Gas_Natural — M€/(PJ/yr)/km** (model gas capacity is PJ-denominated; GW
equivalents in Assumptions.txt):

| Class | Value | Basis |
|---|--:|---|
| Onshore | **0.003** (was 0.0018) | ACER 2015 large-diameter EU actuals 0.0027 + escalation; recent actuals 0.005–0.009 bound above |
| Subsea | **0.006** | EHB offshore factor 1.7×; Nord Stream realized 0.0031 = giant-scale floor |

**H2 — M€/(PJ/yr)/km:**

| Class | Value | Basis |
|---|--:|---|
| Onshore new | **0.008** (was 0.0049) | EHB 2022 48"/36" new-build incl. compression (0.0068–0.017); current value cites DeSantis but doesn't reproduce it |
| Subsea new | **0.018** | EHB offshore new incl. compression 0.012–0.029 |
| (Repurposed class) | 0.003–0.005 | EHB; NOT modelled today — flagged as a large EU-corridor lever for later |

**Biomass — M€/(PJ/yr)/km:** keep **0.0039**, relabeled "nominal
terminals/rolling-stock proxy (no citable per-km capacity capex; logistics
cost lives in Par_TradeCostFactor)"; rolling-stock back-of-envelope supports
0.001–0.002, same order.

## 2. Pair classification (from Par_TradeRoute, 122 All-pairs + 19 NA Power)

- SUBSEA (27 pairs, applied to Power AND Gas/H2): BE-NO, BE-UK, DE-FI,
  DE-NO, DE-SE, DE-UK, DE_MV-DK, DK-NL, DK-NO, DK-SE, DK-UK, EE-FI, ES-IT,
  FR-IE, FR-NO, FR-UK, GR-IT, IT-NONEU_Balkan, LT-SE, NL-NO, NL-UK, NO-UK,
  PL-SE + offshore-hub pairs DE_Baltic-DE_MV, DE_Baltic-DE_SH,
  DE_NI-DE_Nord, DE_Nord-DE_SH.
- MIXED (4): DE-DK, FI-SE, IE-UK, ES-FR (per-pair values above; for gas,
  DE-DK = land (DEUDAN), IE-UK = subsea (Moffat), ES-FR = land existing /
  subsea for H2 (H2Med) — H2 ES-FR gets subsea).
- LAND: everything else (incl. all NA pairs).

## 3. Cleanups bundled in

- Self-pairs: DONE (186 removed + 228 in Par_GrowthRateTradeCapacity).
- Cross-continent NA↔EU dummy rows (1,644): DELETE (physically meaningless;
  inert since conversions region-filter, but bloat + trap).
- Mojibake unit rows (`Mâ‚¬/GW`): superseded by re-valuation; unit column
  normalized to `M€/GWkm` (Power) / `M€/PJkm` (fuels).
- Par_TradeRoute bug: BE-NO + FR-NO Power rows carry 0 km (their All-rows
  say 1294/1851 km) — fix to the All-row distances.
- Flag (not fixed here): DE_Baltic/DE_Nord offshore hubs inherit Gas/H2
  routes via Fuel='All' — likely unintended, needs a set-level decision.

## 4. Impact warning (NA)

NA land Power 0.445 → 1.00 M€/GW/km more than doubles interconnector
expansion cost in the NA model. grid_high/grid_low sensitivity spreads will
compress; the v6 finding "wires dominant lever" weakens in v7. This is a
data-correctness fix (line-only basis excluded converters), not a scenario
choice — but it materially moves results.

## 5. Currency note

Mixed vintages (ACER real-€2025, EHB ≈€2021, MISO US$2023, DeSantis $2017)
— values rounded to the coarse class level where vintage differences are
within rounding; ACER 2026 documents >6%/yr real escalation since 2018, so
these are, if anything, conservative.
