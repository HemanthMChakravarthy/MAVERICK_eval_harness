# MAVERICK Evaluation Harness v3 — Revision R0

A runnable, deterministic simulation harness for the **MAVERICK** research paper:
*multi-agent LLM orchestration covering ASPICE SWE.1–SWE.6 in a safety-supervised pipeline*.

This implementation is stored in `R0_MAVERICK_eval_harness/`. Run commands below from this directory.

It compares the full MAVERICK pipeline against baselines and ablations on synthetic automotive worked examples, measuring traceability completeness, seeded-defect leakage, structural coverage, and human review effort.

> **This is a simulation, not a measurement.** The default backend (`SimulatedLLM`) does not call any LLM. Artifact-level outcomes (defect injection, critic/reviewer performance) are produced by seeded RNGs under documented modelling assumptions. Numbers produced here support *architectural* claims, not empirical claims about any real model.

## Quick start

```bash
cd R0_MAVERICK_eval_harness
pip install -r requirements.txt
python run.py --quick
python run.py --seeds 500 --out results
python run.py --sweep
python run.py --asild
pytest tests/
```

Results land in `R0_MAVERICK_eval_harness/results/`: `report.md`, `sweep.md`, `asild.md`, `ASSUMPTIONS.md`, CSVs, and `figures/*.png`.

## Relationship to Revision R1

The revised implementation is maintained separately in [`../R1_MAVERICK_eval_harness/`](../R1_MAVERICK_eval_harness/). R1 has its own README, package, tests, and result directory.

## Repository layout

```text
R0_MAVERICK_eval_harness/
├── maverick/
│   ├── ledger.py
│   ├── invariants.py
│   ├── gates.py
│   ├── faults.py
│   ├── case_study.py
│   ├── agents.py
│   ├── configs.py
│   ├── metrics.py
│   ├── experiment.py
│   ├── stats.py
│   └── report.py
├── run.py
├── requirements.txt
├── results/
└── tests/
```

## Configurations

| ID | Pipeline | Key behavioral difference |
|----|----------|---------------------------|
| B0 | Manual baseline | Rare slips, near-perfect review, 2.5× effort, full manual traceability |
| B1 | Single LLM agent | Correlated cross-step defects, self-review possible, no checks |
| B2 | Unsupervised multi-agent, shared pool | Defect amplification downstream, no checks |
| B3 | Human + ALM link checks | Humans author; ALM catches missing links only |
| B4 | LLM + advisory invariant checks | Advisory findings trigger rework but do not block |
| B5 | LLM + post-hoc audit | Audit finds issues but cannot block |
| M | Full MAVERICK | Ledger + policy + critic + enforced human gates + coverage |
| M-noledger | M minus ledger protocol | Structural defects rely on policy and humans |
| M-nocritic | M minus critic | Semantic defects rely on humans, coverage, and tests |
| M-nopolicy | M minus policy | Negative control |

## Acceptance

```bash
cd R0_MAVERICK_eval_harness
python run.py --quick
pytest tests/
```

The quick run completes end-to-end and writes `results/report.md`, tables, and figures. Default mode makes no network calls.
