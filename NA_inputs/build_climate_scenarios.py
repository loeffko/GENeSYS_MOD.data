# -*- coding: utf-8 -*-
"""Build the North America climate-adaptation scenario set (branch dev/fel-x-su-climate-adaptation).

Inputs (NA_inputs/SU Climate/):
  base_fel_v261023_cooling_climate.xlsx          FEL demand run with the cooling split and the climate adjustment
  2026-10-14 - Climate projections SSP2-45 for US.xlsx   hourly region-mean temperature, nine US ISO regions, 2030 and 2035 (UTC)
  2018_temperature_northamerica.csv              hourly region-mean temperature 2018 (GIS_&_Timeseries_Tool output) - calibration only
  GENeSYS_CapacityFactor_thermal_stress_<central|extreme|severe>.csv   hourly thermal-plant capacity factors (summer window)

Writes (all idempotent, existing output replaced):
  Par_SpecifiedAnnualDemand/<scenario>/            demand overlay from the climate FEL file (cooling -> Power_Buildings_Cooling)
  TS_POWER_BUILDINGS_HEAT_<2030|2035>/, TS_POWER_BUILDINGS_COOLING_<2030|2035>/
                                                   year-banded heating / cooling profiles (model: regular profile before 2030,
                                                   2030 profile for 2030-2034, 2035 profile from 2035 on)
  TS_CF_THERMAL_<group>/ (= 1) and TS_CF_THERMAL_<group>_2030/ (= 1; <scenario>/ overlays carry the stress profiles)
  Par_TagTechnologyToTimeseries/<scenario>/        binds the thermal technologies to their stress profile (CF sensitivities only)
  Conversion Script/Set_filter_file_NorthAmerica_climate.xlsx   NA filter + the new timeseries folders enabled
  Overview_GENeSYS-MOD.csv, Overview_Sources.csv, Assumptions.txt files, NA_inputs/SU Climate/derived/ (compact derived inputs)

Method notes
  Heating / cooling follow GENeSYSMOD.tools `temperature_timeseries`: heating = max(20 - T, 0), normalised per region to
  (x / mean + 0.25) / 1.25; cooling = max(T - 22, 0). The tool evaluates both per grid point and averages afterwards; the
  projections only give the region mean. Applying the formula to the mean sharpens the profiles (fewer non-zero hours,
  higher peaks), so the sub-regional spread is restored with a normal spread sigma_r around the regional mean,
  E[max(X - a, 0)] for X ~ N(T, sigma_r), with sigma_r (one for heating, one for cooling, per region) fitted so that the
  2018 region-mean temperature reproduces the point-based 2018 profile in the repository. Thermal stress: the three
  sensitivities carry identical hourly values for 2030-2050 and group into identical series per technology class
  (steam cycle, CCGT, OCGT); one 2030 variant per class is written, hours outside the summer window are 1.

Usage:  python NA_inputs/build_climate_scenarios.py [--apply]     (without --apply: report only)
"""
import os, sys, shutil, subprocess
import numpy as np
import pandas as pd
from scipy.stats import norm
from scipy.optimize import minimize_scalar

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, '..'))
SRC = os.path.join(HERE, 'SU Climate')
DERIVED = os.path.join(SRC, 'derived')
PAR = os.path.join(REPO, 'Data', 'Parameters')
TS = os.path.join(REPO, 'Data', 'Timeseries')
CONV = os.path.join(REPO, 'Conversion Script')
sys.path.insert(0, CONV)
from functions.expand_data import append_selection_rows  # noqa: E402

APPLY = '--apply' in sys.argv
DATE = '2026-10-23'
WHO = 'Konstantin Loffler <kl@wip.tu-berlin.de>'
FEL = os.path.join(SRC, 'base_fel_v261023_cooling_climate.xlsx')
SSP = os.path.join(SRC, '2026-10-14 - Climate projections SSP2-45 for US.xlsx')
T2018 = os.path.join(SRC, '2018_temperature_northamerica.csv')
CF_FILES = {s: os.path.join(SRC, f'GENeSYS_CapacityFactor_thermal_stress_{s}.csv') for s in ('central', 'extreme', 'severe')}

US = ['California', 'ERCOT', 'MISO', 'NewEngland', 'NewYork', 'PJM', 'SERC', 'SPP', 'WECC']
SCEN_BASE = 'NorthAmerica_climate_base'
SCEN_CF = {'central': 'NorthAmerica_climate_central', 'extreme': 'NorthAmerica_climate_extreme', 'severe': 'NorthAmerica_climate_severe'}
SCENARIOS = [SCEN_BASE] + list(SCEN_CF.values())
HEAT_T0, COOL_T0 = 20.0, 22.0          # tools-repo thresholds (deg C)
PROJ_YEARS = (2030, 2035)
CF_YEAR = 2030                          # the stress profiles are identical for every year >= 2030 (asserted below)
GROUP_NAME = {'P_Gas_CCGT': 'CCGT', 'P_Gas_OCGT': 'OCGT', 'P_Coal_Hardcoal': 'STEAM', 'P_Nuclear': 'STEAM'}

FEL_SOURCE = 'FEL 2026 Base with cooling split and climate adjustment (NA_inputs/SU Climate/base_fel_v261023_cooling_climate.xlsx)'
TS_SOURCE = ('SSP2-4.5 hourly region-mean temperature 2030/2035 (NA_inputs/SU Climate/2026-10-14 - Climate projections SSP2-45 for US.xlsx), '
             'GENeSYSMOD.tools heating/cooling formula with a sub-regional spread calibrated on 2018; '
             'non-US columns = regular profile; NA_inputs/build_climate_scenarios.py')
CF_SOURCE = 'Thermal-plant heat/water stress capacity factors (NA_inputs/SU Climate/GENeSYS_CapacityFactor_thermal_stress_{s}.csv), summer window, 1 elsewhere; NA_inputs/build_climate_scenarios.py'


def log(*a):
    print(*a, flush=True)


def eclip(mu, sigma):
    """E[max(X, 0)] for X ~ N(mu, sigma) elementwise; sigma = 0 -> max(mu, 0)."""
    mu = np.asarray(mu, float)
    if sigma <= 1e-9:
        return np.clip(mu, 0, None)
    z = mu / sigma
    return mu * norm.cdf(z) + sigma * norm.pdf(z)


def heating_profile(T, sigma):
    h = np.round(eclip(HEAT_T0 - T, sigma), 4)
    return np.round((h / h.mean() + 0.25) / 1.25, 4)


def cooling_profile(T, sigma):
    return np.round(eclip(T - COOL_T0, sigma), 4)


def shape(x):
    x = np.asarray(x, float)
    return x / x.sum() if x.sum() > 0 else x


def read_ts(folder):
    path = os.path.join(TS, folder, folder + '.csv')
    with open(path, encoding='utf-8') as f:
        src = f.readline().rstrip('\n')
    return src, pd.read_csv(path, header=1)


def write_ts(folder, df, source, sub=None):
    d = os.path.join(TS, folder, sub) if sub else os.path.join(TS, folder)
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, folder + '.csv')
    with open(p, 'w', encoding='utf-8', newline='\n') as f:
        f.write('Source: ' + source + '\n')
        df.to_csv(f, index=False, lineterminator='\n')
    return p


def write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)


def append_once(path, marker, text):
    old = open(path, encoding='utf-8').read() if os.path.exists(path) else ''
    if marker in old:
        return False
    with open(path, 'a', encoding='utf-8', newline='\n') as f:
        f.write(('' if old.endswith('\n') or not old else '\n') + text)
    return True


# ---------------------------------------------------------------- 1. demand overlays
def build_demand():
    log('\n== demand overlays (FEL cooling split) ==')
    for scen in SCENARIOS:
        cmd = [sys.executable, os.path.join(HERE, 'convert_fel_to_demand.py'), '--fel', os.path.relpath(FEL, HERE),
               '--scenario-subdir', scen, '--source', FEL_SOURCE, '--date', DATE]
        if APPLY:
            out = subprocess.run(cmd, capture_output=True, text=True, cwd=HERE)
            if out.returncode:
                raise RuntimeError(out.stderr)
            if scen == SCEN_BASE:
                log(out.stdout.strip())
        else:
            log('  would run:', ' '.join(cmd[1:4]), '...')
    if APPLY:
        df = pd.read_csv(os.path.join(PAR, 'Par_SpecifiedAnnualDemand', SCEN_BASE, 'Par_SpecifiedAnnualDemand.csv'))
        piv = df[df.Year.isin([2025, 2030, 2035, 2040])].pivot_table(index='Fuel', columns='Year', values='Value', aggfunc='sum') / 3.6
        log('  TWh by fuel (all NA regions):'); log(piv.round(1).to_string())
        return df


# ---------------------------------------------------------------- 2. heating / cooling variants
def calibrate_spread(T18, heat_ref, cool_ref):
    rows = []
    for r in US:
        t = T18[r].values
        def sse_h(s):
            return ((shape(heating_profile(t, s)) - shape(heat_ref[r].values)) ** 2).sum()
        def sse_c(s):
            return ((shape(cooling_profile(t, s)) - shape(cool_ref[r].values)) ** 2).sum()
        sh = minimize_scalar(sse_h, bounds=(0, 15), method='bounded').x
        sc = minimize_scalar(sse_c, bounds=(0, 15), method='bounded').x
        def peak(x):
            return float(shape(x).max() * 8760)
        rows.append({'Region': r, 'sigma_heating_K': round(sh, 3), 'sigma_cooling_K': round(sc, 3),
                     'heat_peak_ref': round(peak(heat_ref[r]), 2), 'heat_peak_direct': round(peak(heating_profile(t, 0)), 2),
                     'heat_peak_calibrated': round(peak(heating_profile(t, sh)), 2),
                     'cool_peak_ref': round(peak(cool_ref[r]), 2), 'cool_peak_direct': round(peak(cooling_profile(t, 0)), 2),
                     'cool_peak_calibrated': round(peak(cooling_profile(t, sc)), 2),
                     'cool_corr_direct': round(np.corrcoef(shape(cool_ref[r]), shape(cooling_profile(t, 0)))[0, 1], 4),
                     'cool_corr_calibrated': round(np.corrcoef(shape(cool_ref[r]), shape(cooling_profile(t, sc)))[0, 1], 4)})
    return pd.DataFrame(rows)


def read_projection():
    x = pd.ExcelFile(SSP)
    out = {y: pd.DataFrame(index=range(1, 8761)) for y in PROJ_YEARS}
    for r in US:
        df = x.parse(r)
        df.columns = ['Year', 'Month', 'Day', 'Hour', 'T', 'Points']
        for y in PROJ_YEARS:
            d = df[df.Year == y].sort_values(['Month', 'Day', 'Hour'])
            assert len(d) == 8760 and d['T'].notna().all(), (r, y, len(d))
            assert list(d.Hour.values[:3]) == [0, 1, 2]
            out[y][r] = d['T'].values
    return out


def build_heat_cool():
    log('\n== heating / cooling profiles 2030 / 2035 ==')
    src_h, heat = read_ts('TS_POWER_BUILDINGS_HEAT')
    src_c, cool = read_ts('TS_POWER_BUILDINGS_COOLING')
    T18 = pd.read_csv(T2018, index_col=0)
    assert len(T18) == 8760 and all(r in T18.columns for r in US)
    cal = calibrate_spread(T18, heat, cool)
    log('  sub-regional spread calibration on 2018 (peak = max/mean of the normalised profile):')
    log(cal.to_string(index=False))
    proj = read_projection()
    stats = []
    for y in PROJ_YEARS:
        h = heat.copy(); c = cool.copy()
        for r in US:
            t = proj[y][r].values
            sh = float(cal.loc[cal.Region == r, 'sigma_heating_K'].iloc[0]); sc = float(cal.loc[cal.Region == r, 'sigma_cooling_K'].iloc[0])
            h[r] = heating_profile(t, sh); c[r] = cooling_profile(t, sc)
            stats.append({'Year': y, 'Region': r, 'T_mean': round(t.mean(), 2), 'T_mean_2018': round(T18[r].mean(), 2),
                          'HDH20_vs_2018_%': round(100 * (np.clip(20 - t, 0, None).sum() / np.clip(20 - T18[r].values, 0, None).sum() - 1), 1),
                          'CDH22_vs_2018_%': round(100 * (np.clip(t - 22, 0, None).sum() / max(np.clip(T18[r].values - 22, 0, None).sum(), 1e-9) - 1), 1),
                          'cool_peak': round(float(shape(c[r]).max() * 8760), 1), 'cool_peak_2018': round(float(shape(cool[r]).max() * 8760), 1),
                          'heat_peak': round(float(shape(h[r]).max() * 8760), 2), 'heat_peak_2018': round(float(shape(heat[r]).max() * 8760), 2)})
        if APPLY:
            write_ts(f'TS_POWER_BUILDINGS_HEAT_{y}', h, f'{TS_SOURCE}; {DATE}; {WHO}')
            write_ts(f'TS_POWER_BUILDINGS_COOLING_{y}', c, f'{TS_SOURCE}; {DATE}; {WHO}')
    st = pd.DataFrame(stats)
    log('  projection vs 2018 (HDH/CDH = heating/cooling degree hours of the region-mean temperature):')
    log(st.to_string(index=False))
    if APPLY:
        os.makedirs(DERIVED, exist_ok=True)
        cal.to_csv(os.path.join(DERIVED, 'spread_calibration_2018.csv'), index=False, lineterminator='\n')
        st.to_csv(os.path.join(DERIVED, 'heat_cool_profile_stats.csv'), index=False, lineterminator='\n')
        note = (f"TS_POWER_BUILDINGS_HEAT_<YYYY> / TS_POWER_BUILDINGS_COOLING_<YYYY> ({DATE})\n"
                "Year-banded variants of the regular heating / cooling profiles: the model uses the regular profile for\n"
                "years before 2030, the _2030 sheet for 2030-2034 and the _2035 sheet from 2035 on (latest year <= model year).\n"
                "Source: SSP2-4.5 hourly region-mean temperature for the nine US ISO regions (NA_inputs/SU Climate/\n"
                "2026-10-14 - Climate projections SSP2-45 for US.xlsx, UTC like the 2018 series). Non-US columns copy the\n"
                "regular profile (no projection available), so the variant is a no-op there.\n"
                "Method (GENeSYSMOD.tools GIS_&_Timeseries_Tool/functions.py::temperature_timeseries): heating = max(20 - T, 0)\n"
                "normalised per region to (x / mean + 0.25) / 1.25; cooling = max(T - 22, 0). The tool evaluates the formula per\n"
                "grid point and averages afterwards; the projections only give the region mean, and the formula on the mean\n"
                "sharpens the profile (cooling peak/mean +40-75 %). The sub-regional spread is therefore restored as\n"
                "E[max(X - a, 0)] with X ~ N(T_mean, sigma_r); sigma_r (heating and cooling separately, per region) is fitted so\n"
                "that the 2018 region-mean temperature reproduces the point-based 2018 profile of the repository\n"
                "(NA_inputs/SU Climate/derived/spread_calibration_2018.csv; shape correlation 0.98-1.00, peaks within a few %).\n"
                "Generated by NA_inputs/build_climate_scenarios.py.\n")
        for y in PROJ_YEARS:
            for fam in ('TS_POWER_BUILDINGS_HEAT', 'TS_POWER_BUILDINGS_COOLING'):
                write_text(os.path.join(TS, f'{fam}_{y}', 'Assumptions.txt'), note)
    return cal, st


# ---------------------------------------------------------------- 3. thermal stress capacity factors
def read_stress(sens):
    df = pd.read_csv(CF_FILES[sens])
    piv = df.pivot_table(index=['Region', 'Technology', 'Timeslice'], columns='Year', values='Value')
    years = sorted(piv.columns)
    for y in years[1:]:
        assert np.allclose(piv[years[0]].fillna(-1), piv[y].fillna(-1)), f'{sens}: {y} differs from {years[0]}'
    d = df[df.Year == CF_YEAR]
    hours = np.arange(1, 8761)
    series = {}
    for (r, t), g in d.groupby(['Region', 'Technology']):
        s = pd.Series(1.0, index=hours)
        s.loc[g.Timeslice.values] = g.Value.values
        series[(r, t)] = s.values
    techs = sorted(set(t for _, t in series))
    regions = sorted(set(r for r, _ in series))
    # group technologies with identical series in every region
    key = {t: tuple(np.round(np.concatenate([series[(r, t)] for r in regions]), 6)) for t in techs}
    groups = {}
    for t in techs:
        groups.setdefault(key[t], []).append(t)
    named = {}
    for members in groups.values():
        name = next((GROUP_NAME[m] for m in GROUP_NAME if m in members), None) or f'GROUP{len(named) + 1}'
        assert name not in named, name
        named[name] = sorted(members)
    return series, named, regions, (int(d.Timeslice.min()), int(d.Timeslice.max()))


def build_cf():
    log('\n== thermal stress capacity factors ==')
    src_h, heat = read_ts('TS_POWER_BUILDINGS_HEAT')
    cols = [c for c in heat.columns if c != 'HOUR']
    ones = pd.DataFrame({'HOUR': np.arange(1, 8761), **{c: 1.0 for c in cols}})
    tag_rows = {}
    summary = []
    group_names = None
    for sens, scen in SCEN_CF.items():
        series, named, regions, window = read_stress(sens)
        if group_names is None:
            group_names = sorted(named)
        assert sorted(named) == group_names and all(named[g] == named_ref[g] for g in named) if (named_ref := named if sens == 'central' else named_ref) is None else True
        log(f'  {sens}: regions {len(regions)}, window hours {window}, groups: ' + '; '.join(f'{g} ({len(m)} techs)' for g, m in named.items()))
        compact = []
        for g, members in named.items():
            df = ones.copy()
            for r in regions:
                df[r] = series[(r, members[0])]
                compact.append(pd.DataFrame({'Region': r, 'Profile': f'CF_THERMAL_{g}', 'HOUR': df.HOUR, 'Value': df[r]}).query('Value < 1'))
                summary.append({'sensitivity': sens, 'group': g, 'Region': r, 'annual_mean': round(df[r].mean(), 4), 'min': round(df[r].min(), 3),
                                'hours_below_1': int((df[r] < 1).sum())})
            if APPLY:
                write_ts(f'TS_CF_THERMAL_{g}_{CF_YEAR}', df, f'{CF_SOURCE.format(s=sens)}; {DATE}; {WHO}', sub=scen)
            tag_rows[scen] = tag_rows.get(scen, []) + [{'Technology': t, 'Profile': f'CF_THERMAL_{g}', 'Value': 1, '': '', 'Unit': 'Tag',
                                                         'Source': f'thermal stress sensitivity {sens}: hourly CF profile TS_CF_THERMAL_{g} (1 before {CF_YEAR})',
                                                         'Updated at': DATE, 'Updated by': WHO} for t in members]
        if APPLY:
            os.makedirs(DERIVED, exist_ok=True)
            pd.concat(compact).to_csv(os.path.join(DERIVED, f'thermal_stress_{sens}_{CF_YEAR}_compact.csv'), index=False, lineterminator='\n')
    sm = pd.DataFrame(summary)
    log(sm.pivot_table(index=['group', 'Region'], columns='sensitivity', values='annual_mean').round(4).to_string())
    if APPLY:
        for g in group_names:
            src = f'neutral default (= 1 every hour); thermal stress profiles enter as TS_CF_THERMAL_{g}_{CF_YEAR}/<scenario> overlays; {DATE}; {WHO}'
            write_ts(f'TS_CF_THERMAL_{g}', ones, src)
            write_ts(f'TS_CF_THERMAL_{g}_{CF_YEAR}', ones, src)
            note = (f"TS_CF_THERMAL_{g} / TS_CF_THERMAL_{g}_{CF_YEAR} ({DATE})\n"
                    f"Hourly availability (capacity factor) profile for the {g} thermal technology class, bound to the technologies by\n"
                    "Par_TagTechnologyToTimeseries (scenario overlays). The base CSVs are 1 everywhere (no effect); the\n"
                    f"NorthAmerica_climate_<central|extreme|severe> overlays of the _{CF_YEAR} folder hold the SSP2-4.5 heat / cooling-water\n"
                    "stress derates (NA_inputs/SU Climate/GENeSYS_CapacityFactor_thermal_stress_<sens>.csv: nine US regions, summer\n"
                    f"window hours {window[0]}-{window[1]}, identical for every year 2030-2050, hence one {CF_YEAR} variant; 1 outside the\n"
                    "window and for regions without data). central = temperature only; extreme = temperature + river temperature /\n"
                    "flow; severe = extreme with the historic drought years baked in. Members: " + ', '.join(named[g]) + ".\n"
                    "Generated by NA_inputs/build_climate_scenarios.py.\n")
            write_text(os.path.join(TS, f'TS_CF_THERMAL_{g}', 'Assumptions.txt'), note)
            write_text(os.path.join(TS, f'TS_CF_THERMAL_{g}_{CF_YEAR}', 'Assumptions.txt'), note)
        sm.to_csv(os.path.join(DERIVED, 'thermal_stress_summary.csv'), index=False, lineterminator='\n')
        # tag parameter: header-only base + per-scenario overlays
        pdir = os.path.join(PAR, 'Par_TagTechnologyToTimeseries')
        cols_tag = ['Technology', 'Profile', 'Value', '', 'Unit', 'Source', 'Updated at', 'Updated by']
        base = os.path.join(pdir, 'Par_TagTechnologyToTimeseries.csv')
        if not os.path.exists(base):
            write_text(base, ','.join(cols_tag) + '\n')
        for scen, rows in tag_rows.items():
            out = os.path.join(pdir, scen, 'Par_TagTechnologyToTimeseries.csv')
            os.makedirs(os.path.dirname(out), exist_ok=True)
            pd.DataFrame(rows)[cols_tag].sort_values(['Profile', 'Technology']).to_csv(out, index=False, lineterminator='\n')
        write_text(os.path.join(pdir, 'Assumptions.txt'),
                   f"Par_TagTechnologyToTimeseries (Technology, Profile) - optional, {DATE}\n"
                   "Binds a technology's capacity factor to an hourly timeseries sheet TS_<Profile> of the timeseries workbook,\n"
                   "the way the renewables follow their resource profiles (reduced and scaled by the model's timeseries\n"
                   "reduction; year-banded TS_<Profile>_<YYYY> variants apply from year YYYY on). Meant for data-declared\n"
                   "availability profiles of otherwise firm plants. The model also credits a tagged plant in the peaking\n"
                   "constraint with its worst-timeslice capacity factor instead of the variable-RES credit. The column is\n"
                   "named Profile (a 'Timeseries' header would be filtered by the converter). The base CSV is header-only;\n"
                   "the NorthAmerica_climate_<central|extreme|severe> overlays bind the thermal classes to TS_CF_THERMAL_<group>.\n")
    return group_names, tag_rows


# ---------------------------------------------------------------- 2b. residual load shape for Power_General
def build_residual_general():
    """TS_LOAD is the measured pool load and already contains the heating and cooling load. Giving Power_Buildings_Heat
    and Power_Buildings_Cooling their own profiles on top of it double-counts both peaks (v6: winter-peaking in 7 of 9
    pools; the cooling split: summer peaks 6-42 % above the 2024 ISO peaks). TS_POWER_GENERAL is the residual shape:
    (general + heat + cooling energy of the base year) x load shape minus heat x heating shape minus cooling x cooling
    shape, clipped at zero and renormalised, so that general + heat + cooling reproduce the measured load shape in the
    base year. Regions without the split (no Power_Buildings_* demand) keep the load shape. Bound to Power_General
    through Par_TagFuelToTimeseries overlays of the climate scenarios."""
    log('\n== residual load shape for Power_General ==')
    src_l, load = read_ts('TS_LOAD')
    _, heat = read_ts('TS_POWER_BUILDINGS_HEAT'); _, cool = read_ts('TS_POWER_BUILDINGS_COOLING')
    dem = pd.read_csv(os.path.join(PAR, 'Par_SpecifiedAnnualDemand', SCEN_BASE, 'Par_SpecifiedAnnualDemand.csv'))
    base_year = int(dem.Year.min())
    d = dem[dem.Year == base_year].pivot_table(index='Region', columns='Fuel', values='Value', aggfunc='sum').fillna(0.0)
    out = load.copy(); rows = []
    for r in [c for c in load.columns if c != 'HOUR']:
        if r not in d.index or r not in heat.columns or r not in cool.columns:
            continue
        G = float(d.loc[r].get('Power_General', 0)); H = float(d.loc[r].get('Power_Buildings_Heat', 0)); C = float(d.loc[r].get('Power_Buildings_Cooling', 0))
        if H + C <= 0:
            continue
        ls, hs, cs = shape(load[r].values), shape(heat[r].values), shape(cool[r].values)
        resid = (G + H + C) * ls - H * hs - C * cs
        neg = int((resid < 0).sum()); resid = np.clip(resid, 0, None)
        out[r] = np.round(resid / resid.max(), 6)          # same 0..1 convention as TS_LOAD
        tot_v6 = (G + C) * ls + H * hs; tot_split = G * ls + H * hs + C * cs; tot_res = G * shape(resid) + H * hs + C * cs
        rows.append({'Region': r, 'base_year': base_year, 'general_PJ': round(G, 1), 'heat_PJ': round(H, 1), 'cool_PJ': round(C, 1), 'neg_hours_clipped': neg,
                     'peak_hour_load': int(np.argmax(ls)) + 1, 'peak_v6_over_loadshape': round(float(tot_v6.max() / ((G + H + C) * ls).max()), 3),
                     'peak_split_over_loadshape': round(float(tot_split.max() / ((G + H + C) * ls).max()), 3), 'peak_residual_over_loadshape': round(float(tot_res.max() / ((G + H + C) * ls).max()), 3)})
    st = pd.DataFrame(rows); log(st.to_string(index=False))
    if APPLY:
        write_ts('TS_POWER_GENERAL', out, f'residual load shape = load - heating - cooling components of {base_year} (NA regions; other columns = TS_LOAD); NA_inputs/build_climate_scenarios.py; {DATE}; {WHO}')
        write_text(os.path.join(TS, 'TS_POWER_GENERAL', 'Assumptions.txt'),
                   f"TS_POWER_GENERAL ({DATE}) - residual load shape for the Power_General end use.\n"
                   "TS_LOAD is the measured pool load and already contains the electric heating and cooling load. When\n"
                   "Power_Buildings_Heat and Power_Buildings_Cooling carry their own temperature-derived profiles on top of the\n"
                   "load shape, both peaks are counted twice (v6 base: winter-peaking in 7 of 9 US pools; cooling split: summer\n"
                   "peaks 6-42 % above the 2024 ISO peaks). This profile is (general + heat + cooling energy of the base year) x\n"
                   "load shape - heat x heating shape - cooling x cooling shape, clipped at zero (a few hours per pool) and\n"
                   "normalised to its maximum, so that general + heat + cooling reproduce the measured load shape in the base\n"
                   "year; later years inherit the shape. Regions without the end-use split keep the load shape. Bound to\n"
                   "Power_General by Par_TagFuelToTimeseries (NorthAmerica_climate_* overlays). Check table:\n"
                   "NA_inputs/SU Climate/derived/residual_general_shape.csv. Generated by NA_inputs/build_climate_scenarios.py.\n")
        os.makedirs(DERIVED, exist_ok=True); st.to_csv(os.path.join(DERIVED, 'residual_general_shape.csv'), index=False, lineterminator='\n')
        pdir = os.path.join(PAR, 'Par_TagFuelToTimeseries'); cols = ['Fuel', 'Profile', 'Value', '', 'Unit', 'Source', 'Updated at', 'Updated by']
        base = os.path.join(pdir, 'Par_TagFuelToTimeseries.csv')
        if not os.path.exists(base):
            write_text(base, ','.join(cols) + '\n')
            write_text(os.path.join(pdir, 'Assumptions.txt'),
                       "Par_TagFuelToTimeseries (Fuel, Profile) - optional. Binds a demand fuel to the hourly profile TS_<Profile> of the\n"
                       "timeseries workbook instead of the model's built-in mapping (column named Profile because the converter filters a\n"
                       "'Timeseries' header). Base CSV header-only; the NorthAmerica_climate_* overlays bind Power_General to the residual\n"
                       f"load shape TS_POWER_GENERAL ({DATE}).\n")
        for scen in SCENARIOS:
            os.makedirs(os.path.join(pdir, scen), exist_ok=True)
            pd.DataFrame([{'Fuel': 'Power_General', 'Profile': 'POWER_GENERAL', 'Value': 1, '': '', 'Unit': 'Tag',
                           'Source': 'residual load shape (TS_POWER_GENERAL): load minus the heating and cooling components of the base year', 'Updated at': DATE, 'Updated by': WHO}])[cols] \
                .to_csv(os.path.join(pdir, scen, 'Par_TagFuelToTimeseries.csv'), index=False, lineterminator='\n')
    return st


# ---------------------------------------------------------------- 3b. annual activity floors of derated plants
def build_activity_floors(tag_rows):
    """Par_TotalAnnualMinActivity (model: TotalTechnologyAnnualActivityLowerLimit) carries fleet minimum-generation
    floors (NA: P_Biomass at 61-95 % of the availability ceiling). A derated plant pinned to such a floor is infeasible
    (probe IIS 2026-10-23: P_Biomass SERC), so in the CF scenarios the floors of tagged technologies are scaled from
    CF_YEAR on by the annual-mean capacity factor of their stress profile in that region. Rows for untagged
    technologies, other regions and years before CF_YEAR stay as in the base."""
    log('\n== annual minimum-activity floors of derated plants ==')
    base_csv = os.path.join(PAR, 'Par_TotalAnnualMinActivity', 'Par_TotalAnnualMinActivity.csv')
    base = pd.read_csv(base_csv).rename(columns={'Unnamed: 4': ''})
    cols = list(base.columns)
    for sens, scen in SCEN_CF.items():
        tags = {r['Technology']: r['Profile'].replace('CF_THERMAL_', '') for r in tag_rows[scen]}
        means = {}
        for g in set(tags.values()):
            ts = pd.read_csv(os.path.join(TS, f'TS_CF_THERMAL_{g}_{CF_YEAR}', scen, f'TS_CF_THERMAL_{g}_{CF_YEAR}.csv'), header=1)
            for r in US:
                means[(g, r)] = float(ts[r].mean())
        sel = base[base.Region.isin(US) & base.Technology.isin(tags) & (base.Year >= CF_YEAR) & (base.Value > 0)].copy()
        if sel.empty:
            log(f'  {sens}: no floors on tagged technologies - nothing to scale'); continue
        sel['scale'] = [means[(tags[t], r)] for t, r in zip(sel.Technology, sel.Region)]
        sel['Value'] = (sel.Value * sel.scale).round(4)
        sel['Source'] = [f'base floor x annual-mean stress CF {s:.4f} (TS_CF_THERMAL_{tags[t]}_{CF_YEAR}, {sens}); {src}' for s, t, src in zip(sel.scale, sel.Technology, sel.Source)]
        sel['Updated at'] = DATE; sel['Updated by'] = WHO
        log(f'  {sens}: {len(sel)} floor rows scaled, factor {sel.scale.min():.3f}-{sel.scale.max():.3f} ({", ".join(sorted(sel.Technology.unique()))})')
        if APPLY:
            out = os.path.join(PAR, 'Par_TotalAnnualMinActivity', scen, 'Par_TotalAnnualMinActivity.csv')
            os.makedirs(os.path.dirname(out), exist_ok=True)
            sel[cols].sort_values(['Region', 'Technology', 'Year']).to_csv(out, index=False, lineterminator='\n')
    if APPLY:
        append_once(os.path.join(PAR, 'Par_TotalAnnualMinActivity', 'Assumptions.txt'), f'NorthAmerica_climate_<central|extreme|severe> ({DATE})',
                    f"\nNorthAmerica_climate_<central|extreme|severe> ({DATE}): the P_Biomass fleet floors of the nine US regions are\n"
                    f"scaled from {CF_YEAR} on by the annual-mean thermal-stress capacity factor of the STEAM class in that region\n"
                    "(TS_CF_THERMAL_STEAM_2030/<scenario>), because a plant whose summer availability is cut cannot keep a floor set\n"
                    "at ~90 % of its undisturbed availability ceiling (probe IIS 2026-10-23). Generated by NA_inputs/build_climate_scenarios.py.\n")


# ---------------------------------------------------------------- 3c. no fossil expansion beyond the v6f path
NOFOSSIL_PARENTS = {'NorthAmerica_climate_base': 'NorthAmerica_climate_base_nofossil',
                    'NorthAmerica_climate_extreme': 'NorthAmerica_climate_extreme_nofossil',
                    'NorthAmerica_climate_severe': 'NorthAmerica_climate_severe_nofossil'}
FOSSIL_TECHS = ['P_Gas_CCGT', 'P_Gas_CCGT_Residual', 'P_Gas_OCGT', 'P_Gas_Steam', 'P_Gas_Engines', 'P_Gas_CCS',
                'P_Coal_Hardcoal', 'P_Coal_Lignite', 'P_Coal_Hardcoal_CCS', 'P_Coal_Lignite_CCS', 'P_Oil',
                'CHP_Gas_CCGT_Natural', 'CHP_Gas_CCGT_Natural_CCS', 'CHP_Coal_Hardcoal', 'CHP_Coal_Hardcoal_CCS',
                'CHP_Coal_Lignite', 'CHP_Coal_Lignite_CCS', 'CHP_Oil',
                'P_Nuclear', 'P_Nuclear_SMR']   # nuclear added 2026-10-25: no nuclear expansion beyond v6f either (few advanceable projects; derated as well)
FORBID = 0.001        # TotalAnnualMaxCapacity marker: 0 would mean "no limit" for FossilPower techs (bounds rule)


def copy_overlays(parent, child):
    """Copy every Par_*/<parent>/ and TS_*/<parent>/ overlay folder to <child> (child folders replaced)."""
    n = 0
    for root in (PAR, TS):
        for fam in os.listdir(root):
            src = os.path.join(root, fam, parent)
            if os.path.isdir(src):
                dst = os.path.join(root, fam, child)
                if os.path.isdir(dst):
                    shutil.rmtree(dst)
                shutil.copytree(src, dst); n += 1
    return n


def build_nofossil():
    """Variants with no fossil or nuclear expansion beyond the v6f base: TotalAnnualMaxCapacity of every gas, coal, oil and nuclear
    technology = the v6f total-capacity path of that region and year (NA_inputs/SU Climate/derived/
    v6f_fossil_capacity.csv, exported from the results DB of fel2026_base_49_2015_v6f), FORBID where v6f has none.
    The adaptation to the climate inputs then has to come from renewables, storage, nuclear and trade."""
    log('\n== no-fossil-expansion variants ==')
    src = os.path.join(DERIVED, 'v6f_fossil_capacity.csv')
    if not os.path.exists(src):
        log('  v6f_fossil_capacity.csv missing - skipped'); return
    v6 = pd.read_csv(src)
    regions = sorted(v6.Region.unique()); years = sorted(v6.Year.unique())
    cols = ['Region', 'Technology', 'Year', 'Value', '', 'Unit', 'Source', 'Updated at', 'Updated by']
    rows = []
    for r in regions:
        for t in FOSSIL_TECHS:
            for y in years:
                v = v6[(v6.Region == r) & (v6.Technology == t) & (v6.Year == y)].Value
                cap = float(v.iloc[0]) if len(v) else 0.0
                rows.append({'Region': r, 'Technology': t, 'Year': int(y), 'Value': round(max(cap * 1.001 + FORBID, FORBID), 4), '': '', 'Unit': 'GW',
                             'Source': 'v6f capacity path (fel2026_base_49_2015_v6f) + 0.1 % and 0.001 GW margin: no fossil expansion beyond the regular base',
                             'Updated at': DATE, 'Updated by': WHO})
    df = pd.DataFrame(rows)[cols]
    log(f'  {len(df)} cap rows ({len(regions)} regions x {len(FOSSIL_TECHS)} techs x {len(years)} years); NA fossil GW 2040 capped at {round(v6[v6.Year == years[-1]].Value.sum(), 0)}')
    if APPLY:
        for parent, child in NOFOSSIL_PARENTS.items():
            n = copy_overlays(parent, child)
            out = os.path.join(PAR, 'Par_TotalAnnualMaxCapacity', child, 'Par_TotalAnnualMaxCapacity.csv')
            os.makedirs(os.path.dirname(out), exist_ok=True)
            df.to_csv(out, index=False, lineterminator='\n')
            log(f'  {child}: {n} overlay folders copied from {parent} + fossil cap overlay')
        append_once(os.path.join(PAR, 'Par_TotalAnnualMaxCapacity', 'Assumptions.txt'), 'NorthAmerica_climate_*_nofossil (2026-10-25',
                    "\nNorthAmerica_climate_*_nofossil (2026-10-25, supersedes the 2026-10-23 note): TotalAnnualMaxCapacity of the gas,\n"
                    "coal, oil AND nuclear technologies (incl. CCS, CHP and SMR) set to the v6f total-capacity path per region and year (+0.1 % and 0.001 GW\n"
                    "margin; 0.001 = forbidden where v6f has none, since 0 would lift the limit for FossilPower techs), so the\n"
                    "climate cases cannot expand fossil capacity beyond the regular base. Source: results DB scenario\n"
                    "fel2026_base_49_2015_v6f, exported to NA_inputs/SU Climate/derived/v6f_fossil_capacity.csv. Generated by\n"
                    "NA_inputs/build_climate_scenarios.py.\n")


# ---------------------------------------------------------------- 4. filter file + registries
def build_filter_and_registries(group_names):
    log('\n== filter file + registries ==')
    new_ts = ['TS_POWER_GENERAL'] + [f'TS_POWER_BUILDINGS_HEAT_{y}' for y in PROJ_YEARS] + [f'TS_POWER_BUILDINGS_COOLING_{y}' for y in PROJ_YEARS] \
        + [f'TS_CF_THERMAL_{g}' for g in group_names] + [f'TS_CF_THERMAL_{g}_{CF_YEAR}' for g in group_names]
    flt = os.path.join(CONV, 'Set_filter_file_NorthAmerica_climate.xlsx')
    if APPLY:
        shutil.copy(os.path.join(CONV, 'Set_filter_file_NorthAmerica.xlsx'), flt)
        added = append_selection_rows(flt, 'Timeseries_selection', new_ts, selected=1)
        log(f'  {os.path.basename(flt)}: enabled {len(added)} new timeseries folders')
        # Overview_GENeSYS-MOD.csv
        ov = os.path.join(REPO, 'Overview_GENeSYS-MOD.csv')
        txt = open(ov, encoding='utf-8-sig').read()
        lines = []
        for y in PROJ_YEARS:
            lines.append(f'TS_POWER_BUILDINGS_HEAT_{y},Hourly buildings electric heating profile valid from model year {y} on (year-banded variant of TS_POWER_BUILDINGS_HEAT),')
            lines.append(f'TS_POWER_BUILDINGS_COOLING_{y},Hourly buildings electric cooling profile valid from model year {y} on (year-banded variant of TS_POWER_BUILDINGS_COOLING),')
        for g in group_names:
            lines.append(f'TS_CF_THERMAL_{g},Hourly availability (capacity factor) profile of the {g} thermal technology class (1 = no derate),')
            lines.append(f'TS_CF_THERMAL_{g}_{CF_YEAR},Hourly availability profile of the {g} thermal class valid from model year {CF_YEAR} on,')
        lines.append('Par_TagTechnologyToTimeseries,Binds a technology capacity factor to the hourly profile TS_<Profile> (optional; absent = no binding),Tag')
        lines.append('Par_TagFuelToTimeseries,Binds a demand fuel to the hourly profile TS_<Profile> instead of the built-in mapping (optional),Tag')
        lines.append('TS_POWER_GENERAL,Hourly residual load shape of the Power_General end use (load minus the heating and cooling components of the base year),')
        add = [l for l in lines if l.split(',')[0] + ',' not in txt]
        if add:
            with open(ov, 'a', encoding='utf-8', newline='\n') as f:
                f.write(('' if txt.endswith('\n') else '\n') + '\n'.join(add) + '\n')
        log(f'  Overview_GENeSYS-MOD.csv: +{len(add)} rows')
        # Overview_Sources.csv
        srcs = os.path.join(REPO, 'Overview_Sources.csv')
        txt = open(srcs, encoding='utf-8-sig').read()
        rows = [
            'SU Climate SSP2-4.5 temperature projections US ISO regions (2026-10-14),2026-10-14 - Climate projections SSP2-45 for US.xlsx,internal project input (NA_inputs/SU Climate/),TS_POWER_BUILDINGS_HEAT_2030; TS_POWER_BUILDINGS_HEAT_2035; TS_POWER_BUILDINGS_COOLING_2030; TS_POWER_BUILDINGS_COOLING_2035',
            'SU Climate thermal-plant stress capacity factors (central/extreme/severe),GENeSYS_CapacityFactor_thermal_stress_<sens>.csv,internal project input (NA_inputs/SU Climate/; compact copies in NA_inputs/SU Climate/derived/),' + '; '.join(f'TS_CF_THERMAL_{g}_{CF_YEAR}' for g in group_names) + '; Par_TagTechnologyToTimeseries',
            'FEL 2026 Base with cooling split and climate adjustment (2026-10-23),base_fel_v261023_cooling_climate.xlsx,internal project input (NA_inputs/SU Climate/),Par_SpecifiedAnnualDemand (NorthAmerica_climate_* overlays)',
            'GIS_&_Timeseries_Tool 2018 region-mean temperature North America,2018_temperature_northamerica.csv,GENeSYSMOD.tools GIS_&_Timeseries_Tool output/2018 (copy in NA_inputs/SU Climate/),TS_POWER_BUILDINGS_HEAT_2030/2035 and TS_POWER_BUILDINGS_COOLING_2030/2035 (spread calibration only)',
        ]
        add = [r for r in rows if r.split(',')[1] not in txt]
        if add:
            with open(srcs, 'a', encoding='utf-8', newline='\n') as f:
                f.write(('' if txt.endswith('\n') else '\n') + '\n'.join(add) + '\n')
        log(f'  Overview_Sources.csv: +{len(add)} rows')
        # demand assumptions
        marker = f'NorthAmerica_climate_* scenarios ({DATE})'
        append_once(os.path.join(PAR, 'Par_SpecifiedAnnualDemand', 'Assumptions.txt'), marker,
                    f"\n{marker} - climate-adaptation set on the v6-freeze basis.\n"
                    "Demand overlays from the FEL 2026 Base run with the cooling split and the climate adjustment\n"
                    "(NA_inputs/SU Climate/base_fel_v261023_cooling_climate.xlsx) via NA_inputs/convert_fel_to_demand.py:\n"
                    "the new 'cooling' busbar sector -> Power_Buildings_Cooling (previously part of Power_General);\n"
                    "buildings heating (Electric_Boiler + HP_* incl. Heating_Climate_Adj) -> Power_Buildings_Heat as before;\n"
                    "data centres, industry, hydrogen and transport unchanged against base_fel_v260707_v2.xlsx. The four\n"
                    "scenario options (climate_base, climate_central, climate_extreme, climate_severe) share one demand overlay;\n"
                    "they differ only in the thermal-stress capacity factors (Par_TagTechnologyToTimeseries + TS_CF_THERMAL_*).\n")
    else:
        log('  would create', os.path.basename(flt), 'and register', len(new_ts), 'timeseries folders')


def main():
    for p in [FEL, SSP, T2018] + list(CF_FILES.values()):
        assert os.path.exists(p), p
    log('mode:', 'APPLY' if APPLY else 'report only')
    build_demand()
    build_residual_general()
    build_heat_cool()
    group_names, tag_rows = build_cf()
    build_activity_floors(tag_rows)
    build_nofossil()
    build_filter_and_registries(group_names)
    log('\nDONE' if APPLY else '\nreport only - rerun with --apply to write')


if __name__ == '__main__':
    main()
