"""Clone P_Gas_CCGT -> P_Gas_CCGT_Residual (the existing, permit-limited CCGT
fleet) across the tech-DEFINING parameter CSVs, with AvailabilityFactor overridden
to 0.5 (existing CCGTs have permitted-runtime limits).

NOT cloned here (handled elsewhere):
  - capacity params (ResidualCapacity, TotalAnnualMax/MinCapacity): the existing
    fleet is MOVED onto P_Gas_CCGT_Residual by add_capacity_bounds.py (NA scope);
    P_Gas_CCGT becomes new-build only.
  - Par_NewCapacityExpansionStop / Par_RegionalBaseYearProduction: Europe-only rows
    (out of the NA scope chosen for this tech).

Also retunes existing-fleet AvailabilityFactors (permit/runtime limits), colleague
feedback 2026-06:  P_Gas_OCGT 0.3, P_Gas_Steam 0.2, P_Gas_Engines 0.4.

Idempotent (existing _Residual rows are dropped before re-clone).
Run:  python NA_inputs/clone_ccgt_residual.py [--apply]
"""
import os, sys
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_REPO = os.path.normpath(os.path.join(HERE, ".."))
P = lambda *a: os.path.join(DATA_REPO, "Data", "Parameters", *a)
apply = "--apply" in sys.argv

SRC_TECH, NEW_TECH = "P_Gas_CCGT", "P_Gas_CCGT_Residual"
RESIDUAL_AV = 0.5
AV_CHANGES = {"P_Gas_OCGT": 0.3, "P_Gas_Steam": 0.2, "P_Gas_Engines": 0.4}

# Tech-defining base CSVs (World-level data; NA inherits World). No capacity, no
# Europe-only sheets.
DEFINING = [
    ("00_Sets&Tags", "Par_CapacityToActivityUnit"),
    ("00_Sets&Tags", "Par_EmissionPenaltyTagTech"),
    ("00_Sets&Tags", "Par_ReserveMarginTagTechnology"),
    ("00_Sets&Tags", "Par_TagTechnologyToSector"),
    ("00_Sets&Tags", "Par_TagTechnologyToSubsets"),
    ("Par_AvailabilityFactor", "Par_AvailabilityFactor"),
    ("Par_CapitalCost", "Par_CapitalCost"),
    ("Par_EmissionActivityRatio", "Par_EmissionActivityRatio"),
    ("Par_FixedCost", "Par_FixedCost"),
    ("Par_InputActivityRatio", "Par_InputActivityRatio"),
    ("Par_OperationalLife", "Par_OperationalLife"),
    ("Par_OutputActivityRatio", "Par_OutputActivityRatio"),
    ("Par_ProductionChangeCost", "Par_ProductionChangeCost"),
    ("Par_RampingDownFactor", "Par_RampingDownFactor"),
    ("Par_RampingUpFactor", "Par_RampingUpFactor"),
    ("Par_VariableCost", "Par_VariableCost"),
]


def _read(path):
    d = pd.read_csv(path)
    d.columns = ["" if str(c).startswith("Unnamed") else c for c in d.columns]
    return d


def clone_csv(path, av_override=None):
    d = _read(path)
    if "Technology" not in d.columns:
        return "no Technology col", 0
    d = d[d["Technology"] != NEW_TECH]              # idempotent
    src = d[d["Technology"] == SRC_TECH].copy()
    if src.empty:
        return "no source rows", 0
    src["Technology"] = NEW_TECH
    if av_override is not None and "Value" in src.columns:
        src["Value"] = av_override
    out = pd.concat([d, src], ignore_index=True)
    if apply:
        out.to_csv(path, index=False)
    return "ok", len(src)


def main():
    # 1) Sets_Technology: add the tech name.
    st = P("00_Sets&Tags", "Sets_Technology.csv")
    s = _read(st)
    col = s.columns[0]
    s = s[s[col] != NEW_TECH]
    added = 0
    if (s[col] == SRC_TECH).any():
        s = pd.concat([s, pd.DataFrame({col: [NEW_TECH]})], ignore_index=True)
        added = 1
    if apply:
        s.to_csv(st, index=False)
    print(f"Sets_Technology: +{added} ({NEW_TECH})")

    # 2) clone the defining params
    for d, n in DEFINING:
        av = RESIDUAL_AV if n == "Par_AvailabilityFactor" else None
        status, k = clone_csv(P(d, n + ".csv"), av)
        note = f" (av={RESIDUAL_AV})" if av is not None else ""
        print(f"  {n:30} -> {k} _Residual rows  [{status}]{note}")

    # 3) AvailabilityFactor retune for the other existing gas fleets
    avp = P("Par_AvailabilityFactor", "Par_AvailabilityFactor.csv")
    a = _read(avp)
    for tech, val in AV_CHANGES.items():
        m = a["Technology"] == tech
        print(f"  AvailabilityFactor {tech}: {a.loc[m,'Value'].tolist()} -> {val}")
        a.loc[m, "Value"] = val
    if apply:
        a.to_csv(avp, index=False)

    print(f"\n{'APPLIED' if apply else 'DRY-RUN'} (use --apply to write)")


if __name__ == "__main__":
    main()
