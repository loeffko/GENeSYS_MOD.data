# -*- coding: utf-8 -*-
"""Build the data overlays for the Canada scenario set (Siemens Energy Canada request, nine scenarios).

Plan: GENeSYSMOD.jl_SE/docs/proposals/CA_scenario_plan_2026-10-04.xlsx (sheets Assumptions, Run plan).
Every run is a data-scenario subfolder NorthAmerica_cNN<variant>_<name> under Par_X/ (row-upsert overlay on the
v6 base CSVs). Only Canada rows are written; the US side stays identical to the frozen base v6f.
The helpers come from build_14_scenarios.py (same folder). No base file is touched: the set members used here
(fuel Power_LargeLoads with its flat profile, technology subset Onshore, region subset Canada) already exist.

Priority-1 set (one central run per scenario; scenario 5 is a side calculation without a run):
  c01a gridmix        gas fleet kept, SMR and battery paths of CER Current Measures as minima
  c02a localcontent   capital-cost premium on import-dependent technologies from 2028
  c03b nuclear_se     Siemens Energy nuclear outlook (Canada rows of the nuclear_announced overlay)
  c04a partnership    blended financing effect as a capital-cost factor, capacity paths earlier
  c06b dcpipeline     data-centre demand: named project pipeline (below the base)
  c07a windpaced      onshore wind ceiling = announced procurement, capital cost with headwinds
  c07b windaccel      onshore wind floor = CanREA / Dunsky Accelerated, lower capital cost
  c08b minerals       flat load of mines, smelters and processing (utility planning view)
  c09a euprojects     export hydrogen and industry load of a Canada-EU partnership

Usage:  python NA_inputs/build_canada_scenarios.py [--apply] [--repo <path>] [--only c01a,c07b]
        (dry run prints the row counts; runs are v6-based, so build with --repo C:/v6wt and copy the overlay
         folders to the HEAD checkout - HEAD base values differ from the v6 freeze)
"""
import os, sys, shutil
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_14_scenarios as B          # reads --repo / --apply from sys.argv on import

B.TODAY = '2026-10-05'
B.PLAN = 'CA_scenario_plan_2026-10-04.xlsx (Canada set, priority 1)'
ONLY = sys.argv[sys.argv.index('--only') + 1].split(',') if '--only' in sys.argv else None
CA = 'Canada'
YEARS = B.YEARS
fmt, num, interp = B.fmt, B.num, B.interp

WIND_ON = ['P_Wind_Onshore_Avg', 'P_Wind_Onshore_Opt', 'P_Wind_Onshore_Inf']
WIND_OFF = ['P_Wind_Offshore_Shallow', 'P_Wind_Offshore_Transitional', 'P_Wind_Offshore_Deep']
PV_UTIL = ['P_PV_Utility_Avg', 'P_PV_Utility_Opt', 'P_PV_Utility_Inf', 'P_PV_Utility_Tracking']
HYDRO = ['P_Hydro_Reservoir', 'P_Hydro_RoR']
NUCLEAR = ['P_Nuclear', 'P_Nuclear_SMR']


# ---------------------------------------------------------------- helpers
def series(par, tech, region=CA):
    """{year: value} of the base rows of one technology (numeric years only)."""
    df = B.read_base(par)
    df = df[(df.Region == region) & (df.Technology == tech)]
    return {int(r.Year): num(r.Value) for r in df.itertuples(index=False) if r.Year.isdigit() and num(r.Value) is not None}


def cap_rows(tech, vals):
    return [{'Region': CA, 'Technology': tech, 'Year': str(y), 'Value': fmt(v, 4), 'Unit': 'GW'} for y, v in sorted(vals.items())]


def ca_capex(S, techs, mult, source, storage=False):
    """Canada rows = World rows x mult(year), for every year the World rows carry (no year may fall back to a gap).
    The base stores capital cost under World only; Canada-specific rows override it for the Canada node."""
    par, col = ('Par_CapitalCostStorage', 'Storage') if storage else ('Par_CapitalCost', 'Technology')
    df = B.read_base(par)
    df = df[(df.Region == 'World') & df[col].isin(techs)]
    rows = {}
    for r in df.to_dict('records'):
        if not r['Year'].isdigit() or num(r['Value']) is None:
            continue
        y = int(r['Year'])
        rows[(r[col], y)] = {'Region': CA, col: r[col], 'Year': str(y), 'Value': fmt(num(r['Value']) * mult(y), 4),
                             'Unit': 'MEUR/PJ' if storage else 'MEUR/GW'}
    assert rows, f'no World capital-cost rows for {techs}'
    B.ov(S, par, list(rows.values()), source)


def from_year(factor, start):
    return lambda y: factor if y >= start else 1.0


def crf(r, n):
    return r * (1 + r) ** n / ((1 + r) ** n - 1)


def life(tech):
    df = B.read_base('Par_OperationalLife')
    v = [num(r.Value) for r in df.itertuples(index=False) if r.Technology == tech and num(r.Value) is not None]
    assert v, f'no operational life for {tech}'
    return v[0]


def large_load_profile(S):
    B.ov(S, 'Par_TagFuelToTimeseries', [{'Fuel': 'Power_LargeLoads', 'Profile': 'POWER_DATACENTER', 'Value': '1', 'Unit': 'Binary'}], 'flat profile for large loads')


def clean(scen):
    """Remove the overlay folders of a scenario before rebuilding (the upsert keeps rows a changed definition no longer writes)."""
    if not B.APPLY:
        return
    for par in os.listdir(B.PAR):
        d = os.path.join(B.PAR, par, scen)
        if scen.startswith('NorthAmerica_c') and os.path.isdir(d):
            shutil.rmtree(d)


# ---------------------------------------------------------------- scenario blocks
def c01a_gridmix():
    S = 'NorthAmerica_c01a_gridmix'
    # gas fleet kept at the CER Current Measures level (natural gas incl. CCUS); the model sits on the minima of the
    # other gas classes, so the gap is closed with new CCGT, never above the corridor ceiling of the year
    target = {2025: 32.4, 2030: 34.2, 2035: 33.4, 2040: 36.6}
    res_cc = series('Par_ResidualCapacity', 'P_Gas_CCGT_Residual')
    others = {t: series('Par_TotalAnnualMinCapacity', t) for t in ('P_Gas_OCGT', 'P_Gas_Steam', 'P_Gas_Engines')}
    mn, mx = series('Par_TotalAnnualMinCapacity', 'P_Gas_CCGT'), series('Par_TotalAnnualMaxCapacity', 'P_Gas_CCGT')
    new, clamped = {}, []
    for y in YEARS:
        if y < 2026:
            continue
        need = interp(target, y) - res_cc.get(y, 0.0) - sum(o.get(y, 0.0) for o in others.values())
        v = max(mn.get(y, 0.0), need)
        if v > mx[y] * 0.999:
            clamped.append(y); v = mx[y] * 0.999      # just under the ceiling (a rounded minimum must not exceed the maximum)
        if v > mn.get(y, 0.0) + 1e-6:
            new[y] = v
    print('   c01a new-CCGT minimum (GW):', {y: round(v, 2) for y, v in new.items() if y in (2026, 2028, 2030, 2035, 2040)}, '| held at the corridor ceiling in', clamped)
    B.ov(S, 'Par_TotalAnnualMinCapacity', cap_rows('P_Gas_CCGT', new),
         'C1A grid mix: total gas fleet kept at the CER EF2026 Current Measures path 34.2 / 33.4 / 36.6 GW (2030 / 2035 / 2040) - new-CCGT minimum = path minus residual CCGT and the OCGT / steam / engine minima, capped at the base corridor ceiling of the year')
    # SMR: CER Current Measures 0.3 / 1.5 / 2.1 GW, minimum = maximum (as in the base)
    smr = {2029: 0.0, 2030: 0.3, 2035: 1.5, 2040: 2.1}
    smn, smx = series('Par_TotalAnnualMinCapacity', 'P_Nuclear_SMR'), series('Par_TotalAnnualMaxCapacity', 'P_Nuclear_SMR')
    path = {y: max(smn.get(y, 0.0), interp(smr, y)) for y in YEARS if y >= 2030}
    src = 'C1A grid mix: SMR path of CER EF2026 Current Measures 0.3 / 1.5 / 2.1 GW (2030 / 2035 / 2040), minimum = maximum'
    B.ov(S, 'Par_TotalAnnualMinCapacity', cap_rows('P_Nuclear_SMR', path), src)
    B.ov(S, 'Par_TotalAnnualMaxCapacity', cap_rows('P_Nuclear_SMR', {y: max(v, smx.get(y, 0.0) if smx.get(y, 0.0) > 0.0011 else 0.0) for y, v in path.items()}), src)
    # battery storage: CER Current Measures 4.5 / 6.5 / 10.5 GW (the base floor is this path minus 20 %)
    bmn, bmx = series('Par_TotalAnnualMinCapacity', 'D_Battery_Li-Ion'), series('Par_TotalAnnualMaxCapacity', 'D_Battery_Li-Ion')
    bat = {2025: bmn[2025], 2030: 4.5, 2035: 6.5, 2040: 10.5}
    rows = {y: interp(bat, y) for y in YEARS if y >= 2026 and interp(bat, y) > bmn.get(y, 0.0) + 1e-6}
    assert all(v <= bmx[y] for y, v in rows.items()), 'battery minimum above the corridor ceiling'
    B.ov(S, 'Par_TotalAnnualMinCapacity', cap_rows('D_Battery_Li-Ion', rows), 'C1A grid mix: battery storage path of CER EF2026 Current Measures 4.5 / 6.5 / 10.5 GW (2030 / 2035 / 2040) as minimum')


def c02a_localcontent():
    S = 'NorthAmerica_c02a_localcontent'
    src = 'C2A local content as scored preference, capital cost from 2028: '
    ca_capex(S, WIND_ON, from_year(1.08, 2028), src + 'onshore wind x1.08 (US Buy American +5.6 %, India solar local-content +6 %, plus the 25 % tower surtax on 10-15 % of capex)')
    ca_capex(S, PV_UTIL, from_year(1.06, 2028), src + 'utility PV x1.06 (Probst et al. 2020; Peterson Institute 2020)')
    ca_capex(S, ['D_Battery_Li-Ion'], from_year(1.06, 2028), src + 'batteries x1.06 (power component)')
    ca_capex(S, ['S_Battery_Li-Ion'], from_year(1.06, 2028), src + 'batteries x1.06 (energy component)', storage=True)
    ca_capex(S, ['P_Gas_CCGT'], from_year(1.05, 2028), src + 'CCGT x1.05 (generic premium; SE lead-time and price data not yet supplied)')


def c03b_nuclear_se():
    S = 'NorthAmerica_c03b_nuclear_se'
    for par in ('Par_TotalAnnualMinCapacity', 'Par_TotalAnnualMaxCapacity'):
        p = B.sub_path(par, 'NorthAmerica_nuclear_announced')
        assert p, f'nuclear_announced overlay missing for {par}'
        df = pd.read_csv(p, dtype=str, keep_default_na=False, encoding='utf-8-sig')
        df.columns = [c.strip() for c in df.columns]
        df = df[df.Region == CA]
        B.ov(S, par, df.to_dict('records'), 'C3B nuclear growth, Siemens Energy outlook: Canadian Nuclear Review 5.7.2026 (large units 11.5 / 15.6 / 17.9 / 23.4 GW in 2030 / 2035 / 2038 / 2040, SMR 0.6 / 1.8 / 3.0 / 4.2 GW); Canada rows reused from NorthAmerica_nuclear_announced')
    # the announced minimum must fit under the base ceiling of large nuclear
    mx = series('Par_TotalAnnualMaxCapacity', 'P_Nuclear')
    mn = {int(r['Year']): num(r['Value']) for r in pd.read_csv(B.sub_path('Par_TotalAnnualMinCapacity', 'NorthAmerica_nuclear_announced'), dtype=str, keep_default_na=False, encoding='utf-8-sig').rename(columns=str.strip).to_dict('records')
          if r['Region'] == CA and r['Technology'] == 'P_Nuclear' and r['Year'].isdigit()}
    over = {y: (v, mx[y]) for y, v in mn.items() if v > mx[y]}
    assert not over, f'announced nuclear minimum above the base ceiling: {over}'


def c04a_partnership():
    S = 'NorthAmerica_c04a_partnership'
    # financing effect: blended project WACC 4.83 % instead of 5 % (loan guarantees on the Indigenous equity slice,
    # 70 % of new capacity partnered), converted with the annuity ratio over the technology lifetime of the data
    wacc, ref = 0.0483, 0.05
    for techs, name in ((WIND_ON + WIND_OFF, 'wind'), (PV_UTIL, 'utility PV'), (HYDRO, 'hydro'), (NUCLEAR, 'nuclear')):
        n = life(techs[0])
        m = round(crf(wacc, n) / crf(ref, n), 3)
        print(f'   c04a capital-cost factor {name}: {m} (lifetime {n:.0f} yr)')
        ca_capex(S, techs, from_year(m, 2026), f'C4A Indigenous partnership as the norm: blended WACC 4.83 % vs 5 % as capital-cost factor x{m} for {name} (annuity ratio over {n:.0f} years; RBC 2026, FNMPC)')
    # earlier availability: wind / PV ceiling one year earlier, hydro and nuclear paths two years earlier
    src1 = 'C4A: corridor ceiling one year earlier for partnered wind and PV (British Columbia assessment exemption saves 1-2 years)'
    for t in WIND_ON + PV_UTIL:
        mx = series('Par_TotalAnnualMaxCapacity', t)
        if not mx:
            continue
        rows = {y: mx[min(y + 1, 2040)] for y in YEARS if 2026 <= y and mx.get(min(y + 1, 2040)) is not None and abs(mx[min(y + 1, 2040)] - mx.get(y, 0.0)) > 1e-9}
        B.ov(S, 'Par_TotalAnnualMaxCapacity', cap_rows(t, rows), src1)
    src2 = 'C4A: hydro and nuclear paths two years earlier (federal review cut from more than five years to a two-year maximum for national-interest projects)'
    for t in HYDRO + NUCLEAR:
        for par in ('Par_TotalAnnualMinCapacity', 'Par_TotalAnnualMaxCapacity'):
            b = series(par, t)
            rows = {y: b[min(y + 2, 2040)] for y in YEARS if 2026 <= y and b.get(min(y + 2, 2040)) is not None and abs(b[min(y + 2, 2040)] - b.get(y, 0.0)) > 1e-9}
            B.ov(S, par, cap_rows(t, rows), src2)


def c06b_dcpipeline():
    S = 'NorthAmerica_c06b_dcpipeline'
    dc = {2025: B.dem('Power_DataCenter', CA, 2025) / B.TWH, 2030: 47, 2035: 121, 2040: 177}
    B.demand_rows(S, 'Power_DataCenter', {CA: {y: interp(dc, y) * B.TWH for y in YEARS if y >= 2026}},
                  'C6B data centres, named pipeline builds out: 47 / 121 / 177 TWh (2030 / 2035 / 2040) - AESO dated loads and Phase I, Meta, Keephills, Genesee, Beacon, Malachite, Wonder Valley phase 1, Bell Saskatchewan, IESO high forecast, Hydro-Quebec and BC Hydro allocations; load factor 0.85. FLAG: below the FEL base (71 / 178 / 269 TWh) - scenario numbers used as instructed. Dedicated gas 2.8 / 9.9 / 13.5 GW is inside the new CCGT the base forces (unchanged)')


def c07a_windpaced():
    S = 'NorthAmerica_c07a_windpaced'
    res25 = series('Par_ResidualCapacity', 'P_Wind_Onshore_Avg')[2025]
    cap = {2025: res25, 2030: 28.0, 2035: 43.5, 2040: 55.7}
    caps = {y: interp(cap, y) for y in YEARS if y >= 2026}
    B.ov(S, 'Par_GroupTotalAnnualMaxCapacity', B.group_cap_rows('Onshore', 'Canada', caps),
         'C7A wind procurement-paced: onshore wind ceiling = announced procurement 28.0 / 43.5 / 55.7 GW (2030 / 2035 / 2040; Hydro-Quebec +10 GW by 2035, BC Hydro calls 2024 and 2025, IESO LT2, CER Current Measures for Alberta and Saskatchewan, Newfoundland wind-hydrogen fleet removed), all onshore classes together')
    mn = series('Par_TotalAnnualMinCapacity', 'P_Wind_Onshore_Avg')
    low = {y: caps[y] for y in caps if mn.get(y, 0.0) > caps[y]}
    print('   c07a wind minimum lowered to the ceiling in', sorted(low))
    B.ov(S, 'Par_TotalAnnualMinCapacity', cap_rows('P_Wind_Onshore_Avg', low), 'C7A: corridor minimum lowered to the announced path where the base minimum (CER Current Measures -20 %, incl. 11 GW of cancelled Newfoundland wind-hydrogen capacity) is above it')
    ca_capex(S, WIND_ON, from_year(1.13, 2026), 'C7A headwinds: onshore wind capital cost x1.13 (cold-climate package +10 % of turbine cost = +7 % of total; 25 % tower surtax on a 10-30 % tower share = +2.5 to +7.5 %)')


def c07b_windaccel():
    S = 'NorthAmerica_c07b_windaccel'
    mn, mx = series('Par_TotalAnnualMinCapacity', 'P_Wind_Onshore_Avg'), series('Par_TotalAnnualMaxCapacity', 'P_Wind_Onshore_Avg')
    # floor: base corridor to 2027 (projects under construction are known), then linear to 45 / 70 / 87 GW
    path = {2027: mn[2027], 2030: 45.0, 2035: 70.0, 2040: 87.0}
    floor = {y: max(mn.get(y, 0.0), interp(path, y)) for y in YEARS if y >= 2028}
    B.ov(S, 'Par_TotalAnnualMinCapacity', cap_rows('P_Wind_Onshore_Avg', floor),
         'C7B wind accelerated: onshore wind floor 45 / 70 / 87 GW (2030 / 2035 / 2040) = CanREA / Dunsky Market Outlook 2025, Accelerated scenario (2040 interpolated to 122 GW in 2050); base corridor kept to 2027')
    lift = {y: v * 1.02 for y, v in floor.items() if v * 1.02 > mx[y]}
    print('   c07b wind ceiling lifted in', sorted(lift))
    B.ov(S, 'Par_TotalAnnualMaxCapacity', cap_rows('P_Wind_Onshore_Avg', lift), 'C7B: corridor ceiling lifted to the accelerated floor (+2 %) where the base ceiling is below it')
    f = {2025: 1.0, 2030: 0.948, 2035: 0.93, 2040: 0.91}
    ca_capex(S, WIND_ON, lambda y: interp(f, y) if y >= 2026 else 1.0, 'C7B: onshore wind capital cost x0.948 / 0.93 / 0.91 (2030 / 2035 / 2040) = Accelerated vs Reference cost trend of the CanREA / Dunsky outlook, interpolated')


def c08b_minerals():
    S = 'NorthAmerica_c08b_minerals'
    B.flat_adder(S, 'Power_LargeLoads', {CA: {2025: 0, 2030: 7.5, 2035: 19.7, 2040: 21.7}},
                 'C8B critical minerals, advanced projects and utility planning view: +7.5 / +19.7 / +21.7 TWh (2030 / 2035 / 2040) flat load - Jansen potash, Highland Valley, Marathon, Red Chris, Crawford, Kami, Thunder Bay lithium; Quebec from the Hydro-Quebec supply-plan filing 2025 read one year late; load factors 0.85 mines / 0.90 processing')
    large_load_profile(S)


def c09a_euprojects():
    S = 'NorthAmerica_c09a_euprojects'
    B.flat_adder(S, 'Power_Hydrogen', {CA: {2025: 0, 2030: 4, 2035: 26, 2040: 36}},
                 'C9A Canada-EU partnership, surviving export projects: export electrolysis +4 / +26 / +36 TWh (2030 / 2035 / 2040) on top of the base (H2Global window, EverWind Point Tupper, EVREC, North Atlantic, Bear Head; 10 TWh per Mt ammonia)')
    B.flat_adder(S, 'Power_LargeLoads', {CA: {2025: 0, 2030: 8, 2035: 19, 2040: 29}},
                 'C9A Canada-EU partnership: industry load +8 / +19 / +29 TWh (2030 / 2035 / 2040) flat = CER EF2026 Higher minus Current Measures industrial electricity (proxy for manufacturing and minerals processing)')
    large_load_profile(S)


LARGE = dict(fuels=['Power_LargeLoads'], modes=[7])
CSCEN = {
    'c01a': ('NorthAmerica_c01a_gridmix', c01a_gridmix, None),
    'c02a': ('NorthAmerica_c02a_localcontent', c02a_localcontent, None),
    'c03b': ('NorthAmerica_c03b_nuclear_se', c03b_nuclear_se, None),
    'c04a': ('NorthAmerica_c04a_partnership', c04a_partnership, None),
    'c06b': ('NorthAmerica_c06b_dcpipeline', c06b_dcpipeline, None),
    'c07a': ('NorthAmerica_c07a_windpaced', c07a_windpaced, None),
    'c07b': ('NorthAmerica_c07b_windaccel', c07b_windaccel, None),
    'c08b': ('NorthAmerica_c08b_minerals', c08b_minerals, LARGE),
    'c09a': ('NorthAmerica_c09a_euprojects', c09a_euprojects, LARGE),
}

if __name__ == '__main__':
    print('repo:', B.REPO, '| apply:', B.APPLY)
    for key, (name, fn, filt) in CSCEN.items():
        if ONLY and key not in ONLY:
            continue
        clean(name)
        fn()
        if filt:
            B.filter_file(name, **filt)
        print(f'{name:34s}', {p: n for p, n in B.written.get(name, {}).items()}, '| filter:', 'own' if filt else 'base')
    print('APPLIED' if B.APPLY else 'DRY RUN (use --apply)')
