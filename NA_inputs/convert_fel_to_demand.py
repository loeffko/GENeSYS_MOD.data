"""Convert the FEL Excel (NA_inputs/base_fel_anonymized.xlsx, TWh) into
Par_SpecifiedAnnualDemand.csv rows (PJ) for the Power_* end-use fuels, for the
North American model regions, years 2025-2040.

Mapping (per project spec):
  data_centers : _Data_Grid busbar_twh                      -> Power_DataCenter
  industry     : _Data_Grid busbar_twh                      -> Power_General
  buildings    : Electric_Boiler+HP_Commercial+HP_Residential -> Power_Buildings_Heat
                 Buildings_Trajectory_Adjustment+Other_Buildings -> Power_General
                 + buildings td_loss_twh distributed by at-meter share across the two
  hydrogen     : 'Green H2'    -> Power_Hydrogen
                 'Grey/Blue H2'-> Power_General         (no grid losses)
  transport    : BEV_2W3W+BEV_Buses+BEV_LCV+BEV_MHDV+'BEV_Passenger Cars' -> Power_BEVs
                 Maritime+Rail+Road_NonBEV              -> Power_General
                 + transport td_loss_twh distributed by at-meter share across the two
  Power_Buildings_Cooling : left empty for now (cooling not separable in this data).

FRCC merged into SERC. US_R_OTHER and all non-NA (EU/aggregate) rows ignored.
'TOTAL' sub_segments dropped (avoid double counting). Values written as-is (the
occasional negative is an anonymization artifact, not real data).

Idempotent: existing NA-region rows for Power and all Power_* fuels are removed
before the new rows are appended, so the model carries no generic 'Power' demand.

Run from anywhere:  python NA_inputs/convert_fel_to_demand.py
"""
import os
import pandas as pd
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_REPO = os.path.normpath(os.path.join(HERE, ".."))
XLSX = os.path.join(HERE, "base_fel_anonymized.xlsx")
CSV = os.path.join(DATA_REPO, "Data", "Parameters",
                   "Par_SpecifiedAnnualDemand", "Par_SpecifiedAnnualDemand.csv")

TWH_TO_PJ = 3.6
MODEL_YEARS = list(range(2025, 2041))          # 2025..2040 ; 2018 dropped from the NA model

# FEL geo_code -> model region.  FRCC folds into SERC.  Everything else ignored.
REGION_MAP = {
    "US_R_CALIFORNIA": "California",
    "US_R_ERCOT":      "ERCOT",
    "US_R_ISONE":      "NewEngland",
    "US_R_MISO":       "MISO",
    "US_R_NYISO":      "NewYork",
    "US_R_PJM":        "PJM",
    "US_R_SERC":       "SERC",
    "US_R_SPP":        "SPP",
    "US_R_WECC":       "WECC",
    "US_R_FRCC":       "SERC",   # merged
    "CA":              "Canada",
}
NA_REGIONS = set(REGION_MAP.values())
POWER_FUELS = {"Power", "Power_General", "Power_Buildings_Heat",
               "Power_Buildings_Cooling", "Power_DataCenter",
               "Power_Hydrogen", "Power_BEVs"}

BUILD_HEAT    = {"Electric_Boiler", "HP_Commercial", "HP_Residential"}
BUILD_GENERAL = {"Buildings_Trajectory_Adjustment", "Other_Buildings"}
TRANS_BEV     = {"BEV_2W3W", "BEV_Buses", "BEV_LCV", "BEV_MHDV", "BEV_Passenger Cars"}
TRANS_GENERAL = {"Maritime", "Rail", "Road_NonBEV"}

SOURCE = "FEL 2026 Base (NA_inputs/base_fel_anonymized.xlsx)"
DATE = "2026-05-28"
WHO = "Konstantin Loffler <kl@wip.tu-berlin.de>"


def main():
    ds = pd.read_excel(XLSX, "_Data_Sectoral")
    dg = pd.read_excel(XLSX, "_Data_Grid")

    ds["region"] = ds["geo_code"].map(REGION_MAP)
    dg["region"] = dg["geo_code"].map(REGION_MAP)
    ds = ds[ds["region"].notna() & ds["year"].isin(MODEL_YEARS) & (ds["sub_segment"] != "TOTAL")]
    dg = dg[dg["region"].notna() & dg["year"].isin(MODEL_YEARS)]

    # accumulator: (region, year, fuel) -> TWh
    acc = defaultdict(float)

    def sectoral(sector, subs):
        """sum demand_twh over given sub_segments, grouped by (region, year)."""
        s = ds[(ds["sector"] == sector) & (ds["sub_segment"].isin(subs))]
        return s.groupby(["region", "year"])["demand_twh"].sum()

    def grid(sector, col):
        s = dg[dg["sector"] == sector]
        return s.groupby(["region", "year"])[col].sum()

    # data_centers + industry: whole-sector busbar (already includes grid losses)
    for (r, y), v in grid("data_centers", "busbar_twh").items():
        acc[(r, y, "Power_DataCenter")] += v
    for (r, y), v in grid("industry", "busbar_twh").items():
        acc[(r, y, "Power_General")] += v

    # hydrogen: no grid losses
    for (r, y), v in sectoral("hydrogen", {"Green H2"}).items():
        acc[(r, y, "Power_Hydrogen")] += v
    for (r, y), v in sectoral("hydrogen", {"Grey/Blue H2"}).items():
        acc[(r, y, "Power_General")] += v

    def split_with_losses(sector, a_subs, b_subs, a_fuel, b_fuel):
        """Sum a_subs / b_subs at meter, then distribute the sector's td_loss_twh
        across them by at-meter share, into a_fuel / b_fuel."""
        a = sectoral(sector, a_subs)
        b = sectoral(sector, b_subs)
        loss = grid(sector, "td_loss_twh")
        keys = set(a.index) | set(b.index) | set(loss.index)
        for k in keys:
            av = float(a.get(k, 0.0)); bv = float(b.get(k, 0.0)); L = float(loss.get(k, 0.0))
            tot = av + bv
            if tot != 0:
                acc[(k[0], k[1], a_fuel)] += av + L * (av / tot)
                acc[(k[0], k[1], b_fuel)] += bv + L * (bv / tot)
            else:
                # no at-meter demand to weight by: drop losses into the general bucket
                acc[(k[0], k[1], a_fuel)] += av
                acc[(k[0], k[1], b_fuel)] += bv + L

    split_with_losses("buildings", BUILD_HEAT, BUILD_GENERAL,
                      "Power_Buildings_Heat", "Power_General")
    split_with_losses("transport", TRANS_BEV, TRANS_GENERAL,
                      "Power_BEVs", "Power_General")

    # ---- build new rows (TWh -> PJ) ----
    new_rows = []
    for (r, y, fuel), twh in sorted(acc.items()):
        # Clamp negatives to 0: the anonymized FEL file produces some negative bucket sums
        # (artifact), and negative SpecifiedAnnualDemand makes the energy balance infeasible.
        # Real data has no negatives, so this is a no-op there.
        new_rows.append({
            "Region": r, "Fuel": fuel, "Year": int(y),
            "Value": max(0.0, twh * TWH_TO_PJ), "": "", "Unit": "PJ",
            "Source": SOURCE, "Updated at": DATE, "Updated by": WHO,
        })
    df_new = pd.DataFrame(new_rows)

    # ---- merge into the CSV: drop existing NA Power/Power_* rows, then append ----
    df = pd.read_csv(CSV)
    df = df.rename(columns={"Unnamed: 4": ""})            # restore the blank column name
    drop = df["Region"].isin(NA_REGIONS) & df["Fuel"].isin(POWER_FUELS)
    print(f"Removing {int(drop.sum())} existing NA Power/Power_* rows")
    df = df[~drop]
    df = pd.concat([df, df_new], ignore_index=True)
    df.to_csv(CSV, index=False)

    # ---- report ----
    print(f"Wrote {len(df_new)} rows -> {os.path.relpath(CSV, DATA_REPO)}")
    piv = df_new.pivot_table(index="Fuel", values="Value", aggfunc=["count", "sum"])
    print("\nPer-fuel row count + total PJ written:")
    print(piv.to_string())
    print("\nNote: Power_Buildings_Cooling intentionally left empty (cooling not "
          "separable in this dataset yet).")


if __name__ == "__main__":
    main()
