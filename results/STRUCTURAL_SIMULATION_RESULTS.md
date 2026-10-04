# MAVERICK structural simulation results

**Execution date:** 2026-10-03  
**Runner:** `run_structural_experiment.py`  
**Raw trials:** `structural_fault_runs.csv`  
**Machine-readable summary:** `structural_summary.json`

## Measured result

A fixed synthetic traceability ledger representing a camera-based pedestrian-detection post-processing and plausibility function contained 34 typed SWE.1–SWE.6 artifacts. The clean ledger had no C1–C6 violations and traceability completeness (TC) of 1.000. The harness also exercised 12 successful clean gate promotions (six H1 requirement gates and six H4 unit gates).

Across 600 deterministic structural-fault injections (100 repetitions for each of six fault types), the invariant layer detected all injected faults: 600/600 detections, a 0.0% leakage rate. Each of the following catalog classes achieved a 100% detection rate: removed parent link, wrong ASIL, removed qualification test, orphaned unit, removed allocation, and dangling link. The mean TC after injecting one fault was 0.9655, and the mean violation count was 1.3333.

## Scope constraint

These are **preliminary structural-simulation measurements**, not a completed end-to-end LLM/automotive case study. The supplied repository contains no frozen industrial requirements, LLM integration, generated code, coverage report, human-review logs, NASA-TLX data, semantic-fault executions, baselines, or assessor ratings. Consequently, this run does **not** measure MC/DC or branch coverage, review effort, ASPICE ratings, LLM artifact quality, or comparative results against B0/B1/B2 and the ablations. Those cells must remain reported as not measured rather than inferred.
