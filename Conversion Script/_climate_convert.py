# -*- coding: utf-8 -*-
# Convert the climate-adaptation scenario set (v6-freeze base + NorthAmerica_climate_* overlays, weather year 2015)
# and copy the workbooks to the model repo's InputData. Run from this folder:
#   python _climate_convert.py [base central extreme severe]
import os, shutil, sys, time
from functions.function_import import master_function

SCEN = {'base': 'NorthAmerica_climate_base', 'central': 'NorthAmerica_climate_central',
        'extreme': 'NorthAmerica_climate_extreme', 'severe': 'NorthAmerica_climate_severe',
        'base_nofossil': 'NorthAmerica_climate_base_nofossil', 'extreme_nofossil': 'NorthAmerica_climate_extreme_nofossil',
        'severe_nofossil': 'NorthAmerica_climate_severe_nofossil'}
FILTER = 'Set_filter_file_NorthAmerica_climate.xlsx'
WEATHER_YEAR = 2015
OUT = os.path.join('..', 'Output', 'output_excel')
DST = r'C:\Users\testbed\Documents\GENeSYSMOD.jl_SE\InputData'

only = sys.argv[1:] or list(SCEN)
for k in only:
    s = SCEN[k]
    t0 = time.time()
    print(f'\n===== {s}  (filter {FILTER}, weather year {WEATHER_YEAR})', flush=True)
    master_function(FILTER, 'excel', 'long', 'both', s, False, 'California', weather_year=WEATHER_YEAR)
    for name in (f'RegularParameters_{s}.xlsx', f'Timeseries_{s}_{WEATHER_YEAR}.xlsx'):
        src = os.path.join(OUT, name)
        if not os.path.exists(src):
            print('  MISSING output', name, flush=True); continue
        shutil.copy(src, os.path.join(DST, name))
        print(f'  -> InputData/{name}  ({time.time() - t0:.0f} s)', flush=True)
print('CLIMATE CONVERSIONS DONE', flush=True)
