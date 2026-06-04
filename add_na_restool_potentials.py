# -*- coding: utf-8 -*-
"""DEPRECATED — RES potential writes are now folded into the capacity-bounds
script so guardrail funnel + restool potential do not overlap.

For PV / Wind / Rooftop maximum capacities the workflow is:

    python NA_inputs/add_capacity_bounds.py --apply

which writes Par_ResidualCapacity + Par_TotalAnnualMinCapacity +
Par_TotalAnnualMaxCapacity in one consistent pass — guardrail for 2025-2035
and linear interpolation from the 2035 funnel value to the per-region
NA_restool potential at 2040 (with every year 2025-2040 explicitly filled).
"""
import sys


MSG = (
    "DEPRECATED: this script no longer writes RES potentials. "
    "Run `python NA_inputs/add_capacity_bounds.py --apply` instead — "
    "PV / Wind / Rooftop / Offshore potentials are merged with the "
    "guardrail capacity bounds there.\n"
)


def main():
    sys.stderr.write(MSG)
    sys.exit(1)


if __name__ == "__main__":
    main()
