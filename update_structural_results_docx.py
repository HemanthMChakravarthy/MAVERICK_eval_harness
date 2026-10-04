"""Create a clearly labelled manuscript copy containing only measured structural-simulation results."""
from __future__ import annotations

import json
from pathlib import Path
from docx import Document

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT.parent / "MAVERICK_IEEE_TVT_Draft_v3.docx"
OUTPUT = ROOT.parent / "MAVERICK_IEEE_TVT_Draft_v3_structural_simulation_results.docx"
SUMMARY = ROOT / "results" / "structural_summary.json"


def replace_paragraph(paragraph, text: str) -> None:
    for run in paragraph.runs:
        run.text = ""
    paragraph.add_run(text)


def main() -> None:
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    document = Document(SOURCE)
    placeholders = [
        index for index, paragraph in enumerate(document.paragraphs)
        if paragraph.text.startswith("[AUTHORS’ NOTE — DO NOT SUBMIT WITH PLACEHOLDERS]")
    ]
    if len(placeholders) != 1:
        raise RuntimeError("Expected exactly one Results placeholder note.")
    start = placeholders[0]

    replace_paragraph(
        document.paragraphs[start],
        "Preliminary structural-simulation results. The supplied evaluation harness was executed on a fixed, "
        "synthetic traceability ledger for a camera-based pedestrian-detection post-processing and plausibility "
        "function. These results measure only the deterministic traceability-invariant and structural-fault layer; "
        "they are not an end-to-end LLM, human-study, coverage, or ASPICE-assessor evaluation.",
    )
    replace_paragraph(document.paragraphs[start + 1], "Table VI. Main Results: Structural Simulation")
    replace_paragraph(
        document.paragraphs[start + 2],
        f"The synthetic ledger contained {summary['synthetic_artifact_count']} typed SWE.1–SWE.6 artifacts. "
        f"Its clean state achieved TC = {summary['clean_ledger_tc']:.3f} with "
        f"{len(summary['clean_ledger_violations'])} invariant violations; {summary['successful_clean_gate_promotions']} "
        "H1/H4 promotion checks succeeded. Across "
        f"{summary['total_seeded_faults']} deterministic structural-fault injections ({summary['repetitions_per_fault']} "
        "per fault class), the invariant layer detected "
        f"{summary['detected_faults']}/{summary['total_seeded_faults']} faults, yielding a structural-fault leakage "
        f"rate of {summary['structural_fault_leakage_rate']:.1%}. The mean faulted TC was "
        f"{summary['mean_faulted_traceability_completeness']:.4f}, and the mean violation count was "
        f"{summary['mean_faulted_violation_count']:.4f}. All six implemented structural fault classes had a 100% "
        "detection rate."
    )
    replace_paragraph(
        document.paragraphs[start + 3],
        "The result supports a narrow RQ1/RQ2 claim: for the six graph-structural fault patterns implemented by "
        "the harness, typed ledger invariants identify the injected inconsistency before promotion. It must not be "
        "generalized to semantic defects, LLM hallucinations, or production automotive artifacts. No data were "
        "available to compare B0/B1/B2 or the ablations, calculate MC/DC/branch coverage, quantify review effort "
        "or NASA-TLX, or obtain assessor ratings. Those measures require the frozen project inputs, LLM integration, "
        "generated-code and coverage workflow, human-review records, and blind assessment specified in Section V."
    )

    table = document.tables[5]
    rows = {
        "B0 manual": ["Not measured", "Not measured", "Not measured", "Not measured", "Not measured", "Not measured"],
        "B1 single agent": ["Not measured", "Not measured", "Not measured", "Not measured", "Not measured", "Not measured"],
        "B2 unsupervised MAS": ["Not measured", "Not measured", "Not measured", "Not measured", "Not measured", "Not measured"],
        "M − ledger": ["Not measured", "Not measured", "Not measured", "Not measured", "Not measured", "Not measured"],
        "M − critic": ["Not measured", "Not measured", "Not measured", "Not measured", "Not measured", "Not measured"],
        "M − policy": ["Not measured", "Not measured", "Not measured", "Not measured", "Not measured", "Not measured"],
        "MAVERICK": [
            "1.000 (clean); 0.9655 mean faulted",
            "0 (clean); 1.333 mean faulted",
            "0/600 (0.0%) structural catalog only",
            "Not measured",
            "Not measured",
            "Not measured",
        ],
    }
    for row in table.rows[1:]:
        label = row.cells[0].text.strip()
        for cell, value in zip(row.cells[1:], rows[label]):
            cell.text = value

    document.save(OUTPUT)
    print(OUTPUT)


if __name__ == "__main__":
    main()
