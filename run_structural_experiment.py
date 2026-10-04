"""Run the reproducible MAVERICK structural-harness experiment.

This runner measures only what the supplied harness implements: typed traceability
invariants C1-C6, impact propagation, and detection of the six catalogued
structural faults. It is not an LLM, generated-code-coverage, human-review, or
ASPICE-assessment study. Its outputs must therefore be reported as preliminary
structural-simulation results, not as evidence for RQ3-RQ5.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from maverick.ledger import Envelope, Ledger
from maverick.seeding import CATALOG, detected, seed
from maverick.supervisor import Approval, SafetySupervisor


def build_perception_case() -> Ledger:
    """Construct a fixed, synthetic pedestrian-plausibility V-model ledger.

    The artifacts are deliberately synthetic but represent the artifact types and
    links used by SWE.1-SWE.6. A frozen, real project artifact set can replace this
    fixture without changing the evaluation loop.
    """
    ledger = Ledger()
    interfaces = ["ObjectList", "VehicleState", "PlausibilityDecision"]

    for index in range(6):
        ledger.put(
            Envelope(
                f"SYS-{index:02d}",
                "SysReq",
                1,
                "D",
                {"title": f"Pedestrian-plausibility system requirement {index}", "allocated_to_sw": True},
            )
        )

    ledger.put(
        Envelope(
            "ARC-01",
            "SwArch",
            1,
            "D",
            {"component": "Pedestrian plausibility post-processor"},
            interfaces=interfaces,
        )
    )

    for index in range(6):
        requirement_id = f"SWR-{index:02d}"
        unit_id = f"UNIT-{index:02d}"
        ledger.put(
            Envelope(
                requirement_id,
                "SwReq",
                1,
                "D",
                {
                    "title": f"Plausibility rule {index}",
                    "verification_criterion": "Boundary and nominal behavior verified",
                },
                links=[(f"SYS-{index:02d}", "derives-from"), ("ARC-01", "allocated-to")],
            )
        )
        ledger.put(
            Envelope(
                unit_id,
                "SwUnit",
                1,
                "D",
                {"component": f"plausibility_rule_{index}"},
                links=[("ARC-01", "implements")],
            )
        )
        ledger.put(
            Envelope(
                f"UT-{index:02d}",
                "UnitTest",
                1,
                "D",
                {"test": f"unit boundary test {index}"},
                links=[(unit_id, "verifies")],
            )
        )
        ledger.put(
            Envelope(
                f"QT-{index:02d}",
                "QualTest",
                1,
                "D",
                {"test": f"qualification scenario {index}"},
                links=[(requirement_id, "verifies")],
            )
        )

    for index, interface in enumerate(interfaces):
        ledger.put(
            Envelope(
                f"IT-{index:02d}",
                "IntTest",
                1,
                "D",
                {"interfaces": [interface], "test": f"integration test for {interface}"},
                links=[("ARC-01", "verifies")],
            )
        )
    return ledger


def promote_clean_artifacts(ledger: Ledger) -> int:
    """Exercise the H1/H4 promotion path and count successful gates."""
    supervisor = SafetySupervisor(ledger)
    gates = 0
    for requirement in ledger.of("SwReq"):
        ok, reasons = supervisor.promote(requirement, "H1", approval=Approval("reviewer-h1", 2))
        if not ok:
            raise RuntimeError(f"Clean H1 gate rejected {requirement.id}: {reasons}")
        gates += 1
    for unit in ledger.of("SwUnit"):
        ok, reasons = supervisor.promote(
            unit,
            "H4",
            coverage={"branch": 1.0, "mcdc": 1.0},
            approval=Approval("reviewer-h4", 1),
        )
        if not ok:
            raise RuntimeError(f"Clean H4 gate rejected {unit.id}: {reasons}")
        gates += 1
    return gates


def run(output_dir: Path, repetitions: int, seed_offset: int) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    pristine = build_perception_case()
    if pristine.violations():
        raise RuntimeError(f"Synthetic case ledger is invalid: {pristine.violations()}")
    gate_count = promote_clean_artifacts(pristine)

    rows: list[dict] = []
    per_fault = Counter()
    detected_by_fault = Counter()
    violation_counts: list[int] = []
    tc_values: list[float] = []

    for fault_index, fault in enumerate(CATALOG):
        for repetition in range(repetitions):
            run_seed = seed_offset + fault_index * repetitions + repetition
            import random
            faulted, target = seed(pristine, fault, random.Random(run_seed))
            was_detected = detected(faulted, target)
            violations = faulted.violations()
            row = {
                "fault": fault,
                "repetition": repetition + 1,
                "seed": run_seed,
                "target_artifact": target,
                "detected": was_detected,
                "leaked": not was_detected,
                "traceability_completeness": faulted.tc(),
                "violation_count": len(violations),
                "violations": json.dumps(violations),
            }
            rows.append(row)
            per_fault[fault] += 1
            detected_by_fault[fault] += int(was_detected)
            violation_counts.append(len(violations))
            tc_values.append(faulted.tc())

    with (output_dir / "structural_fault_runs.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    summary = {
        "experiment": "MAVERICK deterministic structural-harness experiment",
        "case_study": "Synthetic camera-based pedestrian-detection post-processing and plausibility function",
        "scope": ["C1-C6 invariants", "typed traceability", "structural fault catalog", "H1/H4 supervisor path"],
        "not_measured": ["LLM quality", "generated-code coverage", "semantic faults", "human review effort", "NASA-TLX", "ASPICE assessor ratings"],
        "synthetic_artifact_count": len(pristine.a),
        "successful_clean_gate_promotions": gate_count,
        "fault_catalog": CATALOG,
        "repetitions_per_fault": repetitions,
        "total_seeded_faults": len(rows),
        "detected_faults": int(sum(detected_by_fault.values())),
        "leaked_faults": int(sum(not row["detected"] for row in rows)),
        "structural_fault_leakage_rate": sum(not row["detected"] for row in rows) / len(rows),
        "per_fault_detection_rate": {fault: detected_by_fault[fault] / per_fault[fault] for fault in CATALOG},
        "mean_faulted_traceability_completeness": sum(tc_values) / len(tc_values),
        "mean_faulted_violation_count": sum(violation_counts) / len(violation_counts),
        "clean_ledger_tc": pristine.tc(),
        "clean_ledger_violations": pristine.violations(),
        "reproducibility": {"seed_offset": seed_offset, "python_standard_rng": "random.Random"},
    }
    (output_dir / "structural_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the MAVERICK structural simulation.")
    parser.add_argument("--repetitions", type=int, default=100, help="Fault injections per catalog class (default: 100).")
    parser.add_argument("--seed-offset", type=int, default=20261003, help="Deterministic seed offset.")
    parser.add_argument("--output-dir", type=Path, default=Path("results"), help="Directory for CSV and JSON outputs.")
    args = parser.parse_args()
    if args.repetitions < 1:
        parser.error("--repetitions must be positive")
    summary = run(args.output_dir, args.repetitions, args.seed_offset)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
