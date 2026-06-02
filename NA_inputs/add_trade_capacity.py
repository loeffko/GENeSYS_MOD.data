"""Load NA inter-pool power trade capacities from NA_inputs/pool_links.xlsx into
Par_TradeCapacity.csv (existing 2025 capacity) and Par_CommissionedTradeCapacity.csv
(two planned links that come online later).

pool_links Total_Capacity is in MW; the model's TradeCapacity is a power capacity in GW
(constraint TrC1 multiplies it by 31.536 PJ/GW/yr), so MW -> GW = /1000. Fuel = 'Power'.

Existing links  -> Par_TradeCapacity, Year 2025 (the model start year).
Planned links (currently 0 MW in the file):
  MISO -> PJM            -> CommissionedTradeCapacity, Year 2029, 2.1 GW (unidirectional)
  MISO <-> WECC          -> CommissionedTradeCapacity, Year 2032, 3.0 GW (both directions)

Idempotent: existing NA-NA 'Power' rows in both CSVs are removed before appending.
Run:  python NA_inputs/add_trade_capacity.py            # dry-run
      python NA_inputs/add_trade_capacity.py --apply
"""
import os, sys
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_REPO = os.path.normpath(os.path.join(HERE, ".."))
SRC = os.path.join(HERE, "pool_links.xlsx")
TC = os.path.join(DATA_REPO, "Data", "Parameters", "Par_TradeCapacity", "Par_TradeCapacity.csv")
CTC = os.path.join(DATA_REPO, "Data", "Parameters", "Par_CommissionedTradeCapacity", "Par_CommissionedTradeCapacity.csv")
apply = "--apply" in sys.argv

POOL_MAP = {"CALI": "California", "WECC": "WECC", "SPP": "SPP", "MISO": "MISO",
            "ERCOT": "ERCOT", "SERC": "SERC", "PJM": "PJM", "NYISO": "NewYork",
            "ISO-NE": "NewEngland", "CANADA": "Canada"}
NA = set(POOL_MAP.values())

# planned links: (from, to) -> (commission_year, GW). Excluded from the 2025 TradeCapacity.
PLANNED = {
    ("MISO", "PJM"):  (2029, 2.1),
    ("MISO", "WECC"): (2032, 3.0),
    ("WECC", "MISO"): (2032, 3.0),
}
DATE, WHO = "2026-05-28", "Konstantin Loffler <kl@wip.tu-berlin.de>"


def main():
    pl = pd.read_excel(SRC)
    pl["From"] = pl["Pool_From"].map(POOL_MAP)
    pl["To"] = pl["Pool_To"].map(POOL_MAP)

    tc_rows, ctc_rows = [], []
    for _, r in pl.iterrows():
        a, b, mw = r["From"], r["To"], float(r["Total_Capacity"])
        if a is None or b is None:
            continue
        if (a, b) in PLANNED:
            yr, gw = PLANNED[(a, b)]
            ctc_rows.append({"Region": a, "Region2": b, "Fuel": "Power", "Year": yr,
                             "Value": gw, "": "", "Unit": "GW",
                             "Source": "pool_links planned interconnection", "Updated at": DATE, "Updated by": WHO})
        else:
            tc_rows.append({"Region": a, "Region.1": b, "Fuel": "Power", "Year": 2025,
                            "Value": mw / 1000.0, "": "", "Unit": "GW",
                            "Source": "pool_links 2025 (MW/1000)", "Updated at": DATE, "Updated by": WHO})

    def merge(path, key2, new_rows):
        df = pd.read_csv(path)
        df = df.rename(columns={"Unnamed: 5": ""})
        drop = df["Region"].isin(NA) & df[key2].isin(NA) & (df["Fuel"] == "Power")
        nd = int(drop.sum())
        df = df[~drop]
        add = pd.DataFrame(new_rows)
        # align columns
        for c in df.columns:
            if c not in add.columns:
                add[c] = ""
        add = add[df.columns]
        out = pd.concat([df, add], ignore_index=True)
        if apply:
            out.to_csv(path, index=False)
        return nd, len(new_rows)

    d1, a1 = merge(TC, "Region.1", tc_rows)
    d2, a2 = merge(CTC, "Region2", ctc_rows)

    print("TradeCapacity (2025, GW):")
    for r in tc_rows:
        print(f"  {r['Region']:11s} -> {r['Region.1']:11s} {r['Value']:.3f}")
    print("CommissionedTradeCapacity:")
    for r in ctc_rows:
        print(f"  {r['Region']:11s} -> {r['Region2']:11s} {r['Value']:.1f} GW @ {r['Year']}")
    print(f"\n{'APPLIED' if apply else 'DRY-RUN'}: TradeCapacity -{d1} old / +{a1} new ; "
          f"CommissionedTradeCapacity -{d2} old / +{a2} new.")
    if not apply:
        print("(use --apply to write)")


if __name__ == "__main__":
    main()
