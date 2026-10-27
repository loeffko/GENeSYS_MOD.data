# -*- coding: utf-8 -*-
"""Replace Par_RampingUpFactor + Par_RampingDownFactor entries for power-sector
technologies with calibrated "real-world / 2 (perfect-foresight discount)" values.

Mapping applies the same factor to both up and down (symmetric ramping) and to
CHP variants that mirror the thermal counterpart.
"""
import csv
import os

HERE = os.path.dirname(os.path.abspath(__file__))
RU = os.path.join(HERE, "Data", "Parameters", "Par_RampingUpFactor",   "Par_RampingUpFactor.csv")
RD = os.path.join(HERE, "Data", "Parameters", "Par_RampingDownFactor", "Par_RampingDownFactor.csv")

STAMP = "2026-06-02"
AUTHOR = "Konstantin Loffler <kl@wip.tu-berlin.de>"
SOURCE = ("Real-world plant ramping (Brouwer 2015, EPRI, IRENA, DEA Tech Cat) "
          "halved for perfect-foresight assumption")

# Per-tech factor (fraction of capacity per effective TS step; with hourstep=1
# this approximates per-hour ramp). CHP variants mirror their thermal class.
FACTORS = {
    # Coal
    "P_Coal_Hardcoal":              0.45,
    "P_Coal_Hardcoal_CCS":          0.45,
    "P_Coal_Lignite":               0.30,
    "P_Coal_Lignite_CCS":           0.30,
    "CHP_Coal_Hardcoal":            0.45,
    "CHP_Coal_Hardcoal_CCS":        0.45,
    "CHP_Coal_Lignite":             0.30,
    "CHP_Coal_Lignite_CCS":         0.30,
    # CCGT (gas)
    "P_Gas_CCGT":                   0.60,
    "P_Gas_CCS":                    0.60,
    "CHP_Gas_CCGT_Natural":         0.60,
    "CHP_Gas_CCGT_Natural_CCS":     0.60,
    "CHP_Gas_CCGT_Biogas":          0.60,
    "CHP_Gas_CCGT_Biogas_CCS":      0.60,
    "CHP_Gas_CCGT_SynGas":          0.60,
    # OCGT / engines / H2-OCGT
    "P_Gas_OCGT":                   1.00,
    "P_Gas_Engines":                1.00,
    "P_H2_OCGT":                    1.00,
    # Gas steam turbine (legacy fleet) — gas-fired boiler ramps a bit faster
    # than coal ST (no mills/fuel handling), slower than CCGT
    "P_Gas_Steam":                  0.50,
    # Nuclear
    "P_Nuclear":                    0.15,
    # Hydro (reservoir is the dispatchable hydro tech)
    "P_Hydro_Reservoir":            1.00,
    # Biomass / Bio-CCS
    "P_Biomass":                    0.90,
    "P_Biomass_CCS":                0.90,
    "CHP_Biomass_Solid":            0.90,
    "CHP_Biomass_Solid_CCS":        0.90,
    # Oil ST
    "P_Oil":                        1.00,
    "CHP_Oil":                      1.00,
    # Fuel cell CHP — very fast like OCGT
    "CHP_Hydrogen_FuelCell":        1.00,
    # Waste-to-energy CHP — solid-fuel boiler, slower like coal
    "CHP_WasteToEnergy":            0.45,
}


def rewrite(csv_path):
    with open(csv_path, "r", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    header = rows[0]
    kept = [header]
    techs_touched = set()
    for row in rows[1:]:
        if not row or not row[0]:
            kept.append(row); continue
        tech = row[0]
        if tech in FACTORS:
            techs_touched.add(tech)
            # Drop existing rows for this tech; we'll re-add a single "All" row
            continue
        kept.append(row)
    for tech, val in FACTORS.items():
        kept.append([tech, "All", str(val), "", "Factor", SOURCE, STAMP, AUTHOR])
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        csv.writer(f).writerows(kept)
    print(f"  {os.path.basename(csv_path)}: rewrote {len(techs_touched)} techs, "
          f"wrote {len(FACTORS)} entries")


def main():
    print("Updating ramping factors...")
    rewrite(RU)
    rewrite(RD)


if __name__ == "__main__":
    main()
    print("Done.")
