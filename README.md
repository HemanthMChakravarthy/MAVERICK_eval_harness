# MAVERICK Evaluation Harness

This repository contains two revision folders for the MAVERICK evaluation harness:

- [`R0_MAVERICK_eval_harness/`](R0_MAVERICK_eval_harness/) — initial/legacy implementation.
- [`R1_MAVERICK_eval_harness/`](R1_MAVERICK_eval_harness/) — revised implementation prepared for the IEEE Systems Journal review.

> **These are simulations, not measurements.** The default backends do not call real LLMs. Their artifact-level outcomes are generated from seeded random models under documented assumptions.

## Revision R0

The initial implementation is in [`R0_MAVERICK_eval_harness/`](R0_MAVERICK_eval_harness/). It provides the v3 harness for the MAVERICK pipeline, baselines, ablations, and ASIL-D comparison.

```bash
cd R0_MAVERICK_eval_harness
pip install -r requirements.txt
python run.py --quick
pytest tests/
```

R0 results are written to `R0_MAVERICK_eval_harness/results/`. See [`R0_MAVERICK_eval_harness/README.md`](R0_MAVERICK_eval_harness/README.md) for full documentation.

## Revision R1

The revised implementation is in [`R1_MAVERICK_eval_harness/`](R1_MAVERICK_eval_harness/). It includes executable ledger mechanisms, mechanism-emulation baselines, sensitivity sweeps, global uncertainty analysis, and a mechanism-verification test suite.

```bash
cd R1_MAVERICK_eval_harness
python -m maverick.experiments --out results
python -m maverick.figures results
python -c "import tests.test_mechanisms as T; [getattr(T,n)() for n in dir(T) if n.startswith('test_')]"
```

R1 results are written to `R1_MAVERICK_eval_harness/results/`. See:

- [`R1_MAVERICK_eval_harness/README_R1.md`](R1_MAVERICK_eval_harness/README_R1.md)
- [`R1_MAVERICK_eval_harness/ASSUMPTIONS_R1.md`](R1_MAVERICK_eval_harness/ASSUMPTIONS_R1.md)
- [`R1_MAVERICK_eval_harness/CHANGELOG_R1.md`](R1_MAVERICK_eval_harness/CHANGELOG_R1.md)

## Working from the repository root

Do not execute the R0 or R1 entry points from the repository root unless you first change directory into the corresponding revision folder.
