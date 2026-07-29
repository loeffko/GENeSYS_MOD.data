# -*- coding: utf-8 -*-
"""Meta-runner for the NA private-data refresh.

Runs exactly the scripts that consume the anonymized/private NA input files
and therefore must be re-run on every machine after those inputs change.
One-time migration scripts (power split, EGS, restool, ramping, ...) are
deliberately NOT part of this chain.

    python run_na_pipeline.py            # dry-run (skips scripts without one)
    python run_na_pipeline.py --apply    # write

Chain (order matters, enforce_max_ge_min must be last):
  1. NA_inputs/add_capacity_bounds.py     residuals + min/max funnels + potentials
  2. NA_inputs/add_offshore_wind_bounds.py offshore wind caps
  3. NA_inputs/add_trade_capacity.py      pool interconnection trade capacities
  4. NA_inputs/add_ic_trade_bounds.py     IC AnnualMin/MaxTradeCapacity bounds + trade cost
  5. NA_inputs/convert_fel_to_demand.py   FEL workbook -> Power_* annual demand
  6. enforce_max_ge_min.py                final max >= min invariant sweep

Any non-zero exit aborts the chain so later scripts never run on
half-written data.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APPLY = "--apply" in sys.argv

# (script, supports_dry_run). Scripts without --apply support write
# unconditionally when executed — in dry-run mode they are SKIPPED, not run.
SCRIPTS = [
    (os.path.join("NA_inputs", "add_capacity_bounds.py"), True),
    (os.path.join("NA_inputs", "add_offshore_wind_bounds.py"), True),
    (os.path.join("NA_inputs", "add_trade_capacity.py"), True),
    (os.path.join("NA_inputs", "add_ic_trade_bounds.py"), True),
    (os.path.join("NA_inputs", "add_lcoe_costs.py"), True),
    (os.path.join("NA_inputs", "convert_fel_to_demand.py"), False),
    ("enforce_max_ge_min.py", True),
]

def main():
    print(f"NA data refresh ({'APPLY' if APPLY else 'DRY-RUN'}) — {len(SCRIPTS)} scripts\n")
    for i, (rel, dryable) in enumerate(SCRIPTS, 1):
        path = os.path.join(HERE, rel)
        if not os.path.exists(path):
            print(f"[{i}/{len(SCRIPTS)}] MISSING: {rel} — aborting.")
            sys.exit(1)
        if not APPLY and not dryable:
            print(f"[{i}/{len(SCRIPTS)}] {rel} — SKIPPED (no dry-run support; runs only with --apply)")
            continue
        mode = ["--apply"] if (APPLY and dryable) else []
        print(f"[{i}/{len(SCRIPTS)}] {rel} {' '.join(mode)}")
        r = subprocess.run([sys.executable, path, *mode], cwd=HERE)
        if r.returncode != 0:
            print(f"\nFAILED at {rel} (exit {r.returncode}) — chain aborted.")
            sys.exit(r.returncode)
        print()
    print("NA data refresh finished successfully.")

if __name__ == "__main__":
    main()
