# MAVERICK evaluation harness — Revision R1 (v2.0)

This folder is the revision-stage update of the MAVERICK simulation harness prepared in response to the IEEE Systems Journal review of manuscript ISJ-RE-26-22934.

The implementation is located at:

```text
R1_MAVERICK_eval_harness/
├── maverick/
├── results/
├── tests/
├── README.md
├── ASSUMPTIONS_R1.md
└── CHANGELOG_R1.md
```

Run all commands in this directory. **No LLM is invoked anywhere.**

## What changed relative to R0

| Reviewer concern | What R1 adds |
|---|---|
| Separate mechanism correctness from performance improvement | `tests/test_mechanisms.py` and the mechanism verification matrix |
| Results depend on author-chosen parameters | Global uncertainty analysis over 15 behavioral parameters |
| Baseline definitions require clarification | Explicit mechanism-emulation baselines and relabelled negative controls |
| Retries are unexplained | Per-iteration retry accounting by source |
| Post-hoc audit recall is fixed | Audit recall sweep and separate field-escape reporting |

## Reproduce

```bash
cd R1_MAVERICK_eval_harness
python -m maverick.experiments --out results
python -m maverick.figures results
python -c "import tests.test_mechanisms as T; [getattr(T,n)() for n in dir(T) if n.startswith('test_')]"
```

The package name is `maverick`; it does not use the R1 folder name as a Python package name.

## Outputs

`R1_MAVERICK_eval_harness/results/` contains:

- `table_main.json`
- `effect_sizes.json`
- `table_asild.json`
- `effect_sizes_asild.json`
- `equal_p.csv`
- `corr_sweep.csv`
- `audit_sweep.csv`
- `mechanism_matrix.csv`
- `gua_points.csv`
- `summary.json`
- Per-seed CSV files
- `fig2_leakage.png` and `fig3_gua.png`

## Relationship to R0

R1 is a clean re-implementation of the behavioral model documented in the revised manuscript. It replaces R0's flag-based defect handling with an executable ledger, while making each baseline and mechanism explicit.

See [`ASSUMPTIONS_R1.md`](ASSUMPTIONS_R1.md) before interpreting the numbers.
