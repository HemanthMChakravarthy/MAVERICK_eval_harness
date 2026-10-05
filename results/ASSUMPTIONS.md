# ASSUMPTIONS.md -- documented assumption register

Every number in `report.md` / `sweep.md` / `asild.md` comes from the actual
simulation run. This file documents the modelling assumptions the simulation
rests on. Nothing here is a measurement of a real LLM, a real reviewer, or a
real project.

## Simulation scope

- **Seeded behavioral simulation.** `SimulatedLLM` does not generate
  language; it generates artifact-level outcomes (defect injection with
  per-configuration probabilities). Deterministic given (config, fixture,
  seed). No network calls.
- **Worked examples, not case studies.** Both fixtures (AEB pedestrian
  post-processing, ASIL-B/QM; steering-torque arbitration, ASIL-D) are
  synthetic and illustrative, hand-built for the simulation. Not derived
  from any real product or requirements document.

## Defect model (`faults.py`)

- 15 seeded defect classes: 6 structural (S1-S6), 6 semantic (M1-M6),
  3 link-integrity (W1 wrong-target link, W2 spurious link, R1 hallucinated
  rationale).
- W1/W2/R1 are **invisible to link-existence invariants** (I1/I4/I7) and to
  ALM-style link checks by construction: the links exist and are type-valid.
  Only the critic (probabilistically) or human review can catch them. This
  breaks the "faults map 1:1 to invariants" circularity.
- `detectable_by` declares which mechanism *can* catch each defect; it is a
  modelling choice, not an empirical claim.

## Agent / reviewer / critic behavior (`agents.py`, `configs.py`)

- Per-defect injection probability `inject_p`: 0.75 (LLM pipelines),
  0.45 (B4/B5, lighter prompting assumed), 0.15 (B3 human authoring),
  0.05 (B0 manual).
- Critic: recall 0.70, false-positive rate 0.10 per artifact (assumed
  operating point; precision is emergent and reported).
- Human review catch: 0.90 structural / 0.85 semantic (M-family, B3-B5);
  0.99 (B0 optimistic); 0.40/0.25 (B1 cursory); 0.50/0.35 (B2).
- **Alert fatigue**: effective human recall is multiplied by
  `(1 - 0.3 * false_alarm_rate)` where the false-alarm rate is the critic's
  accumulated FP findings per review. Slope 0.3 is an assumption.
- **Correlated failure** (`corr_p`): with probability `corr_p` the critic
  misses a defect *together with* the generator (shared blind spot),
  regardless of recall. Default 0.0; swept at {0, 0.2, 0.5}.
- Retry budget k=3 (k=5 on the ASIL-D fixture); escalation costs 45
  reviewer-minutes; audit rework 45 minutes.

## Effort model (`metrics.py`)

- Reviewer minutes: lognormal around base minutes per (artifact type x ASIL),
  scaled by configuration `effort_scale` (B0 2.5x, M-family 1.0x, B3 1.0x,
  B4 0.5x, B5 0.3x, B1 0.5x, B2 0.6x).
- **Authoring minutes**: new in v3. Human authoring (B0/B3) charged at full
  base authoring minutes; LLM drafting (all others) at 0.05x. Base values
  (e.g. SwReq 120, SwUnit 240) are plausible magnitudes, not measurements.
- B4 advisory findings: 5 minutes triage each, no rework. B5 audit:
  10 minutes per artifact + 45 per found issue; audit recall 0.85
  (inspired by Sameh & Elbanna 2026's 85% manual-effort reduction, but that
  figure is *effort reduction*, not detection recall -- the 0.85 recall used
  here is an assumption).

## Coverage stub (`metrics.py`)

- Achieved coverage = f(deterministic unit hash, pipeline **rigor**,
  defect presence). Rigor per configuration (M-full 1.0 ... B2 0.2) is a
  documented assumption: a pipeline that skips verification *measures*
  lower coverage. This is why the stub varies by configuration -- the
  variation is *explained*, not noise.
- RQ3 is reported honestly: achieved minimum branch coverage vs the
  ASIL-indexed target (100% for ASIL B/D at H4).

## Baselines B3/B4/B5 (`configs.py`)

- **B3 (human+ALM)**: `alm_checks` catch missing links/artifacts
  deterministically (S1/S2/S3/S5/S6/M3) but never W1/W2/R1 or ASIL faults.
- **B4 (LLM+advisory)**: invariant checks run post-promotion as
  non-blocking findings; nothing is reworked or blocked.
- **B5 (LLM+audit)**: post-hoc audit finds escaped defects (recall 0.85)
  but cannot block; found defects still count as gate-pipeline escapes
  (`leaked=True`).

## Statistics

- n=12 seeds (main comparison), 6 seeds (sweeps). Bootstrap 95% CIs,
  Wilcoxon signed-rank (Holm-adjusted) *and* Cliff's delta (matched-pairs
  rank-biserial) -- the delta is the primary effect size at n=12.
- Leakage: pooled (total escaped / total injected) for headlines;
  per-seed rates (NaN seeds excluded) for CIs and paired tests.
