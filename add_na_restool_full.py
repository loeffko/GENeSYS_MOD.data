# -*- coding: utf-8 -*-
"""Integrate NA_restool outputs into the GENeSYS-MOD data CSVs (full).

Runs both halves of the integration sequentially:
  1) Timeseries  (see add_na_restool_timeseries.py)
  2) Potentials  (see add_na_restool_potentials.py)

Use the split scripts directly when only one half needs refreshing.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import add_na_restool_timeseries as ts
import add_na_restool_potentials as pot


def main():
    ts.main()
    print()
    pot.main()


if __name__ == "__main__":
    main()
    print("\nDone (full).")
