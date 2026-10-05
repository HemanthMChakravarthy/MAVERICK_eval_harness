# MAVERICK Evaluation Harness v3

A runnable, deterministic simulation harness for the **MAVERICK** research paper:
*multi-agent LLM orchestration covering ASPICE SWE.1–SWE.6 in a safety-supervised pipeline*.

It compares the full MAVERICK pipeline against baselines and ablations on synthetic
automotive worked examples, measuring traceability completeness, seeded-defect leakage,
structural coverage, and human review effort.

> **This is a simulation, not a measurement.** The default backend (`SimulatedLLM`)
> does not call any LLM. Artifact-level outcomes (defect injection, critic/reviewer
> performance) are produced by seeded RNGs under documented modelling assumptions.
> Numbers produced here support *architectural* claims (which mechanisms catch which
> defect classes), not empirical claims about any real model.

## Quick start

```bash
pip install -r requirements.txt
python run.py --quick        # smoke: configs B2 x M, 3 seeds
python run.py --seeds 12 --out results   # full: 10 configs x 12 seeds (AEB fixture)
python run.py --sweep        # one-way sensitivity sweeps + break-even (M-full, 6 seeds)
python run.py --asild        # ASIL-D fixture: M, B0, M-nopolicy x 12 seeds
pytest tests/                # unit + smoke tests
```

Results land in `results/`: `report.md`, `sweep.md`, `asild.md`, `ASSUMPTIONS.md`,
CSVs, `figures/*.png`.

## What is simulated

One run = one `(config, fixture, seed)` tuple, fully deterministic. Gates H1–H6
execute in order; at each gate the role agent produces its artifacts from the
worked-example templates, seeded defects from the 15-class catalog may be injected,
and the configuration's mechanisms engage:

1. **Deterministic checks** — ledger invariant checks (I1–I11) pre-promotion,
   ALM-style link-existence subset (B3), and the supervisor's static policy checks,
   with bounded retry (k=3; k=5 on the ASIL-D fixture) then human escalation.
2. **LLM critic** — behavioral model (calibrated recall / false-positive rate,
   optional correlated failure with the generator) reviewing semantic and
   link-integrity defects; all findings are dispositioned.
3. **Human approval** — different-person rule (approver ≠ author), calibrated catch
   rates degraded by alert fatigue (critic false alarms), and the ASIL-indexed
   verification method from Tables III/IV, which scales effort and catch rate.
4. **Promotion** — `promote(E) = Inv(E) ∧ Cov(E,a) ∧ findings-dispositioned ∧ Approve(E,a)`.
5. **Gate extras** — omission handling via gate completeness review, structural coverage
   (H4: statement/branch/MC-DC; H5: function/call), a seeded requirement-change scenario
   with transitive `suspect` propagation (H5), failing-test root-cause (I11: a failing
   verification test finds the escaped defect in the tested artifact), post-hoc audit
   (B5), advisory post-checks (B4), and H6 ledger-closure confirmation measures
   (TC == 1, all baselined, no suspect, chain intact).

## Repository layout

```
maverick/
  ledger.py       handoff envelope E, SHA-256 hash chain, typed link graph,
                  status lifecycle, suspect propagation, consumable()
  invariants.py   I1–I11 as deterministic graph queries (deduplicated), TC metric
  gates.py        H1–H6 gate specs as data: per-ASIL methods, coverage targets,
                  METHOD_RIGOR calibration, promote() decision rule
  faults.py       15-class seeded defect catalog (6 structural + 6 semantic +
                  3 link-integrity: W1/W2/R1, invisible to existence checks)
  case_study.py   SYNTHETIC worked-example fixtures: AEB (ASIL-B/QM) and
                  ASIL-D steering-torque arbitration
  agents.py       role agents; SimulatedLLM backend; SafetySupervisor
                  (policy + ASIL method tables + H6 closure); LLMCritic
                  (recall/fp/correlated-failure); HumanReviewer
  configs.py      B0-B5, M, M-noledger, M-nocritic, M-nopolicy (+notes)
  metrics.py      reviewer-minutes + authoring-minutes models, deterministic
                  coverage stub (rigor-explained config variation)
  experiment.py   (config, fixture, seed) orchestration; RunResult records
  stats.py        bootstrap CIs, Wilcoxon signed-rank, Cliff's delta, Holm
  report.py       aggregates, CSVs, figures, report.md / sweep.md / asild.md /
                  ASSUMPTIONS.md — all read from computed results
run.py            CLI (full 12-seed mode, --sweep, --asild, --quick)
tests/test_smoke.py
```

## Configurations

| ID | Pipeline | Key behavioral difference (assumption) |
|----|----------|----------------------------------------|
| B0 | Manual baseline | Rare slips, near-perfect review, 2.5× effort, full manual traceability |
| B1 | Single LLM agent | Correlated cross-step defects, self-review possible, no checks |
| B2 | Unsupervised multi-agent, shared pool | Defect amplification downstream, no checks |
| B3 | Human + ALM link checks | Humans author; ALM catches missing links only (never W1/W2/R1) |
| B4 | LLM + advisory invariant checks | Post-checks are non-blocking; findings triaged, nothing reworked |
| B5 | LLM + post-hoc audit | Audit finds (recall 0.85) but cannot block; found issues cost rework |
| M | Full MAVERICK | Ledger + policy + critic + enforced human gates + coverage |
| M-noledger | M minus ledger protocol | Structural defects leak (policy subset + humans only) |
| M-nocritic | M minus critic | Semantic defects rely on humans/coverage/tests |
| M-nopolicy | M minus policy | Negative control (ledger already covers the subset) |

See `configs.py` `notes` and `results/ASSUMPTIONS.md` for the full assumption register.

## Assumptions and limitations (read before citing numbers)

- **No real LLMs by default.** `SimulatedLLM` injects catalog defects with configured
  probabilities; it generates artifact-level outcomes, not language.
- **Behavioral, not empirical, parameters.** Injection rates, critic recall (0.70),
  human catch rates, reviewer-minute distributions, authoring costs, alert-fatigue
  slope, and `METHOD_RIGOR` are modelling assumptions chosen to be plausible and
  mechanism-revealing — not measurements.
- **Structural defects are deterministically catchable by design** — except the
  link-integrity classes (W1/W2/R1), which were added precisely to break the old
  "faults map 1:1 to invariants" circularity: they are invisible to I1/I4/I7 and
  to ALM-style checks.
- **Synthetic fixtures.** Both worked examples are hand-built and illustrative,
  not derived from any real product. In the paper they are "worked examples",
  never "case studies".
- **Coverage is a stub with explained variation.** Achieved coverage depends on the
  configuration's verification rigor (documented assumption); RQ3 reports achieved
  vs ASIL-indexed target honestly.
- **Small-n statistics.** Full mode uses 12 seeds; treat CIs, Wilcoxon/Holm, and
  Cliff's delta as simulation-sensitivity indicators. Cliff's delta is the primary
  effect size at n=12.

## Plugging in a real LLM later (optional, not built)

The harness is simulation-only by design. If you later want live model calls,
implement the `Backend` protocol in `maverick/agents.py` (one method:
`produce(req, rng) -> ProductionResult`) and inject it in `Experiment`;
keep provenance logging (prompt, response, model, seed) so runs stay auditable.
No such backend ships with v3 and none is needed to reproduce these results.

## Acceptance

- `python run.py --quick` completes end-to-end and writes `results/report.md` + tables + figures.
- `pytest tests/` passes.
- Deterministic given (config, fixture, seed); no network calls in default mode.
