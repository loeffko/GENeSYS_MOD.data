import os
import pandas as pd

def _merge_override(df, override_csv_path):
    """Column-wise override of the base timeseries: merge on HOUR and replace
    only the regions present in the override file (combine_first per column),
    so regions absent there keep the base data - per-region fallback."""
    df_over = pd.read_csv(override_csv_path, header=1)
    common_cols = [c for c in df.columns if c in df_over.columns and c != 'Value']
    df = df.merge(df_over, on='HOUR', how='left', suffixes=('', '_updated'))
    for col in common_cols:
        if col != 'HOUR':
            df[col] = df[col + '_updated'].combine_first(df[col])
            df.drop(col + '_updated', axis=1, inplace=True)
    return df


def read_filter_timeseries(timeseries_dir, unique_values_concatenated, scenario_option, debugging_output, weather_year='base'):
    filtered_data = {}
    overwritten_data_info = []

    unique_regions = unique_values_concatenated['Region'].unique()

    # Optional Timeseries_selection: when the filter file declares it, only
    # TS_<NAME> folders whose name appears in the enabled list are processed.
    # If the column is absent (older filter file) or empty, fall back to "all".
    if 'Timeseries' in unique_values_concatenated.columns:
        enabled_ts = set(str(v) for v in unique_values_concatenated['Timeseries'].dropna().unique())
    else:
        enabled_ts = None

    for subdir in os.listdir(timeseries_dir):
        if enabled_ts is not None and subdir not in enabled_ts:
            if debugging_output:
                print(f"Skipping timeseries (filter disabled): {subdir}")
            continue
        
        subdir_path = os.path.join(timeseries_dir, subdir)
        if os.path.isdir(subdir_path):
            csv_file = next((f for f in os.listdir(subdir_path) if f.endswith('.csv')), None)
            if csv_file:
                csv_path = os.path.join(subdir_path, csv_file)

                if debugging_output == True:
                    print("File being processed:" + csv_path)

                # Assuming the headers are in the second row (index 1)
                df = pd.read_csv(csv_path, header=1)

                scenario_subdir_path = os.path.join(subdir_path, scenario_option)
                if os.path.exists(scenario_subdir_path) and os.path.isdir(scenario_subdir_path):
                    scenario_csv_file = next((f for f in os.listdir(scenario_subdir_path) if f.endswith('.csv')), None)
                    if scenario_csv_file:
                        scenario_csv_path = os.path.join(scenario_subdir_path, scenario_csv_file)
                        df_scenario = pd.read_csv(scenario_csv_path, header=1)

                        # Identify common columns excluding 'Value'
                        common_cols = [col for col in df.columns if col in df_scenario.columns and col != 'Value']

                        # Merge on column 'HOUR'
                        df = df.merge(df_scenario, on='HOUR', how='left', suffixes=('', '_updated'))
                        for col in common_cols:
                            if col != 'HOUR':
                                col_updated = col+'_updated'
                                df[col] = df[col_updated].combine_first(df[col])
                                df.drop(col_updated, axis=1, inplace=True)
                        overwritten_data_info.append(subdir)

                        data_overwritten = True

                # Weather-year override: TS_<NAME>/<weather_year>/ holds a re-run
                # of the SAME timeseries for another weather year (per-region
                # columns; regions missing there keep the base data). Applied on
                # top of the scenario override.
                if weather_year and str(weather_year) != 'base':
                    wy_dir = os.path.join(subdir_path, str(weather_year))
                    if os.path.isdir(wy_dir):
                        wy_csv = next((f for f in os.listdir(wy_dir) if f.endswith('.csv')), None)
                        if wy_csv:
                            df = _merge_override(df, os.path.join(wy_dir, wy_csv))
                            overwritten_data_info.append(f"{subdir} (weather year {weather_year})")

                # List of columns to include
                columns_to_include = ['HOUR'] + [region for region in unique_regions if region in df.columns]
                
                # Create the filtered DataFrame
                df_filtered = df[columns_to_include].copy()
                    
                filtered_data[subdir] = df_filtered

    return filtered_data, "\n".join(overwritten_data_info)
