# MAVERICK evaluation harness — Revision R1 (v2.0)

This folder is the revision-stage update of the MAVERICK simulation harness
prepared in response to the IEEE Systems Journal review of manuscript
ISJ-RE-26-22934. It is intended to be added to the repository
`HemanthMChakravarthy/MAVERICK_eval_harness` as a new top-level folder
(`revision_r1/`) and tagged `v2.0`. **No LLM is invoked anywhere.**

## What changed relative to v1.x

| Reviewer concern | What v2.0 adds |
|---|---|
| Separate "mechanism works as designed" from "performance improves" | `tests/test_mechanisms.py` (10 deterministic checks) and `mechanism_matrix.csv`: an executable ledger (I1–I11 as graph queries, SHA-256 hash chain, suspect propagation) is mutated by each fault class and the invariant verdicts are *computed*, not sampled. |
| Results depend on author-chosen parameters | Global uncertainty analysis (`gua_points.csv`): 15 behavioural parameters varied jointly by Latin-hypercube sampling (256 points × 100 seeds × 10 configurations), win-rates and PRCC sensitivity indices. Outcomes that never vary are classified as *enforced by construction*. |
| B2 is not MetaGPT | B2 is relabelled a negative control. Three new **mechanism emulations** (B6 SOP/structured-document MAS, MetaGPT-like; B7 chat-chain with reviewer and dehallucination, ChatDev-like; B8 conversable agents with human-in-the-loop by the prompting engineer, AutoGen-like) model the published handoff/validation mechanisms. They are *not* executions of those frameworks. |
| B4 retries unexplained | Retries are now counted per rework iteration **and by source** (`r_invariant`, `r_critic`, `r_test`, `r_human`, `r_llm_review`, `r_release`, `r_self`). A test asserts that B4's advisory invariant findings never trigger rework. |
| B5 recall fixed at 0.85 | `audit_sweep.csv`: audit recall 0.50–0.99; "field escapes" (escapes not found by the audit) reported separately from gate-pipeline leakage. |

## Reproduce

```bash
python -m maverick_r1.experiments --out results_r1      # ~90 s on a laptop
python -m maverick_r1.figures results_r1
python -c "import tests.test_mechanisms as T; [getattr(T,n)() for n in dir(T) if n.startswith('test_')]"
```
Requires Python ≥ 3.10, numpy, scipy, pandas, matplotlib (pytest optional).

## Outputs (`results_r1/`)
`table_main.json` (Table IV of the revised paper), `effect_sizes.json`,
`table_asild.json`, `effect_sizes_asild.json`, `equal_p.csv`, `corr_sweep.csv`,
`audit_sweep.csv`, `mechanism_matrix.csv`, `gua_points.csv`, `summary.json`
(break-even, GUA win-rates, PRCC, evidence classes), per-seed CSVs, figures.

## Relationship to v1.x numbers
v2.0 is a clean re-implementation of the behavioural model documented in
Section V of the manuscript, with an executable ledger replacing flag-based
detection and with explicit definitions for every baseline. Headline values
moved modestly (e.g., M pooled leakage 2.0 % → 2.9 %; escape-fraction ratio
vs. B3 3.8× → 3.9×; retries are now counted per rework iteration). The
revised manuscript reports v2.0 numbers throughout. See `ASSUMPTIONS_R1.md`.
