# -*- coding: utf-8 -*-
"""Build the NorthAmerica_gas scenario: explicit natural gas in the NA power model.

Writes (a) new set members + tags into 00_Sets&Tags (harmless to other datasets:
their filter files do not select them), (b) scenario-subfolder overlays
Data/Parameters/Par_X/NorthAmerica_gas/Par_X.csv, (c) the TS_GAS_NONPOWER hourly
profile, (d) Set_filter_file_NorthAmerica_gas.xlsx, (e) Assumptions.txt notes.
Inputs: NA_inputs/gas_research/*.csv (EIA/CER-derived, see README there) and the
proposal GENeSYSMOD.jl_SE/docs/proposals/NA_GAS_INFRASTRUCTURE_PROPOSAL_2026-09-12.md.

Usage: python NA_inputs/build_gas_scenario.py [--apply]
"""
import os, sys, json, shutil
import pandas as pd
import openpyxl
sys.stdout.reconfigure(encoding='utf-8')

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, '..'))
if '--repo' in sys.argv:  # build against another checkout (e.g. the v6-freeze worktree)
    REPO = os.path.normpath(sys.argv[sys.argv.index('--repo') + 1])
PAR = os.path.join(REPO, 'Data', 'Parameters')
TAGS = os.path.join(PAR, '00_Sets&Tags')
RES = os.path.join(HERE, 'gas_research')  # research tables always from this checkout
CONV = os.path.join(REPO, 'Conversion Script')
JL_INPUT = r"C:\Users\testbed\Documents\GENeSYSMOD.jl_SE\InputData"
APPLY = '--apply' in sys.argv
SCEN = 'NorthAmerica_gas'
NA = ['California', 'WECC', 'ERCOT', 'SPP', 'MISO', 'SERC', 'PJM', 'NewYork', 'NewEngland', 'Canada']
US = [r for r in NA if r != 'Canada']
YEARS = list(range(2025, 2041))
PJ_PER_BCFD = 399.4          # 1.094 PJ/Bcf x 365
GWTH_PER_BCFD = PJ_PER_BCFD / 31.536
WHO = 'Konstantin Loffler <kl@wip.tu-berlin.de>'
TODAY = '2026-09-15'
DOC = 'see NA_inputs/gas_research + docs/proposals/NA_GAS_INFRASTRUCTURE_PROPOSAL_2026-09-12.md'

written = {}

def base_header(par):
    p = os.path.join(PAR, par, par + '.csv')
    if os.path.exists(p):
        return pd.read_csv(p, dtype=str, keep_default_na=False, nrows=0).columns.tolist()
    return None

def ov(par, rows, cols=None):
    """Write scenario overlay rows for parameter `par` (creates base file if new)."""
    hdr = base_header(par)
    if hdr is None:
        assert cols is not None, f'new parameter {par} needs explicit columns'
        hdr = cols + ['', 'Unit', 'Source', 'Updated at', 'Updated by']
        os.makedirs(os.path.join(PAR, par), exist_ok=True)
        if APPLY:
            with open(os.path.join(PAR, par, par + '.csv'), 'w', encoding='utf-8', newline='') as f:
                f.write(','.join(hdr) + '\n')
    df = pd.DataFrame(rows)
    for c in hdr:
        if c not in df.columns:
            df[c] = ''
    df = df[hdr]
    df['Updated at'] = TODAY
    df['Updated by'] = WHO
    written[par] = len(df)
    if APPLY:
        d = os.path.join(PAR, par, SCEN)
        os.makedirs(d, exist_ok=True)
        df.to_csv(os.path.join(d, par + '.csv'), index=False, header=[('' if h.startswith('Unnamed') else h) for h in hdr], lineterminator='\n')
    return df

def add_base_rows(fname, rows, keycols):
    """Append rows to a 00_Sets&Tags file if the key is absent (new set members/tags)."""
    p = os.path.join(TAGS, fname)
    df = pd.read_csv(p, dtype=str, keep_default_na=False, encoding='utf-8-sig')
    df.columns = [c.strip() for c in df.columns]
    headerless = not all(k in df.columns for k in keycols)
    if headerless:  # e.g. Sets_Fuel.csv: plain member list without a header line
        df = pd.read_csv(p, dtype=str, keep_default_na=False, encoding='utf-8-sig', header=None, names=keycols)
    have = set(map(tuple, df[keycols].values.tolist()))
    new = [r for r in rows if tuple(str(r[k]) for k in keycols) not in have]
    if not new:
        return 0
    add = pd.DataFrame(new)
    for c in df.columns:
        if c not in add.columns:
            add[c] = ''
    out = pd.concat([df, add[df.columns]], ignore_index=True)
    if APPLY:
        out.to_csv(p, index=False, header=(False if headerless else [('' if h.startswith('Unnamed') else h) for h in df.columns]), lineterminator='\n')
    return len(new)

def yrs(v, years=YEARS):
    return {y: v for y in years}

# ---------------------------------------------------------------- research inputs
corr = pd.read_csv(os.path.join(RES, 'gas_corridors_corrected.csv'))
prodres = pd.read_csv(os.path.join(RES, 'gas_production_reserves_2024.csv')).set_index('region')
nonp = pd.read_csv(os.path.join(RES, 'gas_nonpower_demand_2024.csv')).set_index('region')
shape = pd.read_csv(os.path.join(RES, 'gas_nonpower_monthly_shape.csv'), index_col=0)
lng = pd.read_csv(os.path.join(RES, 'lng_export_capacity_path.csv'))
stor = pd.read_csv(os.path.join(RES, 'storage_by_region.csv')).set_index('region')

# ---------------------------------------------------------------- 1. base sets + tags
src_sets = 'NA gas infrastructure feature 2026-09 (NorthAmerica_gas scenario); ' + DOC
n_sets = 0
n_sets += add_base_rows('Sets_Fuel.csv', [{'Fuel': 'Gas_Export'}], ['Fuel'])
n_sets += add_base_rows('Sets_Technology.csv', [{'Technology': 'X_Gas_Export'}, {'Technology': 'Infeasibility_Gas_Natural'}], ['Technology'])
n_sets += add_base_rows('Par_TagTechnologyToSector.csv', [{'Technology': 'X_Gas_Export', 'Sector': 'Transformation', 'Value': '1'}], ['Technology', 'Sector'])
n_sets += add_base_rows('Par_TagTechnologyToSubsets.csv', [{'Technology': 'X_Gas_Export', 'Subset': 'Transformation', 'Value': '1', 'Unit': 'Binary', 'Source': src_sets, 'Updated at': TODAY, 'Updated by': WHO}], ['Technology', 'Subset'])
n_sets += add_base_rows('Par_CapacityToActivityUnit.csv', [{'Technology': 'X_Gas_Export', 'Value': '31.536'}, {'Technology': 'Infeasibility_Gas_Natural', 'Value': '31.536'}], ['Technology'])
n_sets += add_base_rows('Par_TagDemandFuelToSector.csv', [{'Fuel': 'Gas_Export', 'Sector': 'Transformation', 'Value': '1'}, {'Fuel': 'Gas_Natural', 'Sector': 'Industry', 'Value': '1'}], ['Fuel', 'Sector'])
op = os.path.join(PAR, 'Par_OperationalLife', 'Par_OperationalLife.csv')
opdf = pd.read_csv(op, dtype=str, keep_default_na=False)
if 'X_Gas_Export' not in set(opdf.Technology):
    row = {c: '' for c in opdf.columns}; row.update({'Technology': 'X_Gas_Export', 'Value': '30', 'Unit': 'Years', 'Source': 'assumption (export conversion dummy)', 'Updated at': TODAY, 'Updated by': WHO})
    opdf = pd.concat([opdf, pd.DataFrame([row])], ignore_index=True); n_sets += 1
    if APPLY:
        opdf.to_csv(op, index=False, header=[('' if h.startswith('Unnamed') else h) for h in opdf.columns], lineterminator='\n')
print(f'base set/tag rows added: {n_sets}')

# ---------------------------------------------------------------- 2. pipelines
cap = {(r.RF, r.RT): float(r.pj_yr) for r in corr.itertuples()}
rows = []
for a in NA:
    for b in NA:
        if a == b: continue
        v = cap.get((a, b), 0.0)
        rows.append({'Region': a, 'Region.1': b, 'Fuel': 'Gas_Natural', 'Year': 'All', 'Value': f'{v:g}', 'Unit': 'PJ',
                     'Source': ('EIA state-to-state pipeline capacity Jan-2026 (2025), county->ISO mapping, EIA flows_to_remove + transit/feed-line corrections, CA receipt cap; 1.094 PJ/Bcf; ' + DOC) if v > 0 else 'no physical inter-regional pipeline (EIA state-to-state 2025); zero replaces the former dummy value'})
ov('Par_TradeCapacity', rows)

DIST = {('California','WECC'): 1000, ('WECC','SPP'): 1265, ('SPP','ERCOT'): 884, ('ERCOT','MISO'): 457, ('SPP','MISO'): 1136,
        ('PJM','MISO'): 844, ('MISO','SERC'): 541, ('PJM','SERC'): 1440, ('PJM','NewYork'): 664, ('NewYork','NewEngland'): 383,
        ('Canada','WECC'): 1511, ('Canada','SPP'): 1939, ('Canada','MISO'): 641, ('Canada','NewYork'): 898, ('Canada','NewEngland'): 1136}
def dist(a, b):
    return DIST.get((a, b)) or DIST.get((b, a))
rows = []
for (a, b), v in cap.items():
    if v <= 0: continue
    rows.append({'Region': a, 'Region.1': b, 'Fuel': 'Gas_Natural', 'Value': str(dist(a, b)), 'Unit': 'km',
                 'Source': 'hub-to-hub pipeline route length (Dominion South, Henry Hub, Katy/Waha, Chicago Citygate, Opal, SoCal border, Transco Z6, Algonquin, Dawn, AECO); great-circle x1.25 or actual line; ' + DOC})
ov('Par_TradeRoute', rows)

# corridor classes: growth %/yr by year, growth cost MEUR per PJ/yr per km
def cls(a, b):
    s = {a, b}
    if 'Canada' in s: return 'E'
    if s == {'California', 'WECC'}: return 'D'
    if s in ({'ERCOT','MISO'}, {'SPP','ERCOT'}) or (a, b) == ('MISO', 'SERC'): return 'A'
    if (a, b) in (('PJM', 'MISO'), ('PJM', 'SERC')): return 'B'
    if (a, b) in (('PJM', 'NewYork'), ('NewYork', 'NewEngland')): return 'C'
    if s in ({'WECC','SPP'}, {'SPP','MISO'}): return 'F'
    return 'G'
def growth(c, y):
    if c == 'A': return 0.15 if y <= 2030 else 0.08
    if c == 'B': return 0.06
    if c == 'C': return 0.0 if y < 2027 else 0.03
    if c == 'D': return 0.0
    if c == 'E': return 0.01
    if c == 'F': return 0.04
    return 0.05
COST = {'A': 0.006, 'B': 0.012, 'C': 0.025, 'D': 0.007, 'E': 0.007, 'F': 0.007, 'G': 0.012}
def cost(a, b, c):
    s = {a, b}
    if s & {'NewYork', 'NewEngland'}: return 0.025
    if s & {'SERC'} and c != 'A': return 0.011
    return COST[c]
CLS_SRC = 'corridor class %s: EIA pipeline project tracker 1996-2026 + FERC dockets, historic additions and permitting record; ' + DOC
rows_g, rows_c = [], []
for (a, b), v in cap.items():
    if v <= 0: continue
    c = cls(a, b)
    for y in YEARS:
        rows_g.append({'Region': a, 'Region2': b, 'Fuel': 'Gas_Natural', 'Year': str(y), 'Value': f'{growth(c, y):g}', 'Unit': 'Factor', 'Source': CLS_SRC % c})
    rows_c.append({'Region': a, 'Region2': b, 'Fuel': 'Gas_Natural', 'Value': f'{cost(a, b, c):g}', 'Unit': 'M€/PJkm',
                   'Source': 'EIA pipeline project sample (63 projects, cost/length/capacity, 2016-2030 in-service): South Central 0.006, West 0.007, Southeast 0.011, Northeast 0.025, Midwest 0.012 MEUR per PJ/yr per km; ' + DOC})
ov('Par_GrowthRateTradeCapacity', rows_g)
ov('Par_TradeCapacityGrowthCosts', rows_c)

COMM = [('MISO','ERCOT',2026,2.0,'Port Arthur Pipeline / Louisiana Connector (LNG feed, part completed)'),
        ('ERCOT','MISO',2027,4.0,'CP Express Ph1+2 (under construction)'),
        ('ERCOT','MISO',2028,0.467,'NGPL Texas-Louisiana Expansion'),
        ('MISO','SERC',2028,2.1,'Mississippi Crossing MSX (FERC approved)'),
        ('MISO','SERC',2028,1.323,'SNG SSE4 / Elba Express (approved)'),
        ('PJM','SERC',2027,1.6,'Transco Southeast Supply Enhancement (under construction, CP25-10)'),
        ('PJM','SERC',2028,0.55,'MVP Southgate incl. amendment (under construction)'),
        ('PJM','NewYork',2027,0.4,'Transco NESE (permits 2025-11, in-service Nov-2027)'),
        ('PJM','MISO',2027,0.473,'ANR Heartland (approved)'),
        ('NewYork','NewEngland',2028,0.125,'Iroquois ExC (approved)')]
rows = [{'Region': a, 'Region2': b, 'Fuel': 'Gas_Natural', 'Year': str(y), 'Value': f'{bcfd*PJ_PER_BCFD:.1f}', 'Unit': 'PJ',
         'Source': f'{name}; EIA natural gas pipeline projects Aug-2026, {bcfd} Bcf/d; ' + DOC} for a, b, y, bcfd, name in COMM]
ov('Par_CommissionedTradeCapacity', rows)

us_internal = sum(v for (a, b), v in cap.items() if a != 'Canada' and b != 'Canada')
rows = [{'RegionSubset': 'USA', 'Fuel': 'Gas_Natural', 'Year': str(y), 'Value': f'{us_internal + max(0, y-2025)*8*PJ_PER_BCFD:.0f}', 'Unit': 'PJ',
         'Source': 'national inter-regional expansion envelope: 2025 US-internal corridor sum + 8 Bcf/d per year (2017-19 interstate pace); ' + DOC} for y in YEARS]
ov('Par_GroupAnnualMaxTradeCapacity', rows)

# ---------------------------------------------------------------- 3. supply
AEO = {2025: 39.15, 2030: 41.39, 2035: 44.93, 2040: 47.06}   # AEO2026 CB dry production, Tcf
CER = {2025: 18.92, 2030: 22.09, 2035: 24.39, 2040: 26.46}   # CER EF2026 Current Measures, Bcf/d
def interp(d, y):
    ks = sorted(d)
    if y <= ks[0]: return d[ks[0]]
    if y >= ks[-1]: return d[ks[-1]]
    lo = max(k for k in ks if k <= y); hi = min(k for k in ks if k >= y)
    return d[lo] if lo == hi else d[lo] + (d[hi]-d[lo])*(y-lo)/(hi-lo)
EXTRACT = {'PJM': 1.9, 'ERCOT': 1.6, 'SPP': 2.4, 'MISO': 3.3, 'WECC': 2.6, 'Canada': 1.5, 'California': 3.0, 'SERC': 3.0, 'NewYork': 3.0, 'NewEngland': 3.0}
prod24 = {r: float(prodres.loc[r, 'dry_production_pj_2024']) if r in prodres.index else 0.0 for r in NA}
prod24['Canada'] = 18.34 * PJ_PER_BCFD
res24 = {r: float(prodres.loc[r, 'proved_reserves_dry_pj_2024']) if r in prodres.index else 0.0 for r in NA}
res24['Canada'] = 2.5 * 18.34 * PJ_PER_BCFD * 11   # CER: ~10-12 yrs R/P; proxy
r_vc, r_act, r_mpl, r_cap, r_af = [], [], [], [], []
for r in NA:
    for y in YEARS:
        f = (interp(CER, y)/CER[2025]) if r == 'Canada' else (interp(AEO, y)/AEO[2025])
        act = prod24[r] * f
        r_vc.append({'Region': r, 'Technology': 'R_Gas', 'Mode_of_operation': '1', 'Year': str(y), 'Value': f'{EXTRACT[r]:g}', 'Unit': 'MEUR/PJ',
                     'Source': 'basin breakeven (Stanwich 2025 regional breakevens, Dallas Fed, EIA Haynesville evidence; associated gas as oil by-product; WCSB AECO proxy); USD/MMBtu x 0.8766; ' + DOC})
        r_act.append({'Region': r, 'Technology': 'R_Gas', 'Year': str(y), 'Value': f'{act:.1f}', 'Unit': 'PJ',
                      'Source': 'EIA ARR 2024 Table 8 wet production x0.93 dry, state->ISO mapping, scaled with AEO2026 CB US dry production path (CER EF2026 Current Measures for Canada); ' + DOC})
        r_cap.append({'Region': r, 'Technology': 'R_Gas', 'Year': str(y), 'Value': f'{act/31.536/0.9:.3f}', 'Unit': 'GW',
                      'Source': 'peak production capability = annual max activity / 0.9; ' + DOC})
    r_mpl.append({'Region': r, 'Technology': 'R_Gas', 'Value': f'{2*res24[r]:.0f}', 'Unit': 'PJ',
                  'Source': 'proved reserves (EIA ARR 2024 T8, dry-equivalent) x 2 for reserve growth over the horizon; ' + DOC})
    r_af.append({'Region': r, 'Technology': 'R_Gas', 'Year': 'All', 'Value': '1', 'Unit': 'Fraction', 'Source': 'by definition'})
    r_af.append({'Region': r, 'Technology': 'Z_Import_Gas', 'Year': 'All', 'Value': '1', 'Unit': 'Fraction', 'Source': 'by definition'})
    r_af.append({'Region': r, 'Technology': 'X_Gas_Export', 'Year': 'All', 'Value': '1', 'Unit': 'Fraction', 'Source': 'by definition'})
ov('Par_VariableCost', r_vc)
ov('Par_TotalAnnualMaxActivity', r_act)
ov('Par_ModelPeriodActivityMaxLimit', r_mpl)
# Z_Import_Gas physical only: LNG import (Everett, New England ~0.1 Bcf/d), Mexico->US border (rarely used)
zimp = {'NewEngland': 1.27, 'ERCOT': 1.0, 'California': 1.0}
xexp_cap = []
lngp = {(r.region, int(r.year)): float(r.lng_capacity_bcfd) for r in lng.itertuples()}
MEX = {'ERCOT': 4.55, 'WECC': 1.30, 'California': 0.65}
export_pj = {}
for r in NA:
    r_cap.append({'Region': r, 'Technology': 'Z_Import_Gas', 'Year': 'All', 'Value': f'{zimp.get(r, 0.001):g}', 'Unit': 'GW',
                  'Source': 'physical import capability only (user decision 2026-09-15): LNG import terminal (Everett/Northeast Gateway ~0.1 Bcf/d) and Mexico->US border capacity; price formation left to the R_Gas supply curve; ' + DOC})
    r_cap.append({'Region': r, 'Technology': 'X_Gas_Export', 'Year': 'All', 'Value': '999999', 'Unit': 'GW', 'Source': 'export conversion dummy, unconstrained'})
    for y in YEARS:
        pj = (lngp.get((r, y), 0.0)*0.9 + MEX.get(r, 0.0)) * PJ_PER_BCFD
        export_pj[(r, y)] = pj
        if pj > 0:
            xexp_cap.append({'Region': r, 'Technology': 'X_Gas_Export', 'Year': str(y), 'Value': f'{pj/31.536/0.9:.3f}', 'Unit': 'GW',
                             'Source': 'export throughput capacity = export demand / 0.9 (LNG liquefaction EIA Q2-2026 existing+UC at 90 % utilisation + Mexico pipeline exports ~6.5 Bcf/d 2024 split ERCOT 70/WECC 20/CA 10 %); ' + DOC})
ov('Par_TotalAnnualMaxCapacity', r_cap)
ov('Par_AvailabilityFactor', r_af)

# ---------------------------------------------------------------- 4. demand
AEO_NONPOWER_2040 = 1.054   # AEO2026 reference: res/com -4 %, industrial +12 % by 2040, blended 41/59 -> +5.4 % (proxy, table not fetched)
d_rows = []
CA_NONPOWER = 3800.0
for r in NA:
    base = CA_NONPOWER if r == 'Canada' else float(nonp.loc[r, 'nonpower_pj_2024'])
    for y in YEARS:
        f = 1 + (AEO_NONPOWER_2040 - 1) * (y - 2025) / 15
        d_rows.append({'Region': r, 'Fuel': 'Gas_Natural', 'Year': str(y), 'Value': f'{base*f:.1f}', 'Unit': 'PJ',
                       'Source': ('EIA 2024 state consumption by end use (total minus electric power), state->ISO mapping, x AEO2026 blended non-power trajectory (+5.4 % by 2040: res/com -4 %, industrial +12 %, 41/59 weights - proxy); ' if r != 'Canada' else 'Canada non-power gas demand proxy 3,800 PJ (CER: ~12 Bcf/d winter / ~7 summer domestic demand, ~20 % power); same AEO-type trajectory; ') + DOC})
        if export_pj[(r, y)] > 0:
            d_rows.append({'Region': r, 'Fuel': 'Gas_Export', 'Year': str(y), 'Value': f'{export_pj[(r, y)]:.1f}', 'Unit': 'PJ',
                           'Source': 'LNG export feedgas (EIA liquefaction Q2-2026 existing + under construction, 90 % utilisation, terminals mapped LA->MISO, TX->ERCOT, MD->PJM, GA->SERC) + Mexico pipeline exports; ' + DOC})
ov('Par_SpecifiedAnnualDemand', d_rows)
# conversion tech rows (World, inherited)
ov('Par_OutputActivityRatio', [{'Region': 'World', 'Technology': 'X_Gas_Export', 'Fuel': 'Gas_Export', 'Mode_of_operation': '1', 'Year': 'All', 'Value': '1', 'Unit': 'Ratio', 'Source': 'export conversion dummy'}])
ov('Par_InputActivityRatio', [{'Region': 'World', 'Technology': 'X_Gas_Export', 'Fuel': 'Gas_Natural', 'Mode_of_operation': '1', 'Year': 'All', 'Value': '1', 'Unit': 'Ratio', 'Source': 'export conversion dummy'}])
ov('Par_ResidualCapacity', xexp_cap + [
    {'Region': r, 'Technology': 'D_Gas_Methane', 'Year': str(y), 'Value': f'{(float(stor.loc[r, "working_PJ"]) if r in stor.index else (1038.0 if r == "Canada" else 0.0))*277.78/800:.2f}', 'Unit': 'GW',
     'Source': 'storage withdrawal/injection power = working gas / 800 h (NA E2P, see Par_StorageE2PRatio overlay); EIA-191 2024 by region, CER 2018 for Canada; ' + DOC}
    for r in NA for y in YEARS])
ov('Par_ResidualStorageCapacity', [
    {'Region': r, 'Storage': 'S_Gas_Methane', 'Year': str(y), 'Value': f'{(float(stor.loc[r, "working_PJ"]) if r in stor.index else (1038.0 if r == "Canada" else 0.0)):.1f}', 'Unit': 'PJ',
     'Source': 'underground working gas capacity, EIA-191 2024 field data mapped to ISO regions (Canada: CER 949 Bcf); ' + DOC}
    for r in NA for y in YEARS])
ov('Par_StorageE2PRatio', [{'Storage': 'S_Gas_Methane', 'Year': 'All', 'Value': '800', 'Unit': 'GWh/GW',
    'Source': 'NA underground storage: working gas / peak deliverability ~ 33 days (EIA-191 2024: 4.9 EJ / 118 Bcf/d); scenario override of the EU 167 h; ' + DOC}])
ov('Par_CapitalCost', [{'Region': r, 'Technology': 'D_Gas_Methane', 'Year': str(y), 'Value': '1', 'Unit': 'MEUR/GW', 'Source': 'World value copied to every modelled year (milestone-only World rows leave off-years at 0)'} for r in NA for y in YEARS])
# FixedCost: the base World series is milestone-only (2025/2030/2035/2040); create_daa
# leaves the gap years at 0 (errorcheck CostYearGap, 120 offenders in the first 49 run),
# so the fixed cost of the storage-deliverability fleet appeared only every fifth year.
# Interpolate the World milestones linearly onto every modelled year per NA region.
_fc = pd.read_csv(os.path.join(PAR, 'Par_FixedCost', 'Par_FixedCost.csv'), dtype=str, keep_default_na=False)
_fc = _fc[(_fc.Region == 'World') & (_fc.Technology == 'D_Gas_Methane') & (_fc.Year.str.isdigit())]
_fc_pts = sorted((int(y), float(v)) for y, v in zip(_fc.Year, _fc.Value) if v != '')
def _fc_interp(y):
    ys, vs = [a for a, _ in _fc_pts], [b for _, b in _fc_pts]
    if y <= ys[0]: return vs[0]
    if y >= ys[-1]: return vs[-1]
    import bisect as _b
    i = _b.bisect_right(ys, y); y0, y1, v0, v1 = ys[i-1], ys[i], vs[i-1], vs[i]
    return v0 + (v1 - v0) * (y - y0) / (y1 - y0)
ov('Par_FixedCost', [{'Region': r, 'Technology': 'D_Gas_Methane', 'Year': str(y), 'Value': f'{_fc_interp(y):.3f}', 'Unit': 'MEUR/GW',
    'Source': 'World milestone series (base Par_FixedCost) interpolated linearly to every modelled year; ' + DOC} for r in NA for y in YEARS])

# ---------------------------------------------------------------- 5. deliverability (CA6)
SUPPLY_BCFD = {'NewEngland': 5.9, 'California': 7.1, 'NewYork': 14.4 + 2.85}
DAYS = {'01':31,'02':28,'03':31,'04':30,'05':31,'06':30,'07':31,'08':31,'09':30,'10':31,'11':30,'12':31}
lim_rows, mon_rows = [], []
for r, sup in SUPPLY_BCFD.items():
    base_np = float(nonp.loc[r, 'nonpower_pj_2024'])
    caps = {}
    for m, d in DAYS.items():
        np_gw = base_np * float(shape.loc[m if m in shape.index else int(m), r]) / d / 0.0864   # PJ/day -> GW-th (1 PJ/d = 11.574 GW)
        caps[m] = max(0.0, sup * GWTH_PER_BCFD - np_gw)
    lim = max(caps.values())
    for y in YEARS:
        lim_rows.append({'Region': r, 'Fuel': 'Gas_Natural', 'Year': str(y), 'Value': f'{lim:.1f}', 'Unit': 'GW',
                         'Source': f'peak-day gas deliverable to consuming technologies = supply capability {sup} Bcf/d (ISO-NE OFSA pipeline+LNG; SoCalGas 3.89 + PG&E ~3.2 receipt; NY inbound pipelines + storage withdrawal) minus non-power demand of the least-constrained month; monthly factors in Par_FuelUseRateLimitMonth; ' + DOC})
    for m in DAYS:
        mon_rows.append({'Region': r, 'Fuel': 'Gas_Natural', 'Month': str(int(m)), 'Value': f'{caps[m]/lim:.4f}', 'Unit': 'Fraction',
                         'Source': 'monthly share = (supply capability - non-power demand of the month) / annual limit; EIA 2024 monthly consumption shape; ' + DOC})
ov('Par_FuelUseRateLimit', lim_rows, cols=['Region', 'Fuel', 'Year', 'Value'])
ov('Par_FuelUseRateLimitMonth', mon_rows, cols=['Region', 'Fuel', 'Month', 'Value'])

# ---------------------------------------------------------------- 6. fuel -> timeseries tags
ov('Par_TagFuelToTimeseries', [
    {'Fuel': 'Gas_Natural', 'Profile': 'GAS_NONPOWER', 'Value': '1', 'Unit': 'Tag', 'Source': 'non-power gas demand profile (TS_GAS_NONPOWER: 41 % heating-shaped, 59 % flat)'},
    {'Fuel': 'Gas_Export', 'Profile': 'POWER_DATACENTER', 'Value': '1', 'Unit': 'Tag', 'Source': 'flat profile (reuses the flat dummy datacenter TS)'}],
   cols=['Fuel', 'Profile', 'Value'])

# ---------------------------------------------------------------- 7. TS_GAS_NONPOWER hourly profile
# EIA 2024 monthly non-power consumption shape per region (TS_HEAT_LOW carries only
# zero placeholders for the NA columns), flat within each month, mean = 1.
# Canada: MISO (northern US) shape as proxy.
DAYS_M = [31,28,31,30,31,30,31,31,30,31,30,31]
hour_month = []
for m, d in enumerate(DAYS_M):
    hour_month += [m] * (d*24)
prof = pd.DataFrame({'HOUR': list(range(1, 8761))})
for r in NA:
    rs = 'MISO' if r == 'Canada' else r
    sh = [float(shape.loc[m if m in shape.index else int(m), rs]) for m in ['01','02','03','04','05','06','07','08','09','10','11','12']]
    w = [sh[m] * 8760 / (DAYS_M[m]*24) for m in range(12)]      # share_m / hours_m x 8760 -> mean 1
    prof[r] = [w[hour_month[i]] for i in range(8760)]
if APPLY:
    d = os.path.join(REPO, 'Data', 'Timeseries', 'TS_GAS_NONPOWER'); os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, 'TS_GAS_NONPOWER.csv'), 'w', encoding='utf-8', newline='') as f:
        f.write(f'Source: non-power gas demand shape = EIA 2024 monthly consumption (total minus electric power) by state mapped to ISO regions, flat within month, mean 1; Canada = MISO shape proxy; {TODAY}; {WHO}' + ',' * len(NA) + '\n')
        prof.to_csv(f, index=False, lineterminator='\n')
    src = os.path.join(JL_INPUT, 'Timeseries_NorthAmerica_2015.xlsx'); dst = os.path.join(JL_INPUT, 'Timeseries_NorthAmerica_gas_2015.xlsx')
    shutil.copy(src, dst)
    wb = openpyxl.load_workbook(dst)
    ref = wb['TS_POWER_DATACENTER']; hdr = [c.value for c in ref[1]]
    ws = wb.create_sheet('TS_GAS_NONPOWER'); ws.append(hdr)
    for i in range(8760):
        ws.append([int(prof.HOUR.iloc[i]) if h == 'HOUR' else (float(prof[h].iloc[i]) if h in prof.columns else None) for h in hdr])
    wb.save(dst)
    print('TS_GAS_NONPOWER written + injected into', os.path.basename(dst))

# ---------------------------------------------------------------- 8. filter file
if APPLY:
    src = os.path.join(CONV, 'Set_filter_file_NorthAmerica.xlsx'); dst = os.path.join(CONV, 'Set_filter_file_NorthAmerica_gas.xlsx')
    shutil.copy(src, dst)
    wb = openpyxl.load_workbook(dst)
    def flip(sheet, names, add_missing=True):
        ws = wb[sheet]; seen = set()
        for row in ws.iter_rows(min_row=2):
            if row[0].value in names:
                row[1].value = 1; seen.add(row[0].value)
        for n in names:
            if n not in seen and add_missing:
                ws.append([n, 1])
    flip('Fuel_selection', ['Gas_Natural', 'Gas_Export'])
    flip('Technology_selection', ['R_Gas', 'Z_Import_Gas', 'D_Gas_Methane', 'X_Gas_Export', 'Infeasibility_Gas_Natural'])
    flip('Storage_selection', ['S_Gas_Methane'])
    wb.save(dst)
    print('filter file written:', os.path.basename(dst))

# ---------------------------------------------------------------- 9. Assumptions
NOTE = f"""
NorthAmerica_gas scenario ({TODAY}) - explicit natural gas infrastructure in the NA
power model. All numbers derived from EIA/CER primary data in NA_inputs/gas_research/
by NA_inputs/build_gas_scenario.py; design and sources documented in
GENeSYSMOD.jl_SE/docs/proposals/NA_GAS_INFRASTRUCTURE_PROPOSAL_2026-09-12.md.
Units: 1 Bcf = 1.094 PJ (1,037 Btu/cf); 1 Bcf/d = 399.4 PJ/yr = 12.66 GW-th; EUR2023 at 1.0813 USD/EUR.
Decisions (user, 2026-09-15): Z_Import_Gas physical-only; deliverability cap
(Par_FuelUseRateLimit) active for NewEngland/California/NewYork; non-power demand
follows an AEO2026-type blended trajectory (+5.4 % by 2040, proxy); v6-freeze basis.
"""
if APPLY:
    for par in ['Par_TradeCapacity', 'Par_TradeRoute', 'Par_GrowthRateTradeCapacity', 'Par_TradeCapacityGrowthCosts', 'Par_CommissionedTradeCapacity',
                'Par_SpecifiedAnnualDemand', 'Par_VariableCost', 'Par_TotalAnnualMaxActivity', 'Par_ResidualStorageCapacity', 'Par_FuelUseRateLimit', 'Par_TagFuelToTimeseries']:
        ap = os.path.join(PAR, par, 'Assumptions.txt')
        if not (os.path.exists(ap) and NOTE.strip()[:60] in open(ap, encoding='utf-8').read()):
            with open(ap, 'a', encoding='utf-8') as f:
                f.write(NOTE)
print('\noverlay rows per parameter:'); [print(f'  {k:34s} {v:5d}') for k, v in written.items()]
print('APPLIED' if APPLY else 'DRY RUN (use --apply)')
