#!/usr/bin/env python3
"""MAVERICK evaluation harness v3 -- command-line driver.

Examples:
    python run.py --quick                 # smoke: B2 x M, 3 seeds
    python run.py                         # full: all configs x 12 seeds (AEB fixture)
    python run.py --seeds 12 --out results
    python run.py --sweep                 # one-way sensitivity sweeps (6 seeds)
    python run.py --asild                 # ASIL-D fixture: M-full and B0 (+M-nopolicy)
    python run.py --configs M B2 --seeds 0 1 2 --outdir results/my_run

Modes:
    main comparison : 10 configs x 12 seeds on the AEB (ASIL-B/QM) fixture
    --sweep         : one-way sensitivity sweeps on M-full, 6 seeds
    --asild         : ASIL-D steering-torque arbitration fixture

Default mode uses the SimulatedLLM backend and makes no network calls.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from maverick.configs import FULL_ORDER
from maverick.experiment import run_experiment
from maverick.report import (
    build_report,
    run_sensitivity_sweeps,
    run_asild_comparison,
)

QUICK_CONFIGS = ["B2", "M"]
QUICK_SEEDS = [0, 1, 2]
FULL_SEEDS = list(range(12))
SWEEP_SEEDS = list(range(6))
ASILD_CONFIGS = ["M", "B0", "M-nopolicy"]


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description="MAVERICK evaluation harness v3")
    ap.add_argument("--quick", action="store_true",
                    help="smoke run: B2 and M, 3 seeds")
    ap.add_argument("--configs", nargs="*", default=None,
                    help="config ids to run (default: all)")
    ap.add_argument("--seeds", nargs="*", default=None,
                    help="seeds to run: a single count N -> 0..N-1, or an explicit "
                         "list (default: 0..11, or 0..2 with --quick)")
    ap.add_argument("--outdir", "--out", default="results",
                    help="output directory for report, CSVs, figures")
    ap.add_argument("--sweep", action="store_true",
                    help="one-way sensitivity sweeps on M-full (6 seeds)")
    ap.add_argument("--asild", action="store_true",
                    help="ASIL-D fixture comparison (M, B0, M-nopolicy)")
    return ap.parse_args(argv)


def _parse_seeds(raw, quick: bool):
    if raw is None:
        return QUICK_SEEDS if quick else FULL_SEEDS
    vals = [int(v) for v in raw]
    if len(vals) == 1:
        return list(range(vals[0]))
    return vals


def _run_main(configs, seeds):
    print(f"MAVERICK_eval_harness v3: {len(configs)} configs x {len(seeds)} seeds")
    results = {}
    for cid in configs:
        runs = []
        for s in seeds:
            runs.append(run_experiment(cid, s))
            print(f"  [{cid}] seed {s}: "
                  f"TC={runs[-1].final_tc:.3f} "
                  f"leaked={runs[-1].n_leaked}/{runs[-1].n_injected} "
                  f"min={runs[-1].total_minutes:.0f}")
        results[cid] = runs
    return results


def main(argv=None) -> int:
    args = parse_args(argv)
    outdir = Path(args.outdir)

    if args.sweep:
        seeds = _parse_seeds(args.seeds, False) if args.seeds is not None else SWEEP_SEEDS
        print(f"sensitivity sweeps: M-full x {len(seeds)} seeds per setting")
        sweep_results = run_sensitivity_sweeps(seeds, outdir)
        print(f"\nSweep results written to {outdir / 'sweep.md'}")
        return 0

    if args.asild:
        seeds = _parse_seeds(args.seeds, False)
        configs = args.configs or ASILD_CONFIGS
        print(f"ASIL-D fixture: {len(configs)} configs x {len(seeds)} seeds")
        asild_results = {}
        for cid in configs:
            runs = [run_experiment(cid, s, fixture="asild") for s in seeds]
            asild_results[cid] = runs
            print(f"  [{cid}]: " +
                  ", ".join(f"TC={r.final_tc:.3f}" for r in runs[:3]) +
                  (" ..." if len(runs) > 3 else ""))
        run_asild_comparison(asild_results, outdir)
        print(f"\nASIL-D results written to {outdir / 'asild.md'}")
        return 0

    if args.configs:
        unknown = [c for c in args.configs if c not in FULL_ORDER]
        if unknown:
            print(f"unknown configs: {unknown} (choose from {FULL_ORDER})",
                  file=sys.stderr)
            return 2
        configs = args.configs
    else:
        configs = QUICK_CONFIGS if args.quick else FULL_ORDER
    seeds = _parse_seeds(args.seeds, args.quick)

    results = _run_main(configs, seeds)
    agg = build_report(results, outdir)

    print("\nHeadline results (mean over seeds):")
    print(f"{'config':<12}{'TC':>8}{'leakage':>10}{'viol':>8}{'minutes':>10}")
    for cid in configs:
        a = agg[cid]
        print(f"{cid:<12}{a['tc']['mean']:>8.3f}{a['leakage']['mean']:>10.3f}"
              f"{a['violations']['mean']:>8.1f}{a['minutes']['mean']:>10.0f}")
    print(f"\nReport written to {outdir / 'report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
