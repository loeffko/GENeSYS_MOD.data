# -*- coding: utf-8 -*-
# Conversion run for the North America placeholder model
# (9 US regions + Canada, years 2025-2040).
#
# Prerequisite: run expand_northamerica.py first so the CSVs and the
# Set_filter_file_NorthAmerica.xlsx preset exist.

settings_file = 'Set_filter_file_NorthAmerica.xlsx'
output_file_format = 'excel'
output_format = 'long'
processing_option = 'both'
scenario_option = 'NorthAmerica'
debugging_output = False
data_base_region = 'California'

from functions.function_import import master_function

master_function(settings_file, output_file_format, output_format,
                processing_option, scenario_option, debugging_output,
                data_base_region)
