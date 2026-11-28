# MAVERICK evaluation harness — Revision R1 (release v2.1.1)

This folder is the revision-stage update of the MAVERICK simulation harness
prepared in response to the IEEE Systems Journal review of manuscript
ISJ-RE-26-22934. It is intended to be added to the repository
`HemanthMChakravarthy/MAVERICK_eval_harness` as the top-level folder
`R1_MAVERICK_eval_harness/` and tagged `v2.1.1`. **No LLM is invoked anywhere.**

## What changed relative to v1.x

| Reviewer concern | What v2.0 adds |
|---|---|
| Separate "mechanism works as designed" from "performance improves" | `tests/test_mechanisms.py` (16 deterministic checks) and `mechanism_matrix.csv`: an executable ledger (I1–I11 as graph queries, metadata-inclusive SHA-256 revision chain with local history verification, suspect propagation) is mutated by each fault class and the invariant verdicts are *computed*, not sampled. |
| Results depend on author-chosen parameters | Global uncertainty analysis (`gua_points.csv`): 16 behavioural parameters varied jointly by Latin-hypercube sampling (256 points × 100 seeds × 10 configurations), win-rates and PRCC sensitivity indices. Outcomes that never vary are classified as *enforced by construction*. |
| B2 is not MetaGPT | B2 is relabelled a negative control. Three new **mechanism emulations** (B6 SOP/structured-document MAS, MetaGPT-like; B7 chat-chain with reviewer and dehallucination, ChatDev-like; B8 conversable agents with human-in-the-loop by the prompting engineer, AutoGen-like) model the published handoff/validation mechanisms. They are *not* executions of those frameworks. |
| B4 retries unexplained | Retries are now counted per rework iteration **and by source** (`r_invariant`, `r_critic`, `r_test`, `r_human`, `r_llm_review`, `r_release`, `r_self`). A test asserts that B4's advisory invariant findings never trigger rework. |
| B5 recall fixed at 0.85 | `audit_sweep.csv`: audit recall 0.50–0.99; "field escapes" (escapes not found by the audit) reported separately from gate-pipeline leakage. |

## Reproduce

```bash
python -m maverick_r1.experiments --out results_r1      # full run; GUA is computationally intensive
python -m maverick_r1.figures results_r1
python -c "import tests.test_mechanisms as T; [getattr(T,n)() for n in dir(T) if n.startswith('test_')]"
```
Requires Python ≥ 3.10, numpy, scipy, pandas, matplotlib (pytest optional).

## Outputs (`results_r1/`)
`table_main.json` (Table IV of the revised paper), `effect_sizes.json`,
`table_asild.json`, `effect_sizes_asild.json`, `equal_p.csv`, `corr_sweep.csv`,
`audit_sweep.csv`, `mechanism_matrix.csv`, `gua_points.csv`, `summary.json`
(break-even, GUA win-rates, PRCC, evidence classes), per-seed CSVs, figures.

## Relationship to earlier numbers
v2.0 replaced the v1.x flag-based detection with an executable ledger. v2.1.x
corrects the rework semantics and random-number design (see `CHANGELOG_R1_1.md`),
so **v2.0 numbers must not be reused**. The revised manuscript reports v2.1.1
numbers throughout, including the full 256-point x 100-seed GUA (`gua_points.csv`,
`summary.json`), regenerated in about 7 minutes on one CPU core.

## Environment
See `requirements.txt` (versions used for the published outputs) and the
`environment` and `gua_design` records in `summary.json`.

## Scope (read before citing)
No LLM, human reviewer, or external agent framework is executed. Structural
detection (Type A) is computed on executable graph mutations; semantic and
link-integrity faults are marker mutations whose detection is sampled from
assumed probabilities. B6-B8 are mechanism emulations inspired by published
approaches, not executable reproductions or benchmark results of those
frameworks. The local ledger history is hash-linked and verified locally; it is
not a signed or externally anchored audit log. Effort figures are outputs of
assumed minutes per artifact (LLM drafting factor 0.05). GUA ranges are
plausible modelling ranges, not empirically calibrated distributions.
