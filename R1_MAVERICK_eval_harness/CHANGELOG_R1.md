# v2.1.1 — review of the R1.1 corrections

Accepted all R1.1 corrections and made four further changes:
- **Deterministic checks hold the release.** An unresolved violation detected by a
  deterministic blocking check (ledger invariant, or ALM existence check in B3) is
  re-evaluated at the release gate, so the release is withheld (`held`,
  `release_held`) instead of the defect escaping. R1.1 let such a defect proceed and
  escape, which contradicts the H6 acceptance rule of the architecture being
  modelled. Unresolved critic, review, and test findings still proceed and may
  escape (conservative). Held releases are reported separately; they are neither
  containment nor escapes. Observed rate: 0 at base values, at most 1% of runs at
  any GUA point.
- **Common random numbers across configurations.** Detection, repair, and
  escalation streams are keyed by a stable layer identifier (`LAYER_ID`) rather
  than the position of the layer in a configuration's list, so the same control
  draws the same uniform for the same fault in every configuration.
- **`p_fix_escalation` is varied in the GUA** (0.80–0.99) instead of being fixed;
  the GUA now covers 16 parameters.
- **Full GUA re-run** (256 points x 100 seeds x 10 configurations) and all
  outputs/figures regenerated; `summary.json` records the GUA design, software
  versions and harness version; `requirements.txt` pins versions.
- Two regression tests added (16 total): repair probability does not shift
  detection draws (paired seeds, three configurations); an unresolved invariant
  violation holds the release and is never released.

Effect of the RNG correction: the PRCC of `p_fix_llm` with M leakage fell from
-0.06 (v2.0) to -0.01, and B5 gate leakage now equals B4 exactly (the audit
cannot block, so the two differ only in effort and post-audit field escapes).

# v2.1.0 — R1.1 corrective implementation

This release corrects simulation and ledger issues identified during the R1 code audit. It changes model semantics and therefore invalidates the previous R1 headline results.

## Behavioural simulation
- Failed bounded rework no longer automatically removes a defect from the release population.
- A separate human-escalation resolution event is modelled with `p_fix_escalation` (default 0.95). If escalation also fails, the defect remains residual and can still be detected by later controls.
- Random draws are separated by event stream; detection and repair draws are keyed by seed, fault instance, and layer. Retry counts no longer shift random draws for subsequent fault detection events.
- Output now reports escalation resolutions and unresolved detection events.

## Evidence ledger
- Canonical artifact hashes now include ID, type, ASIL, kind, payload, links, version, and previous hash.
- A local immutable revision-snapshot history is retained and checked by `chain_ok`. This is not a signed or externally anchored tamper-proof audit log.
- Result traceability requires a supported test-artifact target type.
- Missing or invalid test verdicts fail closed under I11.

## Tests and regenerated results
- Expanded mechanism/regression suite: 14 tests.
- Main AEB and ASIL-D per-seed experiment outputs were regenerated with 500 seeds per configuration.
- GUA was regenerated as a 24-point × 30-seed exploratory run due execution-time constraints. It is explicitly not a replacement for the manuscript's 256-point × 100-seed analysis.
- Figures were regenerated from the corrected main results and exploratory GUA.
- Do not reuse the original R1 headline results or claim the original GUA robustness percentages from this release. Re-run the full GUA before updating manuscript numerical claims.

# v2.0.0 (revision R1)
- Executable Traceability Ledger (I1–I11, hash chain, suspect propagation) replaces flag-based detection.
- New mechanism-emulation baselines B6 (SOP/structured-document MAS), B7 (chat chain), B8 (conversable agents + HIL).
- B2 relabelled negative control; B4/B5 definitions made explicit.
- Retry accounting per rework iteration and by source; advisory findings proven not to trigger rework.
- Post-hoc audit recall sweep with field-escape metric.
- Global uncertainty analysis (LHS, 15 parameters, PRCC) and evidence classification.
- Mechanism-verification test suite (10 tests).
