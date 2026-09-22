# -*- coding: utf-8 -*-
"""Build the data overlays for the 14 SE North-America scenarios (wave 1: one variant each).

Plan: GENeSYSMOD.jl_SE/docs/proposals/NA_scenario_plan_2026-09-18_v3.xlsx (sheet Assumptions).
Every scenario is a data-scenario subfolder NorthAmerica_sNN_<name> under Par_X/ (row-upsert
overlay on the base CSVs), converted with the base NA filter or a scenario filter file when new
set members are involved. New set members / technology properties are appended to the BASE
files (only selected by the scenario filter files that need them):
  fuel  Power_LargeLoads  (flat profile via Par_TagFuelToTimeseries -> POWER_DATACENTER;
                           served by X_Convert_Power mode 7)            s03, s04, s09, s13
  tech  P_Fusion          (Fusion_Market_Model_v09.xlsx, bull case)     s07
  tech  D_IronAir + storage S_IronAir (100 h iron-air, Form-type)      s07
  tag   Par_EmissionPenaltyTagTech = 1 for the gas plants (a CO2 price otherwise skips them) s14

Usage:  python NA_inputs/build_14_scenarios.py [--apply] [--repo <path>] [--only s01,s07]
        (dry run prints the row counts; --repo builds against another checkout, e.g. the
         v6-freeze worktree C:/v6wt). Runs are always v6-based (user decision 2026-09-22).
"""
import os, sys, shutil
import numpy as np
import pandas as pd
import openpyxl

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, '..'))
if '--repo' in sys.argv:
    REPO = os.path.normpath(sys.argv[sys.argv.index('--repo') + 1])
PAR = os.path.join(REPO, 'Data', 'Parameters')
HEAD_PAR = os.path.normpath(os.path.join(HERE, '..', 'Data', 'Parameters'))   # fallback for sensitivity subfolders created after the v6 freeze
TAGS = os.path.join(PAR, '00_Sets&Tags')
CONV = os.path.join(REPO, 'Conversion Script')
APPLY = '--apply' in sys.argv
ONLY = sys.argv[sys.argv.index('--only') + 1].split(',') if '--only' in sys.argv else None

US = ['California', 'WECC', 'ERCOT', 'SPP', 'MISO', 'SERC', 'PJM', 'NewYork', 'NewEngland']
NA = US + ['Canada']
YEARS = list(range(2025, 2041))
TWH = 3.6                      # PJ per TWh
WHO = 'Konstantin Loffler <kl@wip.tu-berlin.de>'
TODAY = '2026-09-22'
PLAN = 'NA_scenario_plan_2026-09-18_v3.xlsx (Assumptions sheet)'
USD = 0.925                    # EUR per USD (EUR2023)
GAS_TECHS = ['P_Gas_CCGT', 'P_Gas_CCGT_Residual', 'P_Gas_OCGT', 'P_Gas_Steam', 'P_Gas_Engines']

written = {}


# ---------------------------------------------------------------- helpers
def read_base(par):
    p = os.path.join(PAR, par, par + '.csv')
    df = pd.read_csv(p, dtype=str, keep_default_na=False, encoding='utf-8-sig')
    df.columns = [c.strip() for c in df.columns]
    return df


def base_header(par):
    p = os.path.join(PAR, par, par + '.csv')
    return read_base(par).columns.tolist() if os.path.exists(p) else None


def ov(scen, par, rows, source):
    """Write scenario overlay rows for `par` into Par_X/<scen>/ (row-upsert on the key columns)."""
    if not rows:
        return
    hdr = base_header(par)
    assert hdr is not None, f'unknown parameter {par}'
    df = pd.DataFrame(rows)
    for c in hdr:
        if c not in df.columns:
            df[c] = ''
    df = df[hdr]
    df['Source'] = source + '; ' + PLAN
    df['Updated at'] = TODAY
    df['Updated by'] = WHO
    written.setdefault(scen, {})[par] = written.get(scen, {}).get(par, 0) + len(df)
    if APPLY:
        d = os.path.join(PAR, par, scen)
        os.makedirs(d, exist_ok=True)
        out = os.path.join(d, par + '.csv')
        if os.path.exists(out):     # several blocks may add rows to the same overlay file
            old = pd.read_csv(out, dtype=str, keep_default_na=False, encoding='utf-8-sig')
            old.columns = [c.strip() for c in old.columns]
            key = [c for c in hdr if c not in ('Value', '', 'Unit', 'Source', 'Updated at', 'Updated by') and not c.startswith('Unnamed')]
            old = old[~old[key].apply(tuple, axis=1).isin(set(df[key].apply(tuple, axis=1)))]
            df = pd.concat([old[hdr], df], ignore_index=True)
        df.to_csv(out, index=False, header=[('' if h.startswith('Unnamed') else h) for h in hdr], lineterminator='\n')


def add_base_rows(fname, rows, keycols, sub='00_Sets&Tags'):
    """Append rows to a base file (tags or parameter) if the key is absent."""
    p = os.path.join(PAR, sub, fname) if sub else os.path.join(PAR, fname)
    df = pd.read_csv(p, dtype=str, keep_default_na=False, encoding='utf-8-sig')
    df.columns = [c.strip() for c in df.columns]
    headerless = not all(k in df.columns for k in keycols)
    if headerless:
        df = pd.read_csv(p, dtype=str, keep_default_na=False, encoding='utf-8-sig', header=None, names=keycols)
    have = set(map(tuple, df[keycols].values.tolist()))
    new = [r for r in rows if tuple(str(r[k]) for k in keycols) not in have]
    if not new:
        return 0
    add = pd.DataFrame(new)
    for c in df.columns:
        if c not in add.columns:
            add[c] = ''
    if 'Updated at' in df.columns:
        add['Updated at'] = TODAY; add['Updated by'] = WHO
    out = pd.concat([df, add[df.columns]], ignore_index=True)
    if APPLY:
        out.to_csv(p, index=False, header=(False if headerless else [('' if h.startswith('Unnamed') else h) for h in df.columns]), lineterminator='\n')
    return len(new)


def interp(points, y):
    """Linear interpolation of a {year: value} dict; flat outside the range."""
    ks = sorted(points)
    if y <= ks[0]:
        return points[ks[0]]
    if y >= ks[-1]:
        return points[ks[-1]]
    for a, b in zip(ks, ks[1:]):
        if a <= y <= b:
            return points[a] + (points[b] - points[a]) * (y - a) / (b - a)


def fmt(v, nd=4):
    return f'{float(v):.{nd}f}'


def num(v):
    """float or None for blank cells."""
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# base demand (PJ) as nested dict [fuel][region][year]
_dem = None
def base_demand():
    global _dem
    if _dem is None:
        df = read_base('Par_SpecifiedAnnualDemand')
        df = df[df.Region.isin(NA)]
        _dem = {}
        for r in df.itertuples(index=False):
            try:
                y = int(r.Year)
            except ValueError:
                continue
            if num(r.Value) is None:
                continue
            _dem.setdefault(r.Fuel, {}).setdefault(r.Region, {})[y] = num(r.Value)
    return _dem


def dem(fuel, region, y):
    return base_demand().get(fuel, {}).get(region, {}).get(y, 0.0)


def demand_rows(scen, fuel, values, source):
    """values: {region: {year: PJ}} -> overlay rows (full replacement rows for those keys)."""
    rows = [{'Region': r, 'Fuel': fuel, 'Year': str(y), 'Value': fmt(v), 'Unit': 'PJ'}
            for r, yv in values.items() for y, v in sorted(yv.items())]
    ov(scen, 'Par_SpecifiedAnnualDemand', rows, source)


def scale_path(fuel, total_twh_us, canada=None, years_from=2028):
    """Rescale the base regional path of `fuel` so that the US total follows total_twh_us
    ({year: TWh}, interpolated; base kept before years_from-1) - regional shares = base shares."""
    out = {}
    for y in YEARS:
        base_us = sum(dem(fuel, r, y) for r in US)
        if y < years_from or base_us == 0:
            continue
        target = interp(total_twh_us, y) * TWH
        ratio = target / base_us
        for r in US:
            out.setdefault(r, {})[y] = dem(fuel, r, y) * ratio
        if canada == 'ratio':
            out.setdefault('Canada', {})[y] = dem(fuel, 'Canada', y) * ratio
    if isinstance(canada, dict):
        for y in YEARS:
            if y >= years_from:
                out.setdefault('Canada', {})[y] = interp(canada, y) * TWH
    return out


def blend_from_base(fuel, target_path, y0=2027):
    """Anchor: base value at y0, then the target milestones (TWh, US total)."""
    base_us_y0 = sum(dem(fuel, r, y0) for r in US) / TWH
    pts = dict(target_path); pts[y0] = base_us_y0
    return pts


def flat_adder(scen, fuel, adders, source):
    """adders: {region: {year: TWh}} interpolated over YEARS; written as fuel rows (base + adder)."""
    vals = {}
    for r, pts in adders.items():
        for y in YEARS:
            v = interp(pts, y)
            if v > 0:
                vals.setdefault(r, {})[y] = dem(fuel, r, y) + v * TWH
    demand_rows(scen, fuel, vals, source)


def by_share(total_pts, shares):
    return {r: {y: v * s for y, v in total_pts.items()} for r, s in shares.items()}


def general_share(regions, y=2040):
    tot = sum(dem('Power_General', r, y) for r in regions)
    return {r: dem('Power_General', r, y) / tot for r in regions}


def cost_multiplier(scen, par, techcol, techs, mult_by_year, source, regions=None, storage=False):
    """Overlay rows = base rows x multiplier(year) for the given technologies (World + NA regions)."""
    df = read_base(par)
    rows = []
    for r in df.itertuples(index=False):
        rr = r._asdict()
        tech = rr[techcol]
        if tech not in techs:
            continue
        if rr['Region'] not in (['World'] + NA if regions is None else regions):
            continue
        try:
            y = int(rr['Year'])
        except ValueError:
            continue
        if y not in mult_by_year or mult_by_year[y] == 1.0 or num(r.Value) is None:
            continue
        rr = {k: v for k, v in rr.items() if k in ('Region', techcol, 'Mode_of_operation', 'Year')}
        rr['Value'] = fmt(num(r.Value) * mult_by_year[y], 4)
        rr['Unit'] = 'MEUR/PJ' if storage else 'MEUR/GW'
        rows.append(rr)
    ov(scen, par, rows, source)


def group_cap_rows(subset, regionsubset, caps, unit='GW'):
    """Full-year rows (missing years would be read as 0)."""
    return [{'TechnologySubset': subset, 'RegionSubset': regionsubset, 'Year': str(y),
             'Value': fmt(caps.get(y, 999999), 3), 'Unit': unit} for y in YEARS]


def sub_path(par, src_scen):
    """Path of an existing sensitivity subfolder file: the --repo checkout first, then HEAD."""
    for base in (PAR, HEAD_PAR):
        p = os.path.join(base, par, src_scen, par + '.csv')
        if os.path.exists(p):
            return p
    return None


def copy_overlay(scen, src_scen, par, source, year_filter=None):
    """Reuse rows of an existing sensitivity subfolder."""
    p = sub_path(par, src_scen)
    if p is None:
        print(f'  WARN missing {src_scen}/{par}')
        return
    df = pd.read_csv(p, dtype=str, keep_default_na=False, encoding='utf-8-sig')
    df.columns = [c.strip() for c in df.columns]
    if year_filter is not None and 'Year' in df.columns:
        df = df[df.Year.apply(lambda s: s.isdigit() and year_filter(int(s)))]
    ov(scen, par, df.to_dict('records'), source + f' (rows reused from {src_scen})')


def filter_file(name, fuels=(), techs=(), storages=(), modes=()):
    if not APPLY:
        return
    src = os.path.join(CONV, 'Set_filter_file_NorthAmerica.xlsx')
    dst = os.path.join(CONV, f'Set_filter_file_{name}.xlsx')
    shutil.copy(src, dst)
    wb = openpyxl.load_workbook(dst)
    def flip(sheet, names):
        ws = wb[sheet]; seen = set()
        for row in ws.iter_rows(min_row=2):
            if row[0].value in names or str(row[0].value) in [str(n) for n in names]:
                row[1].value = 1; seen.add(str(row[0].value))
        for n in names:
            if str(n) not in seen:
                ws.append([n, 1])
    if fuels: flip('Fuel_selection', list(fuels))
    if techs: flip('Technology_selection', list(techs))
    if storages: flip('Storage_selection', list(storages))
    if modes: flip('Mode_of_operation_selection', list(modes))
    wb.save(dst)


# ---------------------------------------------------------------- 0. base additions (new set members)
def base_additions():
    n = 0
    # new demand fuel served by X_Convert_Power mode 7 (flat profile)
    n += add_base_rows('Sets_Fuel.csv', [{'Fuel': 'Power_LargeLoads'}], ['Fuel'])
    n += add_base_rows('Sets_Mode_of_operation.csv', [{'Mode_of_operation': '7'}], ['Mode_of_operation'])
    n += add_base_rows('Par_TagDemandFuelToSector.csv', [{'Fuel': 'Power_LargeLoads', 'Sector': 'Power', 'Value': '1'}], ['Fuel', 'Sector'])
    n += add_base_rows('Par_InputActivityRatio/Par_InputActivityRatio.csv',
                       [{'Region': 'World', 'Technology': 'X_Convert_Power', 'Fuel': 'Power', 'Mode_of_operation': '7', 'Year': 'All', 'Value': '1.0', 'Unit': 'PJ', 'Source': 'power demand splitter (eff=1), flat large-load fuel'}],
                       ['Region', 'Technology', 'Fuel', 'Mode_of_operation', 'Year'], sub='')
    n += add_base_rows('Par_OutputActivityRatio/Par_OutputActivityRatio.csv',
                       [{'Region': 'World', 'Technology': 'X_Convert_Power', 'Fuel': 'Power_LargeLoads', 'Mode_of_operation': '7', 'Year': 'All', 'Value': '1.0', 'Unit': 'PJ', 'Source': 'power demand splitter (eff=1), flat large-load fuel'}],
                       ['Region', 'Technology', 'Fuel', 'Mode_of_operation', 'Year'], sub='')
    # emissions-penalty tag for the gas plants (a CO2 price otherwise applies to coal/oil/CCS only)
    n += add_base_rows('Par_EmissionPenaltyTagTech.csv',
                       [{'Region': 'World', 'Technology': t, 'Emission': 'CO2', 'Year': 'All', 'Value': '1'}
                        for t in GAS_TECHS + ['CHP_Gas_CCGT_Natural', 'P_Biomass', 'CHP_Biomass_Solid']],
                       ['Region', 'Technology', 'Emission', 'Year'])
    # ---- P_Fusion (Fusion_Market_Model_v09.xlsx, bull: FOAK 2034, Class IV x0.7, FOM 2 %, VOM 10 EUR/MWh, CF 0.88, life 60)
    n += add_base_rows('Sets_Technology.csv', [{'Technology': 'P_Fusion'}], ['Technology'])
    n += add_base_rows('Par_TagTechnologyToSector.csv', [{'Technology': 'P_Fusion', 'Sector': 'Power', 'Value': '1'}], ['Technology', 'Sector'])
    n += add_base_rows('Par_TagTechnologyToSubsets.csv', [{'Technology': 'P_Fusion', 'Subset': s, 'Value': '1', 'Unit': 'Binary', 'Source': 'scenario s07'} for s in ('PowerSupply', 'EmergingTechnologies')], ['Technology', 'Subset'])
    n += add_base_rows('Par_CapacityToActivityUnit.csv', [{'Technology': 'P_Fusion', 'Value': '31.536'}], ['Technology'])
    n += add_base_rows('Par_ReserveMarginTagTechnology.csv', [{'Region': 'World', 'Technology': 'P_Fusion', 'Year': 'All', 'Value': '1'}], ['Region', 'Technology', 'Year'])
    n += add_base_rows('Par_OperationalLife/Par_OperationalLife.csv', [{'Technology': 'P_Fusion', 'Value': '60', 'Unit': 'Years', 'Source': 'Fusion_Market_Model_v09.xlsx plant_life_years'}], ['Technology'], sub='')
    n += add_base_rows('Par_OutputActivityRatio/Par_OutputActivityRatio.csv',
                       [{'Region': 'World', 'Technology': 'P_Fusion', 'Fuel': 'Power', 'Mode_of_operation': '1', 'Year': 'All', 'Value': '1.0', 'Unit': 'PJ', 'Source': 'fusion plant, no fuel input modelled'}],
                       ['Region', 'Technology', 'Fuel', 'Mode_of_operation', 'Year'], sub='')
    n += add_base_rows('Par_AvailabilityFactor/Par_AvailabilityFactor.csv',
                       [{'Region': 'World', 'Technology': 'P_Fusion', 'Year': 'All', 'Value': '0.88', 'Unit': 'Fraction', 'Source': 'Fusion_Market_Model_v09.xlsx capacity_factor bull'}],
                       ['Region', 'Technology', 'Year'], sub='')
    n += add_base_rows('Par_ProductionChangeCost/Par_ProductionChangeCost.csv', [{'Technology': 'P_Fusion', 'Year': 'All', 'Value': '5.55556', 'Unit': 'M€/PJ', 'Source': 'as P_Nuclear_SMR'}], ['Technology', 'Year'], sub='')
    for f in ('Par_RampingUpFactor', 'Par_RampingDownFactor'):
        n += add_base_rows(f'{f}/{f}.csv', [{'Technology': 'P_Fusion', 'Year': 'All', 'Value': '0.15', 'Unit': 'Factor', 'Source': 'as P_Nuclear_SMR'}], ['Technology', 'Year'], sub='')
    # capex ramp (EUR/kW = MEUR/GW): reactor N1..N4 at 2034/36/38/40 x 0.7 (bull), flat before, interpolated between
    capex = {2034: 31000 * 0.7, 2036: 23741.67 * 0.7, 2038: 17935 * 0.7, 2040: 13184.09 * 0.7}
    n += add_base_rows('Par_CapitalCost/Par_CapitalCost.csv',
                       [{'Region': 'World', 'Technology': 'P_Fusion', 'Year': str(y), 'Value': fmt(interp(capex, y), 1), 'Unit': 'MEUR/GW', 'Source': 'Fusion_Market_Model_v09.xlsx capex sheet, bull (Class IV x0.7), reactor N1-N4 at 2034-2040'} for y in YEARS],
                       ['Region', 'Technology', 'Year'], sub='')
    n += add_base_rows('Par_FixedCost/Par_FixedCost.csv',
                       [{'Region': 'World', 'Technology': 'P_Fusion', 'Year': str(y), 'Value': fmt(0.02 * interp(capex, y), 2), 'Unit': 'MEUR/GW', 'Source': 'Fusion_Market_Model_v09.xlsx fixed_om_pct_of_capex bull 2 %/yr'} for y in YEARS],
                       ['Region', 'Technology', 'Year'], sub='')
    n += add_base_rows('Par_VariableCost/Par_VariableCost.csv',
                       [{'Region': 'World', 'Technology': 'P_Fusion', 'Mode_of_operation': '1', 'Year': 'All', 'Value': fmt(10 / 3.6, 4), 'Unit': 'MEUR/PJ', 'Source': 'Fusion_Market_Model_v09.xlsx variable_om bull 10 EUR/MWh'}],
                       ['Region', 'Technology', 'Mode_of_operation', 'Year'], sub='')
    n += add_base_rows('Par_TechnologyDiscountRate/Par_TechnologyDiscountRate.csv',
                       [{'Region': 'World', 'Technology': 'P_Fusion', 'Value': '0.07', 'Unit': 'Fraction', 'Source': 'Fusion_Market_Model_v09.xlsx wacc base 7 %'}],
                       ['Region', 'Technology'], sub='')
    # ---- iron-air LDES (D_IronAir / S_IronAir): 100 h, RTE 45 %, 20 yr
    n += add_base_rows('Sets_Technology.csv', [{'Technology': 'D_IronAir'}], ['Technology'])
    n += add_base_rows('Sets_Storage.csv', [{'Storage': 'S_IronAir'}], ['Storage'])
    n += add_base_rows('Par_TagTechnologyToSector.csv', [{'Technology': 'D_IronAir', 'Sector': 'Storages', 'Value': '1'}], ['Technology', 'Sector'])
    n += add_base_rows('Par_TagTechnologyToSubsets.csv', [{'Technology': 'D_IronAir', 'Subset': s, 'Value': '1', 'Unit': 'Binary', 'Source': 'scenario s07'} for s in ('PhaseInSet', 'StorageDummies', 'Transformation', 'IronAir')], ['Technology', 'Subset'])
    n += add_base_rows('Par_TagTechnologyToSubsets.csv', [{'Technology': 'D_Battery_Li-Ion', 'Subset': 'LiIon', 'Value': '1', 'Unit': 'Binary', 'Source': 'scenario s11 group cap'}], ['Technology', 'Subset'])
    n += add_base_rows('Par_CapacityToActivityUnit.csv', [{'Technology': 'D_IronAir', 'Value': '31.536'}], ['Technology'])
    n += add_base_rows('Par_OperationalLife/Par_OperationalLife.csv', [{'Technology': 'D_IronAir', 'Value': '20', 'Unit': 'Years', 'Source': 'Form Energy iron-air, assumed 20 yr'}], ['Technology'], sub='')
    n += add_base_rows('Par_OperationalLifeStorage/Par_OperationalLifeStorage.csv', [{'Storage': 'S_IronAir', 'Value': '20', 'Unit': 'Years', 'Source': 'assumed as D_IronAir'}], ['Storage'], sub='')
    n += add_base_rows('Par_InputActivityRatio/Par_InputActivityRatio.csv',
                       [{'Region': 'World', 'Technology': 'D_IronAir', 'Fuel': 'Power', 'Mode_of_operation': '1', 'Year': 'All', 'Value': '1.0', 'Unit': 'PJ', 'Source': 'efficiency in TechnologyToStorage'}],
                       ['Region', 'Technology', 'Fuel', 'Mode_of_operation', 'Year'], sub='')
    n += add_base_rows('Par_OutputActivityRatio/Par_OutputActivityRatio.csv',
                       [{'Region': 'World', 'Technology': 'D_IronAir', 'Fuel': 'Power', 'Mode_of_operation': '2', 'Year': 'All', 'Value': '1.0', 'Unit': 'PJ', 'Source': 'efficiency in TechnologyFromStorage'}],
                       ['Region', 'Technology', 'Fuel', 'Mode_of_operation', 'Year'], sub='')
    n += add_base_rows('Par_TechnologyToStorage/Par_TechnologyToStorage.csv', [{'Technology': 'D_IronAir', 'Storage': 'S_IronAir', 'Mode_of_operation': '1', 'Year': 'All', 'Value': '0.67', 'Unit': 'Fraction', 'Source': 'iron-air RTE ~45 % (Form Energy, secondary) = 0.67 x 0.67'}], ['Technology', 'Storage', 'Mode_of_operation', 'Year'], sub='')
    n += add_base_rows('Par_TechnologyFromStorage/Par_TechnologyFromStorage.csv', [{'Technology': 'D_IronAir', 'Storage': 'S_IronAir', 'Mode_of_operation': '2', 'Year': 'All', 'Value': '0.67', 'Unit': 'Fraction', 'Source': 'iron-air RTE ~45 % = 0.67 x 0.67'}], ['Technology', 'Storage', 'Mode_of_operation', 'Year'], sub='')
    n += add_base_rows('Par_StorageE2PRatio/Par_StorageE2PRatio.csv', [{'Storage': 'S_IronAir', 'Year': 'All', 'Value': '100', 'Unit': 'GWh/GW', 'Source': 'Form Energy 100-hour iron-air'}], ['Storage', 'Year'], sub='')
    n += add_base_rows('Par_AvailabilityFactor/Par_AvailabilityFactor.csv', [{'Region': 'World', 'Technology': 'D_IronAir', 'Year': 'All', 'Value': '1.0', 'Unit': 'Fraction', 'Source': 'as other storage dummies'}], ['Region', 'Technology', 'Year'], sub='')
    n += add_base_rows('Par_CapitalCost/Par_CapitalCost.csv', [{'Region': 'World', 'Technology': 'D_IronAir', 'Year': str(y), 'Value': fmt(300 * USD, 1), 'Unit': 'MEUR/GW', 'Source': 'iron-air power component ~300 USD/kW backed out of the DOE LDES Liftoff multi-day 2030 target (1,100 USD/kW system)'} for y in YEARS], ['Region', 'Technology', 'Year'], sub='')
    n += add_base_rows('Par_FixedCost/Par_FixedCost.csv', [{'Region': 'World', 'Technology': 'D_IronAir', 'Year': str(y), 'Value': '6.0', 'Unit': 'MEUR/GW', 'Source': 'assumed ~2 %/yr of the power component'} for y in YEARS], ['Region', 'Technology', 'Year'], sub='')
    n += add_base_rows('Par_VariableCost/Par_VariableCost.csv', [{'Region': 'World', 'Technology': 'D_IronAir', 'Mode_of_operation': m, 'Year': 'All', 'Value': '0.5', 'Unit': 'MEUR/PJ', 'Source': 'as D_Battery_Redox'} for m in ('1', '2')], ['Region', 'Technology', 'Mode_of_operation', 'Year'], sub='')
    e_capex = {2028: 60, 2035: 30, 2040: 20}   # USD/kWh -> MEUR/PJ: x 277.778 x EUR/USD
    n += add_base_rows('Par_CapitalCostStorage/Par_CapitalCostStorage.csv', [{'Region': 'World', 'Storage': 'S_IronAir', 'Year': str(y), 'Value': fmt(interp(e_capex, y) * 277.778 * USD, 1), 'Unit': 'MEUR/PJ', 'Source': 'iron-air energy component 60 -> 30 -> 20 USD/kWh (Form Energy target 20 USD/kWh; implied ~77 today)'} for y in YEARS], ['Region', 'Storage', 'Year'], sub='')
    return n


# ---------------------------------------------------------------- scenario blocks
def s01_ev():
    S = 'NorthAmerica_s01_ev'
    src = 'S1 EV comeback: EIA AEO2026 reference transport electricity 146/408/624 TWh (2030/35/40), base to 2027; Canada CER EF2026 net-zero 29/72/125 TWh'
    us = blend_from_base('Power_BEVs', {2030: 146, 2035: 408, 2040: 624})
    ca = {2027: dem('Power_BEVs', 'Canada', 2027) / TWH, 2030: 29, 2035: 72, 2040: 125}
    demand_rows(S, 'Power_BEVs', scale_path('Power_BEVs', us, canada=ca), src)


def s02_h2():
    S = 'NorthAmerica_s02_h2'
    src = 'S2 H2 comeback: DOE 3.8 GW firm electrolysers by 2030, 3 Mt (2035) / 6 Mt (2040) electrolytic = 30 % of the DOE 20 Mt target x 55.5 kWh/kg; hub-based regional shares; Canada CER EF2026 Current Measures electrolysis'
    us = {2027: sum(dem('Power_Hydrogen', r, 2027) for r in US) / TWH, 2028: 10, 2030: 27, 2035: 165, 2040: 333}
    shares = {'ERCOT': .35, 'PJM': .25, 'MISO': .20, 'California': .10, 'SPP': .05, 'WECC': .05}
    vals = {}
    for y in YEARS:
        if y < 2028:
            continue
        tot = interp(us, y) * TWH
        for r in US:
            vals.setdefault(r, {})[y] = tot * shares.get(r, 0.0)
        vals.setdefault('Canada', {})[y] = interp({2027: dem('Power_Hydrogen', 'Canada', 2027) / TWH, 2030: 25, 2035: 52, 2040: 80}, y) * TWH
    demand_rows(S, 'Power_Hydrogen', vals, src)


def s03_compute():
    S = 'NorthAmerica_s03_compute'
    src = 'S3 age of compute: DC base to 2030, BNEF 194 GW (2035) x 0.85 LF, +9 %/yr to 2040; Canada scaled with the US ratio'
    demand_rows(S, 'Power_DataCenter', scale_path('Power_DataCenter', {2030: sum(dem('Power_DataCenter', r, 2030) for r in US) / TWH, 2035: 1450, 2040: 2230}, canada='ratio', years_from=2031), src)
    crypto = by_share({2026: 60, 2035: 80, 2040: 80}, {'ERCOT': .40, 'SPP': .15, 'MISO': .15, 'SERC': .10, 'PJM': .10, 'WECC': .10})
    ind = general_share(US)
    robo = by_share({2027: 0, 2028: 5, 2035: 90, 2040: 150}, ind)
    tele = by_share({2029: 0, 2030: 10, 2040: 50}, ind)
    adders = {}
    for d in (crypto, robo, tele):
        for r, pts in d.items():
            adders.setdefault(r, [])
            adders[r].append(pts)
    merged = {r: {y: sum(interp(p, y) for p in lst) for y in YEARS} for r, lst in adders.items()}
    flat_adder(S, 'Power_LargeLoads', merged, 'S3 second-wave flat loads: crypto (CCAF 138 TWh global x 40 % US), robotics/dark factories (Wood Mackenzie 363 TWh global 2035 x 25 % US), telecom/edge/defense (stated dial)')
    ov(S, 'Par_TagFuelToTimeseries', [{'Fuel': 'Power_LargeLoads', 'Profile': 'POWER_DATACENTER', 'Value': '1', 'Unit': 'Binary'}], 'flat profile for large loads')


def s04_space():
    S = 'NorthAmerica_s04_space'
    shares = {'ERCOT': .5, 'California': .2, 'SERC': .2, 'WECC': .1}
    tot = {2028: 0, 2030: 5, 2035: 35, 2040: 155}   # e-propellant 2/20/100 + manufacturing/ground 3/15/55
    flat_adder(S, 'Power_LargeLoads', by_share(tot, shares), 'S4 space race (terrestrial industry): e-propellant for 100/1,000/5,000 Starship launches per year (~21 GWh each: electrolytic H2 + DAC CO2 + liquefaction) + satellite/launcher manufacturing and ground segment; orbital-compute displacement NOT applied (separate space_dc trio)')
    ov(S, 'Par_TagFuelToTimeseries', [{'Fuel': 'Power_LargeLoads', 'Profile': 'POWER_DATACENTER', 'Value': '1', 'Unit': 'Binary'}], 'flat profile for large loads')


def s05_brakes():
    S = 'NorthAmerica_s05_brakes'
    mult = {'ERCOT': lambda y: 0.3 if y <= 2030 else 0.6, 'California': lambda y: .5, 'NewYork': lambda y: .5, 'NewEngland': lambda y: .5,
            'PJM': lambda y: .7, 'MISO': lambda y: .7, 'SERC': lambda y: .7, 'WECC': lambda y: .8, 'SPP': lambda y: .9, 'Canada': lambda y: 1.0}
    vals = {}
    for r in NA:
        d26 = dem('Power_DataCenter', r, 2026)
        for y in YEARS:
            if y >= 2027:
                vals.setdefault(r, {})[y] = d26 + mult[r](y) * (dem('Power_DataCenter', r, y) - d26)
    demand_rows(S, 'Power_DataCenter', vals, 'S5 political brakes: regional multipliers on the base DC increment after 2026 (ERCOT anchored on BNEF ~8 GW adds through 2030 after the Aug-2026 interconnection pause; NY EO 62; moratoria leaders CA/GA/FL/NJ/NC)')
    ov(S, 'Par_GroupTotalAnnualMaxNewCap', group_cap_rows('GasPlants', 'USA', {y: 10.0 for y in range(2027, 2032)}), 'S5: US gas new-build cap 10 GW/yr 2027-31 = 50 % of the IIR schedule (~107 GW starts 2026-30); turbine slots into 2031')
    # gas guardrail minimum removed: min = residual capacity
    res = read_base('Par_ResidualCapacity'); res = res[res.Region.isin(US) & res.Technology.isin(GAS_TECHS)]
    rows = [{'Region': r.Region, 'Technology': r.Technology, 'Year': r.Year, 'Value': r.Value, 'Unit': 'GW'} for r in res.itertuples(index=False) if r.Year.isdigit() and int(r.Year) >= 2027 and num(r.Value) is not None]
    ov(S, 'Par_TotalAnnualMinCapacity', rows, 'S5: no forced gas builds (guardrail minimum = residual capacity)')
    # RES funnel max = announced pipeline (base funnel widens to x1.30 at 2035)
    mx = read_base('Par_TotalAnnualMaxCapacity')
    reps = ['P_PV_Utility_Opt', 'P_Wind_Onshore_Opt', 'P_Wind_Offshore_Shallow', 'P_Wind_Offshore_Deep', 'P_Wind_Offshore_Transitional']
    mx = mx[mx.Region.isin(US) & mx.Technology.isin(reps)]
    mn = read_base('Par_TotalAnnualMinCapacity'); mn = mn[mn.Region.isin(US) & mn.Technology.isin(reps)]
    minv = {(r.Region, r.Technology, r.Year): num(r.Value) or 0.0 for r in mn.itertuples(index=False)}
    rows = []
    for r in mx.itertuples(index=False):
        if not r.Year.isdigit() or num(r.Value) is None:
            continue
        y = int(r.Year); v = num(r.Value)
        if v >= 99999 or y < 2029:
            continue
        f = 1 + 0.30 * min(y - 2028, 7) / 7
        # never below the running maximum of the base minima up to this year (capacity built to meet an
        # earlier minimum persists; offshore minima are contracted pipelines, not funnel floors)
        floor = max([minv.get((r.Region, r.Technology, str(yy)), 0.0) for yy in range(2025, y + 1)] + [0.0])
        rows.append({'Region': r.Region, 'Technology': r.Technology, 'Year': r.Year, 'Value': fmt(max(v / f, floor * 1.001), 6), 'Unit': 'GW'})
    ov(S, 'Par_TotalAnnualMaxCapacity', rows, 'S5: RES funnel max = announced pipeline (base x1.30 widening removed)')


def s06_hormuz():
    S = 'NorthAmerica_s06_hormuz'
    # macro leg: capex x1.35 (2026-28: +15 % equipment, +18 % = WACC +150 bp via CRF), x1.18 (2029-30), x1.09 (2031), 1.0 from 2032
    m = {2026: 1.35, 2027: 1.35, 2028: 1.35, 2029: 1.18, 2030: 1.18, 2031: 1.09}
    cc = read_base('Par_CapitalCost')
    techs = sorted({t for t in cc.Technology.unique() if t.startswith(('P_', 'D_', 'CHP_'))})
    cost_multiplier(S, 'Par_CapitalCost', 'Technology', techs, m, 'S6 Hormuz macro leg: equipment inflation +15 % 2026-28 (turbines +195 % vs 2019, CT in-service 562 -> 728-1,544 USD/kW) and WACC +150 bp 2026-30 folded into capex via CRF(6.5 %)/CRF(5 %) = 1.18, decaying to 1.0 by 2032')
    cs = read_base('Par_CapitalCostStorage')
    cost_multiplier(S, 'Par_CapitalCostStorage', 'Storage', sorted(cs.Storage.unique()), m, 'S6 Hormuz macro leg (storage energy component), same multiplier', storage=True)
    copy_overlay(S, 'NorthAmerica_grid_low', 'Par_AnnualMaxTradeCapacity', 'S6: IC growth capped at 0.75 %/yr 2026-30 (utility capex freeze proxy; ~60 % of solar / 50 % of battery projects delayed early 2026)', year_filter=lambda y: 2026 <= y <= 2030)
    # demand: recession FEL 2026-2030, blend back to base by 2033
    rec = pd.read_csv(sub_path('Par_SpecifiedAnnualDemand', 'NorthAmerica_recession'), dtype=str, keep_default_na=False, encoding='utf-8-sig')
    rec.columns = [c.strip() for c in rec.columns]
    vals = {}
    for r in rec.itertuples(index=False):
        if not r.Year.isdigit() or r.Region not in NA:
            continue
        y = int(r.Year); v = num(r.Value); b = dem(r.Fuel, r.Region, y)
        if v is None:
            continue
        if 2026 <= y <= 2030:
            vals.setdefault(r.Fuel, {}).setdefault(r.Region, {})[y] = v
        elif 2031 <= y <= 2032:
            w = (y - 2030) / 3
            vals.setdefault(r.Fuel, {}).setdefault(r.Region, {})[y] = v + (b - v) * w
    for f, d in vals.items():
        demand_rows(S, f, d, 'S6: recession-FEL demand 2026-30 (Dallas Fed: 3-quarter closure +1.1 pp PCE, oil-shock analogues 1974/1982/2009), blended back to base by 2033')
    # LNG / fuel leg -> separate allFuels workbook (Henry Hub +10 % 2026, +2 USD/MMBtu 2027-29, +1 in 2030), written by build_s06_allfuels()


def build_s06_allfuels(src_xlsx, dst_xlsx):
    """Copy the v6 allFuels workbook and uplift the Z_Import_Gas VariableCost (folded fuel price)."""
    wb = openpyxl.load_workbook(src_xlsx)
    ws = wb['Par_VariableCost']
    hdr = [c.value for c in ws[1]]
    it, iy, iv = hdr.index('Technology'), hdr.index('Year'), hdr.index('Value')
    n = 0
    for row in ws.iter_rows(min_row=2):
        if row[it].value == 'Z_Import_Gas':
            y = int(row[iy].value); v = float(row[iv].value)
            if y == 2026:
                row[iv].value = round(v * 1.10, 4); n += 1
            elif 2027 <= y <= 2029:
                row[iv].value = round(v + 2 * 0.877, 4); n += 1     # +2 USD/MMBtu = +1.754 MEUR/PJ
            elif y == 2030:
                row[iv].value = round(v + 0.877, 4); n += 1
    wb.save(dst_xlsx)
    return n


def s07_tech():
    S = 'NorthAmerica_s07_tech'
    # SMR fast: max 2/5/15/40 GW (2030/32/35/40), base 2040 regional shares; capex INL advanced -> Liftoff NOAK
    mx = read_base('Par_TotalAnnualMaxCapacity')
    smr40 = {r.Region: num(r.Value) or 0.0 for r in mx[(mx.Technology == 'P_Nuclear_SMR') & (mx.Year == '2040') & mx.Region.isin(NA)].itertuples(index=False)}
    tot40 = sum(smr40.values())
    tot = {2029: 0, 2030: 2, 2032: 5, 2035: 15, 2040: 40}
    rows = [{'Region': r, 'Technology': 'P_Nuclear_SMR', 'Year': str(y), 'Value': fmt(interp(tot, y) * smr40.get(r, 0) / tot40, 3), 'Unit': 'GW'} for r in NA for y in YEARS]
    ov(S, 'Par_TotalAnnualMaxCapacity', rows, 'S7 SMR fast: available 2030, 2/5/15/40 GW (2030/32/35/40) split by the base 2040 regional SMR potential (Darlington, Natrium, Clinch River, Hermes 2; TVA/ENTRA1 6 GW, Meta/Google/Amazon deals)')
    capex = {2030: 5500 * USD, 2035: 4300 * USD, 2040: 3600 * USD}
    ov(S, 'Par_CapitalCost', [{'Region': 'World', 'Technology': 'P_Nuclear_SMR', 'Year': str(y), 'Value': fmt(interp(capex, y), 1), 'Unit': 'MEUR/GW'} for y in YEARS], 'S7 SMR capex: INL/NREL ATB 2025 advanced BOAK 5,500 USD/kW (2030) with 9.5 % learning to the DOE Liftoff NOAK ~3,600 USD/kW by 2040 (base 9,091 EUR/kW flat)')
    # iron-air: enable from 2028 with a NA build cap; Li-ion optimistic reused
    ov(S, 'Par_TotalAnnualMaxCapacity', [{'Region': r, 'Technology': 'D_IronAir', 'Year': str(y), 'Value': '0' if y < 2028 else '999999', 'Unit': 'GW'} for r in NA for y in YEARS], 'S7 iron-air available from 2028')
    ov(S, 'Par_GroupTotalAnnualMaxNewCap', group_cap_rows('IronAir', 'NorthAmerica', {2025: 0, 2026: 0, 2027: 0, 2028: 0.5, 2029: 1.0, 2030: 2.0, 2031: 3.0, **{y: 5.0 for y in range(2032, 2041)}}), 'S7 iron-air build cap: Weirton 500 MW/yr by 2028, Google/Xcel 300 MW/30 GWh, pipeline 750 MW / 75 GWh -> 0.5/1/2/3/5 GW/yr')
    for par in ('Par_CapitalCost', 'Par_CapitalCostStorage', 'Par_StorageE2PRatio'):
        copy_overlay(S, 'NorthAmerica_bess_optimistic', par, 'S7: Li-ion optimistic cost + 7 h duration')
    # fusion (bull ramp, 100 % located in NA): min = max = cumulative backed ramp
    shares = {'PJM': .4, 'WECC': .2, 'SERC': .2, 'California': .1, 'ERCOT': .1}
    ramp = {2034: 2.0, 2036: 4.25, 2038: 6.75, 2040: 9.5}
    def cum(y):
        return max([v for k, v in ramp.items() if k <= y], default=0.0)
    rows_max = [{'Region': r, 'Technology': 'P_Fusion', 'Year': str(y), 'Value': fmt(cum(y) * s, 3), 'Unit': 'GW'} for r, s in shares.items() for y in YEARS]
    rows_max += [{'Region': r, 'Technology': 'P_Fusion', 'Year': str(y), 'Value': '0', 'Unit': 'GW'} for r in NA if r not in shares for y in YEARS]
    ov(S, 'Par_TotalAnnualMaxCapacity', rows_max, 'S7 fusion: Fusion_Market_Model_v09 bull backed ramp (5 developers x 400/450/500/550 MW at 2034/36/38/40 = 2.0/4.25/6.75/9.5 GW cumulative), 100 % located in NA at announced sites (CFS VA, Helion WA, Type One TN, Pacific Fusion CA, ERCOT)')
    ov(S, 'Par_TotalAnnualMinCapacity', [x for x in rows_max if float(x['Value']) > 0], 'S7 fusion: the backed ramp is must-build (workbook logic)')


def s08_canada():
    S = 'NorthAmerica_s08_canada'
    ca = {2027: dem('Power_DataCenter', 'Canada', 2027) / TWH, 2030: 41, 2035: 130, 2040: 220}
    demand_rows(S, 'Power_DataCenter', {'Canada': {y: interp(ca, y) * TWH for y in YEARS if y >= 2028}}, 'S8 Canada DC frontier, pipeline-consistent: ISED 5.5 GW by 2030, ~16 GW 2035 (AESO interim 1.2 + viable 4.8 + interruptible 1.6 + Meta 1.8 + ON/QC/BC), ~28 GW 2040 x 8.76 x 0.85. FLAG: below the FEL base (71/178/269 TWh) - scenario numbers used as instructed')
    mn = read_base('Par_TotalAnnualMinCapacity'); mn = mn[(mn.Region == 'Canada') & (mn.Technology == 'P_Gas_CCGT')]
    base = {int(r.Year): num(r.Value) or 0.0 for r in mn.itertuples(index=False) if r.Year.isdigit()}
    def byop(y):
        return (0.25 if y >= 2028 else 0) + (0.93 if y >= 2030 else 0) + (1.4 if y >= 2033 else 0)
    ov(S, 'Par_TotalAnnualMinCapacity', [{'Region': 'Canada', 'Technology': 'P_Gas_CCGT', 'Year': str(y), 'Value': fmt(base.get(y, 0) + byop(y), 3), 'Unit': 'GW'} for y in YEARS if byop(y) > 0], 'S8 bring-your-own-power gas: Capital Power 250 MW bridge (2028), Greenlight 932 MW CCGT (FID Jul 2026, COD 2H 2030), Wonder Valley phase 1 1.4 GW (2033) on top of the base Canada CCGT minimum')


def s09_water():
    S = 'NorthAmerica_s09_water'
    flat_adder(S, 'Power_LargeLoads', by_share({2029: 0, 2030: 4, 2035: 18, 2040: 36}, {'WECC': .4, 'California': .3, 'ERCOT': .2, 'SERC': .1}), 'S9 manufactured-water Southwest: 10 Mm3/d desal + conveyance (6.5 kWh/m3), 2 Mm3/d Florida SWRO, pumped imports replacing 50 % of the Colorado deficit; pipeline anchors Corpus Christi/Harbor Island/Pure Water SoCal+LA/Phoenix/WIFA (Israel ~2, Gulf ~20 Mm3/d today)')
    ov(S, 'Par_TagFuelToTimeseries', [{'Fuel': 'Power_LargeLoads', 'Profile': 'POWER_DATACENTER', 'Value': '1', 'Unit': 'Binary'}], 'flat profile for large loads')


def s10_climate():
    S = 'NorthAmerica_s10_climate'
    donors = ['SERC', 'ERCOT', 'California']; receivers = ['MISO', 'PJM', 'NewEngland', 'NewYork', 'WECC']
    rshare = general_share(receivers)
    s = {2029: 0, 2035: .10, 2040: .20}
    cool = {2029: 0, 2040: .08}
    vals = {'Power_General': {}, 'Power_DataCenter': {}}
    for y in YEARS:
        if y < 2030:
            continue
        sh = interp(s, y); cu = interp(cool, y)
        moved = {'Power_General': 0.0, 'Power_DataCenter': 0.0}
        for r in NA:
            g = dem('Power_General', r, y) * 1.01                        # rebuild load +1 % national
            if r in ('SERC', 'ERCOT', 'SPP', 'California'):
                g *= (1 + cu)                                             # Sunbelt cooling uplift
            d = dem('Power_DataCenter', r, y)
            if r in donors:
                moved['Power_General'] += g * sh; g *= (1 - sh)
                moved['Power_DataCenter'] += d * sh; d *= (1 - sh)
            vals['Power_General'].setdefault(r, {})[y] = g
            vals['Power_DataCenter'].setdefault(r, {})[y] = d
        for r in receivers:
            vals['Power_General'][r][y] += moved['Power_General'] * rshare[r]
            vals['Power_DataCenter'][r][y] += moved['Power_DataCenter'] * rshare[r]
    src = 'S10 Great Reshuffle: 10 % (2035) / 20 % (2040) of SERC+ERCOT+California General and DC load re-allocated to MISO/PJM/NewEngland/NewYork/WECC by load share (First Street: 55 M movers by 2055); Sunbelt cooling +8 % by 2040 (CDD +10-80 %); rebuild load +1 %'
    for f, d in vals.items():
        demand_rows(S, f, d, src)
    # coastal IC cost x1.5 (no year dimension), coastal thermal availability -5 pp from 2030
    tc = read_base('Par_TradeCapacityGrowthCosts'); coastal = {'SERC', 'ERCOT', 'NewYork', 'NewEngland', 'California'}
    rows = [{'Region': r.Region, 'Region2': r.Region2, 'Fuel': r.Fuel, 'Value': fmt(num(r.Value) * 1.5, 6), 'Unit': 'M€/GWkm'} for r in tc.itertuples(index=False) if r.Fuel == 'Power' and (r.Region in coastal or r.Region2 in coastal) and r.Region in NA and r.Region2 in NA and num(r.Value) is not None]
    ov(S, 'Par_TradeCapacityGrowthCosts', rows, 'S10: coastal grid hardening (Duke Florida 16 bn USD 5-yr plan, Entergy 15 bn / 10 yr) as +50 % IC expansion cost on coastal corridors')
    af = read_base('Par_AvailabilityFactor'); af = af[af.Technology.isin(GAS_TECHS + ['P_Nuclear']) & af.Region.isin(['World'] + list(coastal))]
    rows = []
    for t in GAS_TECHS + ['P_Nuclear']:
        for reg in sorted(coastal):
            # regional rows if present, else the World rows (inherited); 'All' -> every year
            src_rows = af[(af.Technology == t) & (af.Region == reg)]
            if src_rows.empty:
                src_rows = af[(af.Technology == t) & (af.Region == 'World')]
            vals = {}
            for r in src_rows.itertuples(index=False):
                if num(r.Value) is None:
                    continue
                if r.Year == 'All':
                    vals = {y: num(r.Value) for y in YEARS}
                elif r.Year.isdigit():
                    vals[int(r.Year)] = num(r.Value)
            if not vals:
                continue
            for y in YEARS:
                if y >= 2030:
                    v = vals.get(y, interp(vals, y))
                    rows.append({'Region': reg, 'Technology': t, 'Year': str(y), 'Value': fmt(max(v - 0.05, 0.05), 4), 'Unit': 'Fraction'})
    ov(S, 'Par_AvailabilityFactor', rows, 'S10: storm outages, coastal gas/nuclear availability -5 pp from 2030')


def s11_feoc():
    S = 'NorthAmerica_s11_feoc'
    m = {2026: 1.44, 2027: 1.37, 2028: 1.30, 2029: 1.22, 2030: 1.15}
    m.update({y: 1.15 + (1.05 - 1.15) * (y - 2030) / 5 for y in range(2031, 2036)}); m.update({y: 1.05 for y in range(2036, 2041)})
    cost_multiplier(S, 'Par_CapitalCost', 'Technology', ['D_Battery_Li-Ion'], m, 'S11 FEOC: BNEF Dec 2025 North-America pack premium +44 % decaying as domestic cells ramp (20 -> 140 GWh/yr by 2028)')
    cost_multiplier(S, 'Par_CapitalCostStorage', 'Storage', ['S_Battery_Li-Ion'], m, 'S11 FEOC: same premium on the energy component', storage=True)
    cc = read_base('Par_CapitalCost'); pv = sorted({t for t in cc.Technology.unique() if t.startswith('P_PV')})
    cost_multiplier(S, 'Par_CapitalCost', 'Technology', pv, {y: 1.02 for y in range(2026, 2031)}, 'S11 FEOC: western inverter premium ~2 % of PV capex 2026-30 (Wood Mackenzie)')
    tc = read_base('Par_TradeCapacityGrowthCosts')
    ov(S, 'Par_TradeCapacityGrowthCosts', [{'Region': r.Region, 'Region2': r.Region2, 'Fuel': r.Fuel, 'Value': fmt(num(r.Value) * 1.2, 6), 'Unit': 'M€/GWkm'} for r in tc.itertuples(index=False) if r.Fuel == 'Power' and r.Region in NA and r.Region2 in NA and num(r.Value) is not None], 'S11 FEOC: transformer prices +77 % / lead times 128-144 wk -> IC expansion cost x1.2 (whole horizon; parameter has no year dimension, mean of x1.30 2026-30 -> x1.10 2035)')
    ov(S, 'Par_GroupTotalAnnualMaxNewCap', group_cap_rows('LiIon', 'USA', {2026: 17.0, 2027: 17.0}), 'S11 FEOC: US Li-ion additions capped at 17 GW/yr 2026-27 (WoodMac/ACP: 2026 below the 18.9 GW of 2025 for lack of FEOC-compliant BESS)')
    # the base Li-ion minimum path (US Pools storage trajectory) forces more than 17 GW/yr in 2026-27:
    # scale the 2026/2027 minimum increments so the forced build fits under the cap (2028+ minima unchanged)
    mn = read_base('Par_TotalAnnualMinCapacity'); mn = mn[(mn.Technology == 'D_Battery_Li-Ion') & mn.Region.isin(US)]
    m = {(r.Region, int(r.Year)): num(r.Value) or 0.0 for r in mn.itertuples(index=False) if r.Year.isdigit()}
    rows = []
    for y, cap_cum in ((2026, 17.0), (2027, 34.0)):
        inc = {r: max(m.get((r, y), 0.0) - m.get((r, 2025), 0.0), 0.0) for r in US}
        tot = sum(inc.values())
        scale = min(1.0, cap_cum / tot) if tot > 0 else 1.0
        for r in US:
            rows.append({'Region': r, 'Technology': 'D_Battery_Li-Ion', 'Year': str(y), 'Value': fmt(m.get((r, 2025), 0.0) + inc[r] * scale, 4), 'Unit': 'GW'})
    ov(S, 'Par_TotalAnnualMinCapacity', rows, 'S11 FEOC: Li-ion forced minimum for 2026-27 scaled to fit under the 17 GW/yr US cap (base minimum increments scaled proportionally; 2028+ unchanged)')


def s12_overbuild():
    S = 'NorthAmerica_s12_overbuild'
    us = blend_from_base('Power_DataCenter', {2030: 540, 2035: 620, 2040: 690})
    demand_rows(S, 'Power_DataCenter', scale_path('Power_DataCenter', us, canada='ratio'), 'S12 AI overbuild correction: Grid Strategies (utility DC forecasts overstated ~25 GW / 40 %) ~ LBNL 2026 low case 521 TWh in 2030, then +2 %/yr; Canada scaled with the US ratio')


def s13_reindustrial():
    S = 'NorthAmerica_s13_reindustrial'
    adders = {
        'WECC': {2027: 0, 2030: 9.5, 2035: 22, 2040: 25},        # TSMC AZ 3 -> 6 fabs, Micron Boise
        'NewYork': {2029: 0, 2030: 0, 2033: 6, 2035: 6, 2040: 13}, # Micron Clay 2 -> 4 fabs
        'ERCOT': {2027: 0, 2030: 6 + 30, 2035: 13 + 79, 2040: 13 + 79},  # Samsung/TI fabs + 25 % of the non-DC large-load queue
        'PJM': {2030: 0, 2035: 3, 2040: 6},                      # Intel Ohio 2031+
        'SPP': {2029: 0, 2030: 5.35, 2031: 10.7, 2040: 10.7},    # Century/EGA Inola 750 kt/yr x 14.3 MWh/t
        'MISO': {2027: 0, 2030: 3, 2035: 6, 2040: 8},            # steel EAF/DRI, battery, defense (stylised)
        'SERC': {2027: 0, 2030: 3, 2035: 6, 2040: 8},
    }
    flat_adder(S, 'Power_LargeLoads', adders, 'S13 reindustrialization: fabs ~3.6 TWh/yr per 100k-wafer/month fab (TSMC 37.1 kWh per 12-inch wafer mask layer x ~80 layers), Century/EGA smelter, 25 % realisation of the ERCOT non-DC queue (~45 GW), stylised steel/battery/defense adders')
    ov(S, 'Par_TagFuelToTimeseries', [{'Fuel': 'Power_LargeLoads', 'Profile': 'POWER_DATACENTER', 'Value': '1', 'Unit': 'Binary'}], 'flat profile for large loads')


def s14_decarb():
    S = 'NorthAmerica_s14_decarb'
    price = {2028: 0, 2029: 30, 2035: 60, 2040: 90}     # USD/t -> MEUR/Gt: x 1e3 x EUR/USD
    ov(S, 'Par_EmissionsPenalty', [{'Region': r, 'Emission': 'CO2', 'Year': str(y), 'Value': fmt(interp(price, y) * 1e3 * USD, 1), 'Unit': 'M€ / Gt'} for r in NA for y in YEARS], 'S14: CO2 price 30 (2029) -> 60 (2035) -> 90 USD/t (2040) in the US, anchored on 45Q 85 USD/t as the revealed federal CO2 value; Canada follows the same path (its industrial OBPS benchmark price, C$95/t 2026 -> C$170/t 2030, is of the same order)')
    m = {y: 0.70 for y in range(2029, 2041)}
    cc = read_base('Par_CapitalCost')
    res = sorted({t for t in cc.Technology.unique() if t.startswith(('P_PV', 'P_Wind', 'D_Battery', 'P_Geothermal', 'P_EGS'))})
    cost_multiplier(S, 'Par_CapitalCost', 'Technology', res, m, 'S14: restored 30 % ITC on RES and storage from 2029 (45Y/48E ended for wind/solar under OBBBA)')
    cost_multiplier(S, 'Par_CapitalCostStorage', 'Storage', ['S_Battery_Li-Ion', 'S_Battery_Redox'], m, 'S14: restored 30 % ITC (storage energy component)', storage=True)
    ccs_tot = {2029: 0, 2030: 2, 2035: 15, 2040: 40}; ccs_sh = {'SERC': .30, 'ERCOT': .25, 'PJM': .20, 'MISO': .15, 'California': .10}
    ov(S, 'Par_TotalAnnualMaxCapacity', [{'Region': r, 'Technology': 'P_Gas_CCS', 'Year': str(y), 'Value': fmt(interp(ccs_tot, y) * ccs_sh.get(r, 0), 3), 'Unit': 'GW'} for r in US for y in YEARS], 'S14: CCPP+CCUS enabled 2/15/40 GW (2030/35/40) (Sutter 550 MW, Baytown 810 MW as FOAK; NETL Rev 3 costs)')
    vc = read_base('Par_VariableCost'); base_vc = [r for r in vc.itertuples(index=False) if r.Technology == 'P_Gas_CCS' and r.Region == 'World']
    bv = {r.Year: num(r.Value) or 0.0 for r in base_vc}
    def b(y):
        return bv.get(str(y), bv.get('All', 0.0))
    ov(S, 'Par_VariableCost', [{'Region': 'World', 'Technology': 'P_Gas_CCS', 'Mode_of_operation': '1', 'Year': str(y), 'Value': fmt(b(y) - (7.95 if y >= 2029 else 0), 4), 'Unit': 'MEUR/PJ'} for y in YEARS], 'S14: 45Q 85 USD/t x 90 % capture x 112.7 kt CO2 per PJ electricity (IAR 2.02, 55.8 kt/PJ gas) = -7.95 MEUR/PJ 2029-2040 as a negative variable cost (12-year term approximated)')
    for par in ('Par_TotalAnnualMinCapacity', 'Par_TotalAnnualMaxCapacity'):
        copy_overlay(S, 'NorthAmerica_nuclear_announced', par, 'S14: announced nuclear (+19.1 GW by 2035 incl. hyperscaler SMR/restarts)')
    # uprates +2.5 GW 2027, +5 GW 2029 on P_Nuclear minima (by base 2025 nuclear minimum share)
    mn = read_base('Par_TotalAnnualMinCapacity'); nuc = mn[(mn.Technology == 'P_Nuclear') & mn.Region.isin(US)]
    b25 = {r.Region: num(r.Value) or 0.0 for r in nuc[nuc.Year == '2025'].itertuples(index=False)}; tot25 = sum(b25.values()) or 1.0
    base_min = {(r.Region, int(r.Year)): num(r.Value) or 0.0 for r in nuc.itertuples(index=False) if r.Year.isdigit()}
    ann = pd.read_csv(sub_path('Par_TotalAnnualMinCapacity', 'NorthAmerica_nuclear_announced'), dtype=str, keep_default_na=False, encoding='utf-8-sig')
    ann.columns = [c.strip() for c in ann.columns]
    ann_min = {(r.Region, int(r.Year)): num(r.Value) or 0.0 for r in ann.itertuples(index=False) if r.Technology == 'P_Nuclear' and r.Year.isdigit()}
    rows = []
    for r in US:
        for y in YEARS:
            up = (2.5 if y >= 2027 else 0) + (2.5 if y >= 2029 else 0)
            if up == 0:
                continue
            v = ann_min.get((r, y), base_min.get((r, y), 0.0)) + up * b25.get(r, 0) / tot25
            rows.append({'Region': r, 'Technology': 'P_Nuclear', 'Year': str(y), 'Value': fmt(v, 3), 'Unit': 'GW'})
    ov(S, 'Par_TotalAnnualMinCapacity', rows, 'S14: DOE UPRISE uprates +2.5 GW by 2027, +5 GW by 2029 on top of the announced-nuclear minima (allocated by 2025 fleet share)')
    # state CES proxy: regional power CO2 caps vs 2025 (v6c: NY 57.9, NE 67.8, CA 138.5, PJM 244.5 Mt)
    caps = {'NewYork': (57.9, .80), 'NewEngland': (67.8, .70), 'California': (138.5, .60), 'PJM': (244.5, .40)}
    rows = []
    for r, (e25, red) in caps.items():
        for y in YEARS:
            if y < 2029:
                rows.append({'Region': r, 'Emission': 'CO2', 'Year': str(y), 'Value': '999999', 'Unit': 'Gigatonnes'})
            else:
                rows.append({'Region': r, 'Emission': 'CO2', 'Year': str(y), 'Value': fmt(e25 / 1000 * (1 - red * (y - 2028) / 12), 5), 'Unit': 'Gigatonnes'})
    ov(S, 'Par_RegionalAnnualEmissionLimit', rows, 'S14: state 100 %-clean targets as regional power-CO2 caps (NY 2040, CT 2040, NJ 2035, CA 2045; PJM partial): -80/-70/-60/-40 % by 2040 vs the v6c 2025 level, linear from 2029')


SCEN = {
    's01': ('NorthAmerica_s01_ev', s01_ev, None),
    's02': ('NorthAmerica_s02_h2', s02_h2, None),
    's03': ('NorthAmerica_s03_compute', s03_compute, dict(fuels=['Power_LargeLoads'], modes=[7])),
    's04': ('NorthAmerica_s04_space', s04_space, dict(fuels=['Power_LargeLoads'], modes=[7])),
    's05': ('NorthAmerica_s05_brakes', s05_brakes, None),
    's06': ('NorthAmerica_s06_hormuz', s06_hormuz, None),
    's07': ('NorthAmerica_s07_tech', s07_tech, dict(techs=['P_Fusion', 'D_IronAir', 'P_Nuclear_SMR'], storages=['S_IronAir'])),
    's08': ('NorthAmerica_s08_canada', s08_canada, None),
    's09': ('NorthAmerica_s09_water', s09_water, dict(fuels=['Power_LargeLoads'], modes=[7])),
    's10': ('NorthAmerica_s10_climate', s10_climate, None),
    's11': ('NorthAmerica_s11_feoc', s11_feoc, None),
    's12': ('NorthAmerica_s12_overbuild', s12_overbuild, None),
    's13': ('NorthAmerica_s13_reindustrial', s13_reindustrial, dict(fuels=['Power_LargeLoads'], modes=[7])),
    's14': ('NorthAmerica_s14_decarb', s14_decarb, None),
}

if __name__ == '__main__':
    print('repo:', REPO, '| apply:', APPLY)
    nb = base_additions()
    print(f'base additions (new set members / properties): {nb} rows')
    for key, (name, fn, filt) in SCEN.items():
        if ONLY and key not in ONLY:
            continue
        fn()
        if filt:
            filter_file(name, **filt)
        print(f'{name:32s}', {p: n for p, n in written.get(name, {}).items()}, '| filter:', 'own' if filt else 'base')
    print('APPLIED' if APPLY else 'DRY RUN (use --apply)')
