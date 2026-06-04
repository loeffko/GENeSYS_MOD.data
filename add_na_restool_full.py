# -*- coding: utf-8 -*-
"""Integrate NA_restool outputs into the GENeSYS-MOD data CSVs (full).

Sequence:
  1) Timeseries  (see add_na_restool_timeseries.py)
  2) Capacity bounds + RES potentials (NA_inputs/add_capacity_bounds.py).
     This step replaces the old add_na_restool_potentials.py — the guardrail
     funnel and restool potential live in the same script to avoid overlap.

Use add_na_restool_timeseries.py or NA_inputs/add_capacity_bounds.py directly
when only one half needs refreshing.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import add_na_restool_timeseries as ts


def main():
    ts.main()
    print()
    print("=== Capacity bounds + RES potentials (merged) ===")
    subprocess.check_call([sys.executable,
                           os.path.join(HERE, "NA_inputs", "add_capacity_bounds.py"),
                           "--apply"])


if __name__ == "__main__":
    main()
    print("\nDone (full).")
