"""US biomass power fleet (P_Biomass) — historic residual, no growth.

Writes the nine US-pool P_Biomass rows into the BASE parameter CSVs
(idempotent: existing US-pool P_Biomass rows are replaced):
  Par_ResidualCapacity       net-summer capacity, FLAT 2025-2040 (assumption:
                             biomass power does not grow significantly)
  Par_TotalAnnualMaxCapacity = residual (no endogenous build)
  Par_AvailabilityFactor     0.5 (EIA 2024 fleet CF ~46% on net-summer basis;
                             AF acts as the annual fleet-CF cap in the model)
Canada is NOT touched: its P_Biomass rows come from the CER block in
add_capacity_bounds.py. add_capacity_bounds exempts P_Biomass from the
unmanaged-tech forbid net (EXTERNAL_OWNERS) so these rows survive rebuilds.

Capacities: EIA-860 existing capacity by state 2024 (Wood and Wood Derived
Fuels + Other Biomass, Total Electric Power Industry, net summer), states
mapped to pools. US mapped total 11.3 GW / 46.2 TWh (2024).

Run:  python NA_inputs/add_biomass_fleet.py --apply
"""
import os, sys
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_REPO = os.path.normpath(os.path.join(HERE, ".."))
PARAMS = os.path.join(DATA_REPO, "Data", "Parameters")
apply = "--apply" in sys.argv

YEARS = list(range(2025, 2041))
DATE, WHO = "2026-07-13", "Konstantin Loffler <kl@wip.tu-berlin.de>"
SRC = "EIA-860/923 2024 by state (wood + other biomass, net summer), state->pool mapping; flat (no-growth assumption)"

BIOMASS_GW = {  # net-summer, 2024
    "California": 1.0, "WECC": 0.7, "SPP": 0.1, "MISO": 1.9, "ERCOT": 0.3,
    "SERC": 4.0, "PJM": 1.6, "NewYork": 0.4, "NewEngland": 1.2,
}
BIOMASS_AF = 0.5   # EIA 2024 fleet CF ~46% (net-summer basis); slight upside allowed


def upsert(param, rows, cols):
    path = os.path.join(PARAMS, param, param + ".csv")
    d = pd.read_csv(path)
    d = d.rename(columns={c: "" for c in d.columns if str(c).startswith("Unnamed")})
    drop = (d.Technology == "P_Biomass") & d.Region.isin(BIOMASS_GW)
    nd = int(drop.sum())
    d = d[~drop]
    add = pd.DataFrame(rows)
    for c in d.columns:
        if c not in add.columns:
            add[c] = ""
    d = pd.concat([d, add[d.columns]], ignore_index=True)
    if apply:
        d.to_csv(path, index=False, lineterminator="\n")
    print(f"{param}: -{nd} old / +{len(rows)} rows")


# Activity floor: biomass is CHP-/contract-driven must-run in reality (steam
# hosts, PPAs) - at ~39 EUR/MWh SRMC it idles in the merit order almost
# everywhere, so without a floor the fleet generates ~0 (only ERCOT ran).
# Floor = 90% of EIA-923 2024 generation, flat (persistence, slight decline ok).
BIOMASS_GEN_TWH = {  # EIA-923 2024 by state -> pool
    "California": 4.8, "WECC": 3.1, "SPP": 0.5, "MISO": 7.7, "ERCOT": 0.9,
    "SERC": 17.0, "PJM": 6.3, "NewYork": 1.6, "NewEngland": 4.4,
}
BIOMASS_GEN_FLOOR = 0.9

res_rows, max_rows, af_rows, act_rows = [], [], [], []
for r, gw in BIOMASS_GW.items():
    for y in YEARS:
        res_rows.append(dict(Region=r, Technology="P_Biomass", Year=y, Value=gw,
                             Unit="GW", Source=SRC, **{"Updated at": DATE, "Updated by": WHO}))
        max_rows.append(dict(Region=r, Technology="P_Biomass", Year=y, Value=gw,
                             Unit="GW", Source=SRC + "; max = residual (no growth)",
                             **{"Updated at": DATE, "Updated by": WHO}))
    af_rows.append(dict(Region=r, Technology="P_Biomass", Year="All", Value=BIOMASS_AF,
                        Unit="share", Source="EIA 2024 biomass fleet CF ~46%; AF = annual CF cap",
                        **{"Updated at": DATE, "Updated by": WHO}))

for r, twh in BIOMASS_GEN_TWH.items():
    for y in YEARS:
        act_rows.append(dict(Region=r, Technology="P_Biomass", Year=y,
                             Value=round(twh * 3.6 * BIOMASS_GEN_FLOOR, 3), Unit="PJ",
                             Source="EIA-923 2024 biomass gen x0.9 (CHP/contract must-run persistence; no-growth)",
                             **{"Updated at": DATE, "Updated by": WHO}))

upsert("Par_ResidualCapacity", res_rows, None)
upsert("Par_TotalAnnualMaxCapacity", max_rows, None)
upsert("Par_AvailabilityFactor", af_rows, None)
upsert("Par_TotalAnnualMinActivity", act_rows, None)
print(f"US biomass fleet: {sum(BIOMASS_GW.values()):.1f} GW flat, AF {BIOMASS_AF}"
      + ("  APPLIED" if apply else "  DRY-RUN"))
