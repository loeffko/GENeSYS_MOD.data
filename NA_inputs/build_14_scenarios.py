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

Usage:  python NA_inputs/build_14_scenarios.py [--apply] [--repo <path>] [--only s01,s07,open]
        ('open' = the funnel-released twins sNN_<name>_open; built after the scenarios unless --only excludes it)
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
TODAY = '2026-10-02'
PLAN = 'FEEDBACK_PLAN_wave4_2026-10-02.md (wave 4; waves 1-3: NA_scenario_plan_2026-09-18_v4.xlsx)'
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


def set_base_rows(fname, keycols, keyvals, newval, note, sub=''):
    """Overwrite Value of existing base rows matching any of keyvals (tuples over keycols)."""
    p = os.path.join(PAR, sub, fname) if sub else os.path.join(PAR, fname)
    df = pd.read_csv(p, dtype=str, keep_default_na=False, encoding='utf-8-sig')
    df.columns = [c.strip() for c in df.columns]
    keyset = set(keyvals)
    mask = df[keycols].apply(tuple, axis=1).isin(keyset)
    n = int(mask.sum())
    if n and APPLY:
        df.loc[mask, 'Value'] = str(newval)
        if 'Source' in df.columns:
            df.loc[mask, 'Source'] = note
        if 'Updated at' in df.columns:
            df.loc[mask, 'Updated at'] = TODAY; df.loc[mask, 'Updated by'] = WHO
        df.to_csv(p, index=False, header=[('' if h.startswith('Unnamed') else h) for h in df.columns], lineterminator='\n')
    return n


def remove_base_rows(fname, keycols, keyvals, sub='00_Sets&Tags'):
    p = os.path.join(PAR, sub, fname) if sub else os.path.join(PAR, fname)
    df = pd.read_csv(p, dtype=str, keep_default_na=False, encoding='utf-8-sig')
    df.columns = [c.strip() for c in df.columns]
    mask = df[keycols].apply(tuple, axis=1).isin(set(keyvals))
    n = int(mask.sum())
    if n and APPLY:
        df[~mask].to_csv(p, index=False, header=[('' if h.startswith('Unnamed') else h) for h in df.columns], lineterminator='\n')
    return n


def set_base_rows_map(fname, keycols, newvals, note, sub=''):
    """Overwrite Value of existing base rows per key: newvals = {keytuple: value}. One pass."""
    p = os.path.join(PAR, sub, fname) if sub else os.path.join(PAR, fname)
    df = pd.read_csv(p, dtype=str, keep_default_na=False, encoding='utf-8-sig')
    df.columns = [c.strip() for c in df.columns]
    keys = df[keycols].apply(tuple, axis=1)
    mask = keys.isin(set(newvals))
    n = int(mask.sum())
    if n and APPLY:
        df.loc[mask, 'Value'] = [str(newvals[k]) for k in keys[mask]]
        if 'Source' in df.columns:
            df.loc[mask, 'Source'] = note
        if 'Updated at' in df.columns:
            df.loc[mask, 'Updated at'] = TODAY; df.loc[mask, 'Updated by'] = WHO
        df.to_csv(p, index=False, header=[('' if h.startswith('Unnamed') else h) for h in df.columns], lineterminator='\n')
    return n


def release_gas_minima(scen, year_from, source):
    """Funnel release: gas guardrail minimum = residual capacity from year_from (US regions)."""
    res = read_base('Par_ResidualCapacity'); res = res[res.Region.isin(US) & res.Technology.isin(GAS_TECHS)]
    rows = [{'Region': r.Region, 'Technology': r.Technology, 'Year': r.Year, 'Value': r.Value, 'Unit': 'GW'}
            for r in res.itertuples(index=False) if r.Year.isdigit() and int(r.Year) >= year_from and num(r.Value) is not None]
    ov(scen, 'Par_TotalAnnualMinCapacity', rows, source)


def open_variant(key):
    """Funnel-released twin of a scenario: every overlay of the parent copied, then the gas minima released from 2031."""
    name, fn, filt = SCEN[key]
    S = name + '_open'
    for par in sorted(os.listdir(PAR)):
        if par.startswith('Par_') and sub_path(par, name):
            copy_overlay(S, name, par, f'{key} definition')
    release_gas_minima(S, 2031, f'{key} open: no forced gas builds after 2030 (guardrail minimum = residual capacity from 2031; announced projects through 2030 kept; build-rate caps unchanged)')
    return S, filt


def base_fixes():
    """Wave-2 base fix (applies to the base workbook AND every scenario): the EU biogas co-firing mode
    (mode 2, Gas_Bio folded from R_Biogas without a resource limit) is disabled for the NA gas plants -
    it produced 1,710 TWh of zero-CO2 'biogas' generation in 2030 in every v6 run (Henry-Hub peak year)
    and absorbs the whole gas fleet under a CO2 price."""
    techs = GAS_TECHS + ['CHP_Gas_CCGT_Natural', 'CHP_Gas_CCGT_Natural_CCS']
    # (2026-09-23) engines must stay outside GasPlants: the base has separate GasPlants and GasEngines new-build caps
    remove_base_rows('Par_TagTechnologyToSubsets.csv', ['Technology', 'Subset'], [('P_Gas_Engines', 'GasPlants')])
    n = set_base_rows('Par_OutputActivityRatio/Par_OutputActivityRatio.csv', ['Region', 'Technology', 'Fuel', 'Mode_of_operation', 'Year'],
                      [('World', t, 'Power', '2', 'All') for t in techs], '0',
                      'biogas co-firing mode disabled for North America (no biogas resource limit in the power-only data; 2026-09-23 wave-2 fix)')
    # (2026-09-24, wave-3 fix, review N4) gas steam: the guardrail minimum is held flat after 2035 while the residual
    # fleet keeps retiring, which forced ~12 GW of new steam units 2026-40 -> clamp the minimum to the residual path
    res = read_base('Par_ResidualCapacity'); res = res[res.Technology == 'P_Gas_Steam']
    resv = {(r.Region, r.Year): num(r.Value) for r in res.itertuples(index=False) if num(r.Value) is not None}
    mn = read_base('Par_TotalAnnualMinCapacity'); mn = mn[mn.Technology == 'P_Gas_Steam']
    clamp = {}
    for r in mn.itertuples(index=False):
        v = num(r.Value); rv = resv.get((r.Region, r.Year))
        if v is not None and rv is not None and v > rv + 1e-6:
            clamp[(r.Region, 'P_Gas_Steam', r.Year)] = fmt(rv, 6)
    n += set_base_rows_map('Par_TotalAnnualMinCapacity/Par_TotalAnnualMinCapacity.csv', ['Region', 'Technology', 'Year'], clamp,
                           'US Pools widening band (min) clamped to the residual fleet: no new gas steam builds (2026-09-24 wave-3 fix)')
    return n


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
    # ---- (2026-09-24, wave-3 fix, review N1) rooftop PV build-rate cap: rooftop had no pipeline minimum and no
    # build-rate limit (only the flat restool potential), so it bypassed the utility-PV pipeline funnel at ~31 GW/yr
    # (4x the US record). National cap on new capacity via a group limit (per-tech investment caps are not a data
    # sheet): EIA small-scale solar additions 6.4 GW in 2022 (record; 39.5 GW total) and STEO 44 GW (Jun-2023)
    # -> 55 GW (end-2024) = ~7.7 GW/yr -> 7 GW/yr 2026-30, growing to 10 GW/yr by 2040 (assumption, flagged).
    n += add_base_rows('Par_TagTechnologyToSubsets.csv', [{'Technology': 'P_PV_Rooftop_Commercial', 'Subset': 'RooftopPV', 'Value': '1', 'Unit': 'Binary', 'Source': 'rooftop build-rate group cap (wave-3 fix, review N1)'}], ['Technology', 'Subset'])
    roof = {2026: 7.0, 2030: 7.0, 2040: 10.0}
    n += add_base_rows('Par_GroupTotalAnnualMaxNewCap/Par_GroupTotalAnnualMaxNewCap.csv',
                       [{'TechnologySubset': 'RooftopPV', 'RegionSubset': 'USA', 'Year': str(y), 'Value': fmt(interp(roof, y) if y >= 2026 else 999999, 3), 'Unit': 'GW',
                         'Source': 'US distributed-PV build rate: EIA small-scale additions 6.4 GW 2022 (TIE 2023-09-11), STEO 44 GW Jun-2023 -> 55 GW end-2024 (~7.7 GW/yr); 7 GW/yr 2026-30 -> 10 GW/yr 2040 (growth assumed)'} for y in YEARS],
                       ['TechnologySubset', 'RegionSubset', 'Year'], sub='')
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
    n += add_base_rows('Par_TagTechnologyToSubsets.csv', [{'Technology': 'P_Gas_CCS', 'Subset': 'GasCCS', 'Value': '1', 'Unit': 'Binary', 'Source': 'scenario s14 group cap (the switch_ccs bounds blanket-enable any CCS TotalAnnualMaxCapacity above the 0.001 marker)'}], ['Technology', 'Subset'])
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
    # wave 4 (NA Hub): even the full snap-back adds only ~16-21 TWh/yr by 2030 (BEV share ~23 % vs ~10 %; hybrids do
    # not plug in). Keep the AEO2026 upside shape but scale it to +20 TWh in 2030 (about +50 TWh in 2040); Canada base.
    src = 'S1 EV comeback (wave 4): NA Hub sizing +20 TWh in 2030 (BEV share 23 % vs 10 % baseline; Cox Automotive / Urban Science via NA Hub), AEO2026-shaped upside after 2030; Canada base'
    aeo = blend_from_base('Power_BEVs', {2030: 146, 2035: 408, 2040: 624})
    base_us = {y: sum(dem('Power_BEVs', r, y) for r in US) / TWH for y in YEARS}
    up = {y: max(interp(aeo, y) - base_us[y], 0.0) for y in YEARS if y >= 2028}
    k = 20.0 / up[2030]
    us = {y: base_us[y] + k * up[y] for y in up}
    demand_rows(S, 'Power_BEVs', scale_path('Power_BEVs', us), src)


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
    crypto = by_share({2026: 0, 2030: 10, 2035: 20, 2040: 20}, {'ERCOT': .40, 'SPP': .15, 'MISO': .15, 'SERC': .10, 'PJM': .10, 'WECC': .10})   # growth above today's ~60 TWh (already in the base load)
    ind = general_share(US)
    robo = by_share({2027: 0, 2028: 5, 2035: 90, 2040: 150}, ind)
    tele = by_share({2029: 0, 2030: 10, 2040: 50}, ind)
    adders = {}
    for d in (crypto, robo, tele):
        for r, pts in d.items():
            adders.setdefault(r, [])
            adders[r].append(pts)
    merged = {r: {y: sum(interp(p, y) for p in lst) for y in YEARS} for r, lst in adders.items()}
    flat_adder(S, 'Power_LargeLoads', merged, 'S3 second-wave flat loads: crypto growth above today (+20 TWh by 2035; CCAF 138 TWh global x 40 % US today, already in the base load), robotics/dark factories (Wood Mackenzie 363 TWh global 2035 x 25 % US), telecom/edge/defense (stated dial)')
    ov(S, 'Par_TagFuelToTimeseries', [{'Fuel': 'Power_LargeLoads', 'Profile': 'POWER_DATACENTER', 'Value': '1', 'Unit': 'Binary'}], 'flat profile for large loads')


def s04_space():
    S = 'NorthAmerica_s04_space'
    shares = {'ERCOT': .5, 'California': .2, 'SERC': .2, 'WECC': .1}
    tot = {2028: 0, 2030: 5, 2035: 35, 2040: 155}   # e-propellant 2/20/100 + manufacturing/ground 3/15/55
    flat_adder(S, 'Power_LargeLoads', by_share(tot, shares), 'S4 space race (terrestrial industry): e-propellant for 100/1,000/5,000 Starship launches per year (~21 GWh each: electrolytic H2 + DAC CO2 + liquefaction) + satellite/launcher manufacturing and ground segment; orbital-compute displacement NOT applied (separate space_dc trio)')
    ov(S, 'Par_TagFuelToTimeseries', [{'Fuel': 'Power_LargeLoads', 'Profile': 'POWER_DATACENTER', 'Value': '1', 'Unit': 'Binary'}], 'flat profile for large loads')


def s05_brakes():
    S = 'NorthAmerica_s05_brakes'
    # wave 4 (NA Hub): "delay, not destruction" plus the speculative tranche only - the DC increment above 2026 is
    # shifted 2 years (ERCOT / New York 3: Texas audit + permit halt, NY moratorium) and only the credible tranche is
    # kept (55 %; ERCOT 66 % = ERCOT-adjusted 145 vs TSP 218 GW; Currence / Jefferies via NA Hub); Canada base
    delay = {r: 2 for r in US}; delay.update({'ERCOT': 3, 'NewYork': 3})
    cred = {r: 0.55 for r in US}; cred['ERCOT'] = 0.66
    vals = {}
    for r in US:
        d26 = dem('Power_DataCenter', r, 2026)
        for y in YEARS:
            if y >= 2027:
                vals.setdefault(r, {})[y] = d26 + cred[r] * (dem('Power_DataCenter', r, max(y - delay[r], 2026)) - d26)
    demand_rows(S, 'Power_DataCenter', vals, 'S5 political brakes (wave 4): DC increment above 2026 delayed 2 years (ERCOT/NY 3: Texas audit + TCEQ permit halt, NY moratorium) and cut to the credible tranche (55 %, ERCOT 66 %; NA Hub / Currence / Jefferies); Canada base')
    gc = read_base('Par_GroupTotalAnnualMaxNewCap')
    base_cap = {(r.TechnologySubset, r.RegionSubset, r.Year): num(r.Value) for r in gc.itertuples(index=False)}
    rows = [{'TechnologySubset': 'GasPlants', 'RegionSubset': 'USA', 'Year': str(y), 'Value': fmt(min(10.0, base_cap.get(('GasPlants', 'USA', str(y)), 999999) or 999999), 3), 'Unit': 'GW'} for y in range(2027, 2032)]
    rows += [{'TechnologySubset': 'GasEngines', 'RegionSubset': 'USA', 'Year': str(y), 'Value': fmt(min(1.0, base_cap.get(('GasEngines', 'USA', str(y)), 999999) or 999999), 3), 'Unit': 'GW'} for y in range(2027, 2032)]
    ov(S, 'Par_GroupTotalAnnualMaxNewCap', rows, 'S5: US gas new-build cap 10 GW/yr (GasPlants) + 1 GW/yr (GasEngines) 2027-31, never above the base caps (base: GasPlants 6/9/10/35/47 GW 2026-31, GasEngines 2.5); other years keep the base caps')
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
    """wave 4 (NA Hub): Hormuz is a live condition; utility capex plans have risen, not frozen -> only the fuel-price
    channel is kept (Henry-Hub uplift 2026-30 in the s06 allFuels workbook, build_s06_allfuels). The capex/WACC
    uplift, the IC cap and the recession demand of waves 1-3 are dropped. No RegularParameters overlay: the run uses
    the base workbook with allFuels_v6_s06; the same workbook swap gives the _hormuz variants of s03/s05/s12/s14."""
    print('  s06: fuel-only (allFuels_v6_s06 workbook), no overlay rows')


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


def s07a_ldes():
    S = 'NorthAmerica_s07a_ldes'
    # wave 4 (NA Hub): split - LDES is a 2027-31 question that erodes peaking economics
    # iron-air: enable from 2028 with a NA build cap; Li-ion optimistic reused
    ov(S, 'Par_TotalAnnualMaxCapacity', [{'Region': r, 'Technology': 'D_IronAir', 'Year': str(y), 'Value': '0' if y < 2027 else '999999', 'Unit': 'GW'} for r in NA for y in YEARS], 'S7a iron-air available from 2027')
    ov(S, 'Par_GroupTotalAnnualMaxNewCap', group_cap_rows('IronAir', 'NorthAmerica', {2025: 0, 2026: 0, 2027: 0.5, 2028: 1.0, 2029: 2.0, 2030: 3.0, 2031: 4.0, **{y: 5.0 for y in range(2032, 2041)}}), 'S7a iron-air build cap: Form pipeline >65 GWh incl. Xcel/Google 30 GWh and Crusoe 12 GWh from 2027 -> 0.5/1/2/3/4/5 GW/yr from 2027')
    for par in ('Par_CapitalCost', 'Par_CapitalCostStorage', 'Par_StorageE2PRatio'):
        copy_overlay(S, 'NorthAmerica_bess_optimistic', par, 'S7a: Li-ion optimistic cost + 7 h duration')
    release_gas_minima(S, 2031, 'S7a: no forced gas builds after 2030 (guardrail minimum = residual from 2031; the breakthrough displaces the speculative gas pipeline; build-rate caps unchanged)')


def s07b_fusion():
    S = 'NorthAmerica_s07b_fusion'
    # wave 4 (NA Hub): split - fusion and SMR are post-2032 and erode baseload
    # SMR fast: max 2/5/15/40 GW (2030/32/35/40), base 2040 regional shares; capex INL advanced -> Liftoff NOAK
    mx = read_base('Par_TotalAnnualMaxCapacity')
    smr40 = {r.Region: num(r.Value) or 0.0 for r in mx[(mx.Technology == 'P_Nuclear_SMR') & (mx.Year == '2040') & mx.Region.isin(NA)].itertuples(index=False)}
    tot40 = sum(smr40.values())
    tot = {2029: 0, 2030: 2, 2032: 5, 2035: 15, 2040: 40}
    base_max = {(r.Region, r.Year): num(r.Value) or 0.0 for r in mx[(mx.Technology == 'P_Nuclear_SMR') & mx.Region.isin(NA)].itertuples(index=False)}
    mn_smr = read_base('Par_TotalAnnualMinCapacity'); mn_smr = mn_smr[(mn_smr.Technology == 'P_Nuclear_SMR') & mn_smr.Region.isin(NA)]
    base_min = {(r.Region, r.Year): num(r.Value) or 0.0 for r in mn_smr.itertuples(index=False)}
    # never below the base maximum or the base (committed) minimum, e.g. Darlington in Canada
    rows = [{'Region': r, 'Technology': 'P_Nuclear_SMR', 'Year': str(y), 'Value': fmt(max(interp(tot, y) * smr40.get(r, 0) / tot40, base_max.get((r, str(y)), 0.0) if base_max.get((r, str(y)), 0.0) < 99999 else 0.0, base_min.get((r, str(y)), 0.0) * 1.001), 4), 'Unit': 'GW'} for r in NA for y in YEARS]
    ov(S, 'Par_TotalAnnualMaxCapacity', rows, 'S7 SMR fast: available 2030, 2/5/15/40 GW (2030/32/35/40) split by the base 2040 regional SMR potential (Darlington, Natrium, Clinch River, Hermes 2; TVA/ENTRA1 6 GW, Meta/Google/Amazon deals)')
    capex = {2030: 5500 * USD, 2035: 4300 * USD, 2040: 3600 * USD}
    ov(S, 'Par_CapitalCost', [{'Region': 'World', 'Technology': 'P_Nuclear_SMR', 'Year': str(y), 'Value': fmt(interp(capex, y), 1), 'Unit': 'MEUR/GW'} for y in YEARS], 'S7 SMR capex: INL/NREL ATB 2025 advanced BOAK 5,500 USD/kW (2030) with 9.5 % learning to the DOE Liftoff NOAK ~3,600 USD/kW by 2040 (base 9,091 EUR/kW flat)')
    # fusion (bull ramp, 100 % located in NA): min = max = cumulative backed ramp
    shares = {'PJM': .4, 'WECC': .2, 'SERC': .2, 'California': .1, 'ERCOT': .1}
    ramp = {2034: 2.0, 2036: 4.25, 2038: 6.75, 2040: 9.5}
    def cum(y):
        return max([v for k, v in ramp.items() if k <= y], default=0.0)
    rows_max = [{'Region': r, 'Technology': 'P_Fusion', 'Year': str(y), 'Value': fmt(cum(y) * s, 3), 'Unit': 'GW'} for r, s in shares.items() for y in YEARS]
    rows_max += [{'Region': r, 'Technology': 'P_Fusion', 'Year': str(y), 'Value': '0', 'Unit': 'GW'} for r in NA if r not in shares for y in YEARS]
    ov(S, 'Par_TotalAnnualMaxCapacity', rows_max, 'S7 fusion: Fusion_Market_Model_v09 bull backed ramp (5 developers x 400/450/500/550 MW at 2034/36/38/40 = 2.0/4.25/6.75/9.5 GW cumulative), 100 % located in NA at announced sites (CFS VA, Helion WA, Type One TN, Pacific Fusion CA, ERCOT)')
    ov(S, 'Par_TotalAnnualMinCapacity', [x for x in rows_max if float(x['Value']) > 0], 'S7 fusion: the backed ramp is must-build (workbook logic)')
    release_gas_minima(S, 2031, 'S7b: no forced gas builds after 2030 (guardrail minimum = residual from 2031; the breakthrough displaces the speculative gas pipeline; build-rate caps unchanged)')


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
    s = {2029: 0, 2035: 0.0, 2040: .05}   # wave 4 (NA Hub): relocation lags beyond the MEP27 horizon
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
    src = 'S10 Great Reshuffle (wave 4): 0 % (2035) / 5 % (2040) of SERC+ERCOT+California General and DC load re-allocated to MISO/PJM/NewEngland/NewYork/WECC by load share (First Street: 55 M movers by 2055); Sunbelt cooling +8 % by 2040 (CDD +10-80 %); rebuild load +1 %'
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
                    cut = min(0.01 * (y - 2029), 0.05)                       # -1 pp/yr 2030-34, -5 pp from 2034 (wave 3: ramp instead of step)
                    rows.append({'Region': reg, 'Technology': t, 'Year': str(y), 'Value': fmt(max(v - cut, 0.05), 4), 'Unit': 'Fraction'})
    ov(S, 'Par_AvailabilityFactor', rows, 'S10: storm outages, coastal gas/nuclear availability -1 pp/yr from 2030 to -5 pp in 2034')


def s11_feoc():
    S = 'NorthAmerica_s11_feoc'
    m = {2026: 1.44, 2027: 1.37, 2028: 1.30, 2029: 1.22, 2030: 1.15}
    m.update({y: 1.15 + (1.05 - 1.15) * (y - 2030) / 5 for y in range(2031, 2036)}); m.update({y: 1.05 for y in range(2036, 2041)})
    cost_multiplier(S, 'Par_CapitalCost', 'Technology', ['D_Battery_Li-Ion'], m, 'S11 FEOC: BNEF Dec 2025 North-America pack premium +44 % decaying as domestic cells ramp (20 -> 140 GWh/yr by 2028)')
    cost_multiplier(S, 'Par_CapitalCostStorage', 'Storage', ['S_Battery_Li-Ion'], m, 'S11 FEOC: same premium on the energy component', storage=True)
    cc = read_base('Par_CapitalCost'); pv = sorted({t for t in cc.Technology.unique() if t.startswith('P_PV')})
    cost_multiplier(S, 'Par_CapitalCost', 'Technology', pv, {y: 1.02 for y in range(2026, 2031)}, 'S11 FEOC: western inverter premium ~2 % of PV capex 2026-30 (Wood Mackenzie)')
    tc = read_base('Par_TradeCapacityGrowthCosts')
    ov(S, 'Par_TradeCapacityGrowthCosts', [{'Region': r.Region, 'Region2': r.Region2, 'Fuel': r.Fuel, 'Value': fmt(num(r.Value) * 1.2 * 1.15, 6), 'Unit': 'M€/GWkm'} for r in tc.itertuples(index=False) if r.Fuel == 'Power' and r.Region in NA and r.Region2 in NA and num(r.Value) is not None], 'S11 FEOC + tariffs (wave 4): transformer prices +77 % / lead times 128-144 wk -> IC expansion cost x1.2, times x1.15 for the Section 232 transformer tariff (NA Hub proposal D); whole horizon, parameter has no year dimension')
    ov(S, 'Par_GroupTotalAnnualMaxNewCap', group_cap_rows('LiIon', 'USA', {2026: 17.0, 2027: 17.0}), 'S11 FEOC: US Li-ion additions capped at 17 GW/yr 2026-27 (WoodMac/ACP: 2026 below the 18.9 GW of 2025 for lack of FEOC-compliant BESS)')
    # the base Li-ion minimum path (US Pools storage trajectory) forces more than 17 GW/yr in 2026-27:
    # scale the 2026/2027 minimum increments so the forced build fits under the cap (2028+ minima unchanged)
    mn = read_base('Par_TotalAnnualMinCapacity'); mn = mn[(mn.Technology == 'D_Battery_Li-Ion') & mn.Region.isin(US)]
    m = {(r.Region, int(r.Year)): num(r.Value) or 0.0 for r in mn.itertuples(index=False) if r.Year.isdigit()}
    rc = read_base('Par_ResidualCapacity'); rc = rc[(rc.Technology == 'D_Battery_Li-Ion') & rc.Region.isin(US)]
    res = {(r.Region, int(r.Year)): num(r.Value) or 0.0 for r in rc.itertuples(index=False) if r.Year.isdigit()}
    rows = []
    for y, cap_cum in ((2026, 17.0), (2027, 34.0)):
        # new build needed above the (retiring) residual fleet; NewCapacity is fixed to 0 in 2025
        inc = {r: max(m.get((r, y), 0.0) - res.get((r, y), 0.0), 0.0) for r in US}
        tot = sum(inc.values())
        scale = min(1.0, 0.98 * cap_cum / tot) if tot > 0 else 1.0
        for r in US:
            rows.append({'Region': r, 'Technology': 'D_Battery_Li-Ion', 'Year': str(y), 'Value': fmt(res.get((r, y), 0.0) + inc[r] * scale, 4), 'Unit': 'GW'})
    ov(S, 'Par_TotalAnnualMinCapacity', rows, 'S11 FEOC: Li-ion forced minimum for 2026-27 scaled to fit under the 17 GW/yr US cap (base minimum increments scaled proportionally; 2028+ unchanged)')


def s12_overbuild():
    S = 'NorthAmerica_s12_overbuild'
    # wave 4 (NA Hub): stress the speculative tranche only - of 182 GW planned for 2026-30 only ~101 GW is credible
    # (55 %; ERCOT TSP 218 vs ERCOT-adjusted 145 GW = 66 %), hyperscaler capex digestion with negative growth 2031-32,
    # growth resumes at the FEL rate after; Canada base (US scope)
    cred = {r: 0.55 for r in US}; cred['ERCOT'] = 0.66
    vals = {}
    for r in US:
        d26 = dem('Power_DataCenter', r, 2026)
        path = {y: d26 + cred[r] * (dem('Power_DataCenter', r, y) - d26) for y in range(2027, 2031)}
        path[2031] = path[2030]; path[2032] = path[2030]
        for y in range(2033, 2041):
            path[y] = path[2032] + (dem('Power_DataCenter', r, y) - dem('Power_DataCenter', r, 2032))
        vals[r] = path
    demand_rows(S, 'Power_DataCenter', vals, 'S12 AI overbuild (wave 4): credible tranche only (55 % of the 2026-30 DC increment, ERCOT 66 %: Currence / Jefferies / Greenwich via NA Hub), flat 2031-32 (capex digestion, Piper Sandler), FEL growth rate after; Canada base')
    release_gas_minima(S, 2031, 'S12: no forced gas builds after 2030 (guardrail minimum = residual from 2031; the overbuild correction cancels the speculative gas pipeline; build-rate caps unchanged)')


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
    # wave 4 (NA Hub): elevate - up to ~30 GW of new US load from reindustrialization (TransAlta; 1/3-1/2 of non-AI
    # growth), i.e. ~236 TWh at 90 % LF by 2035, flat after; the wave-3 regional pattern is kept and scaled
    target35 = 30.0 * 8.76 * 0.9
    k = target35 / sum(interp(p, 2035) for p in adders.values())
    scaled = {r: {y: interp(p, min(y, 2035)) * k for y in YEARS} for r, p in adders.items()}
    # named point loads: Starbase Louisiana (Pecan Island; construction 2027, first launch 2029; own methane
    # production and power = propellant/industrial load), Starbase TX + central-Texas chip plant, Permian oil & gas
    # electrification (SPS summer peak +32 %). 2 GW each at 0.9 LF, Permian +1.6 GW at 0.8 LF (NA Hub; sizes assumed)
    pts = {'SERC': {2028: 0, 2029: 3.0, 2032: 10.0, 2035: 2 * 8.76 * 0.9},
           'ERCOT': {2027: 0, 2028: 2.0, 2031: 8.0, 2033: 2 * 8.76 * 0.9},
           'SPP': {2027: 0, 2032: 1.6 * 8.76 * 0.8}}
    for r, p in pts.items():
        for y in YEARS:
            scaled.setdefault(r, {})[y] = scaled[r].get(y, 0.0) + interp(p, y)
    flat_adder(S, 'Power_LargeLoads', scaled, 'S13 reindustrialization (wave 4): ~30 GW by 2035 (TransAlta via NA Hub; 236 TWh at 90 % LF, flat after) on the wave-3 regional pattern (fabs AZ/ID/NY/TX, Century/EGA smelter, ERCOT non-DC queue, stylised steel/battery/defense) + Starbase Louisiana 2 GW (SERC), Starbase TX + chip plant 2 GW (ERCOT), Permian O&G electrification 1.6 GW (SPP)')
    ov(S, 'Par_TagFuelToTimeseries', [{'Fuel': 'Power_LargeLoads', 'Profile': 'POWER_DATACENTER', 'Value': '1', 'Unit': 'Binary'}], 'flat profile for large loads')


def s14_decarb():
    S = 'NorthAmerica_s14_decarb'
    price = {2028: 0, 2029: 30, 2035: 60, 2040: 90}     # USD/t -> MEUR/Gt: x 1e3 x EUR/USD
    ov(S, 'Par_EmissionsPenalty', [{'Region': r, 'Emission': 'CO2', 'Year': str(y), 'Value': fmt(interp(price, y) * 1e3 * USD, 1), 'Unit': 'M€ / Gt'} for r in NA for y in YEARS], 'S14: CO2 price 30 (2029) -> 60 (2035) -> 90 USD/t (2040) in the US, anchored on 45Q 85 USD/t as the revealed federal CO2 value; Canada follows the same path (its industrial OBPS benchmark price, C$95/t 2026 -> C$170/t 2030, is of the same order)')
    m = {2029: 0.90, 2030: 0.80, **{y: 0.70 for y in range(2031, 2041)}}   # phased in 2029-31 to avoid a single-year build spike (reviewer check 2026-09-23)
    cc = read_base('Par_CapitalCost')
    res = sorted({t for t in cc.Technology.unique() if t.startswith(('P_PV', 'P_Wind', 'D_Battery', 'P_Geothermal', 'P_EGS'))})
    cost_multiplier(S, 'Par_CapitalCost', 'Technology', res, m, 'S14: restored 30 % ITC on RES and storage phased in 2029-31 (x0.9/0.8/0.7; 45Y/48E ended for wind/solar under OBBBA)')
    cost_multiplier(S, 'Par_CapitalCostStorage', 'Storage', ['S_Battery_Li-Ion', 'S_Battery_Redox'], m, 'S14: restored 30 % ITC (storage energy component)', storage=True)
    ccs_tot = {2029: 0, 2030: 2, 2035: 15, 2040: 40}; ccs_sh = {'SERC': .30, 'ERCOT': .25, 'PJM': .20, 'MISO': .15, 'California': .10}
    ov(S, 'Par_TotalAnnualMaxCapacity', [{'Region': r, 'Technology': 'P_Gas_CCS', 'Year': str(y), 'Value': fmt(interp(ccs_tot, y) * ccs_sh.get(r, 0), 3), 'Unit': 'GW'} for r in US for y in YEARS], 'S14: CCPP+CCUS enabled 2/15/40 GW (2030/35/40) (Sutter 550 MW, Baytown 810 MW as FOAK; NETL Rev 3 costs) - regional rows only enable the technology (the model blanket-lifts CCS caps > 0.001 GW); the binding limit is the GasCCS group cap')
    ov(S, 'Par_GroupTotalAnnualMaxCapacity', group_cap_rows('GasCCS', 'USA', {y: interp(ccs_tot, y) for y in YEARS}), 'S14: US-wide CCPP+CCUS capacity cap 0 (to 2029) -> 2 (2030) -> 15 (2035) -> 40 GW (2040), FOAK-limited pipeline')
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
    # the EU biogas co-firing mode (mode 2, R_Biogas folded at ~5.8 MEUR/PJ, no CO2, unlimited in the
    # power-only data) would absorb all gas generation under a CO2 price -> disable it in this scenario
    ov(S, 'Par_OutputActivityRatio', [{'Region': 'World', 'Technology': t, 'Fuel': 'Power', 'Mode_of_operation': '2', 'Year': 'All', 'Value': '0', 'Unit': 'PJ'}
                                      for t in GAS_TECHS + ['CHP_Gas_CCGT_Natural']],
       'S14: biogas co-firing mode (mode 2) disabled - the NA power-only data has no biogas resource limit, so with a CO2 price the whole gas fleet would switch to it (found in the first s14 run)')
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
    release_gas_minima(S, 2031, 'S14: no forced gas builds after 2030 (guardrail minimum = residual from 2031; a 90 USD/t policy world cancels the speculative gas pipeline; build-rate caps unchanged)')


def s15_afford():
    S = 'NorthAmerica_s15_afford'
    # wave 4 (NA Hub proposal A, "affordability backlash and the large-load cost-allocation fight"):
    # (1) large-load tariffs with deposits, collateral and ramp schedules (PA PUC, Texas, Louisiana EO, Ratepayer
    #     Protection Act H.R. 9340, FERC 206) delay the grid-connected DC increment by one year (US; Canada base)
    vals = {}
    for r in US:
        for y in YEARS:
            if y >= 2027:
                vals.setdefault(r, {})[y] = dem('Power_DataCenter', r, y - 1)
    demand_rows(S, 'Power_DataCenter', vals, 'S15 affordability / cost allocation: large-load tariffs with deposits, collateral and ramp schedules delay the grid-connected DC increment by one year (NA Hub proposal A); Canada base')
    # (2) ratepayer protection limits the socialised transmission build: IC growth = v6 grid_low path (0.75 %/yr)
    copy_overlay(S, 'NorthAmerica_grid_low', 'Par_AnnualMaxTradeCapacity', 'S15: ratepayer protection limits socialised transmission build - interconnector growth capped at 0.75 %/yr (v6 grid_low path)')
    # (3) bring-your-own-generation (40 % of the DC increment served by dedicated gas) is an ownership shift: in a
    #     nodal model it adds no capacity beyond the announced-pipeline minimum (which already exceeds the
    #     BYOG-equivalent) -> reported as a metric in the analysis, not forced here


def s16_gridhigh():
    S = 'NorthAmerica_s16_gridhigh'
    # wave 4 (NA Hub proposal F, transmission supercycle): the v6 grid_high interconnector path only (aggregate IC
    # budget 2x the 2025 installed by 2040 with the corridor funnel); approved programmes as the narrative anchor
    # (MISO Tranche 2.1 22 bn, PJM 11.8 bn, SPP 9-10 bn USD). The gas-funnel part of grid_high is NOT used.
    for par in ('Par_AnnualMaxTradeCapacity', 'Par_AnnualMinTradeCapacity', 'Par_GroupAnnualMaxTradeCapacity'):
        copy_overlay(S, 'NorthAmerica_grid_high', par, 'S16 transmission supercycle: v6 grid_high interconnector path (aggregate IC budget 2x installed by 2040; MISO Tranche 2.1 / PJM RTEP / SPP approved programmes as the anchor, NA Hub proposal F)')


SCEN = {
    's01': ('NorthAmerica_s01_ev', s01_ev, None),
    's02': ('NorthAmerica_s02_h2', s02_h2, None),
    's03': ('NorthAmerica_s03_compute', s03_compute, dict(fuels=['Power_LargeLoads'], modes=[7])),
    's04': ('NorthAmerica_s04_space', s04_space, dict(fuels=['Power_LargeLoads'], modes=[7])),
    's05': ('NorthAmerica_s05_brakes', s05_brakes, None),
    's06': ('NorthAmerica_s06_hormuz', s06_hormuz, None),
    's07a': ('NorthAmerica_s07a_ldes', s07a_ldes, dict(techs=['D_IronAir'], storages=['S_IronAir'])),
    's07b': ('NorthAmerica_s07b_fusion', s07b_fusion, dict(techs=['P_Fusion', 'P_Nuclear_SMR'])),
    's08': ('NorthAmerica_s08_canada', s08_canada, None),
    's09': ('NorthAmerica_s09_water', s09_water, dict(fuels=['Power_LargeLoads'], modes=[7])),
    's10': ('NorthAmerica_s10_climate', s10_climate, None),
    's11': ('NorthAmerica_s11_feoc', s11_feoc, None),
    's12': ('NorthAmerica_s12_overbuild', s12_overbuild, None),
    's13': ('NorthAmerica_s13_reindustrial', s13_reindustrial, dict(fuels=['Power_LargeLoads'], modes=[7])),
    's14': ('NorthAmerica_s14_decarb', s14_decarb, None),
    's15': ('NorthAmerica_s15_afford', s15_afford, None),
    's16': ('NorthAmerica_s16_gridhigh', s16_gridhigh, None),
}

if __name__ == '__main__':
    print('repo:', REPO, '| apply:', APPLY)
    nb = base_additions()
    print(f'base additions (new set members / properties): {nb} rows')
    nf = base_fixes()
    print(f'base fixes (biogas mode disabled for gas plants): {nf} rows')
    for key, (name, fn, filt) in SCEN.items():
        if ONLY and key not in ONLY:
            continue
        fn()
        if filt:
            filter_file(name, **filt)
        print(f'{name:32s}', {p: n for p, n in written.get(name, {}).items()}, '| filter:', 'own' if filt else 'base')
    if not ONLY or 'open' in ONLY:
        for key in SCEN:
            if key == 's05':
                continue
            S, filt = open_variant(key)
            if filt:
                filter_file(S, **filt)
            print(f'{S:32s}', {p: n for p, n in written.get(S, {}).items()}, '| filter:', 'own' if filt else 'base')
    print('APPLIED' if APPLY else 'DRY RUN (use --apply)')
