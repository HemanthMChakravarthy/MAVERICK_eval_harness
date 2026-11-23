"""Seeded defect catalog for the MAVERICK evaluation harness.

Fifteen defect types: six *structural* (violating traceability invariants
I1-I6, hence deterministically catchable by ledger invariant checks), six
*semantic* (payload-level faults that no graph query can see; they require
the LLM critic, structural coverage, or human review), and three
*link-integrity* defects (W1 wrong-target link, W2 spurious link, R1
hallucinated rationale) that break the "faults map 1:1 to invariants"
circularity: the link is present and type-valid, so link-existence
invariants (I1/I4/I7) cannot see the fault; only the critic
(probabilistically) or human review can.

Each defect targets a specific gate and artifact. ``detectable_by`` names the
mechanisms that can catch it: "ledger" (invariant checks I1-I11 and the gate
completeness review), "alm" (ALM-style link-existence checks -- the B3
baseline; a subset of "ledger" covering only missing-link/missing-artifact
defects, never wrong-target/spurious/rationale faults), "policy"
(supervisor deterministic checks), "critic" (LLM critic), "human" (human
review), "coverage" (structural coverage shortfall).
Three defects are *omissions* (the agent fails to produce an artifact); these
are handled at gate level rather than by payload mutation.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from .ledger import Link


@dataclass(frozen=True)
class DefectSpec:
    defect_id: str  # "S1".."S6" structural, "M1".."M6" semantic,
    # "W1"/"W2"/"R1" link-integrity
    kind: str  # "structural" | "semantic" | "link-integrity"
    name: str
    description: str
    target_gate: str  # gate at which the defect is introduced
    target: str  # selector, e.g. "swreq:any", "unit:UNIT-x", "omit:swreq:SWR-005"
    detectable_by: Tuple[str, ...]


CATALOG: List[DefectSpec] = [
    # ---------------- structural ----------------
    DefectSpec(
        "S1", "structural", "orphan-unit",
        "SwUnit produced without any implements link (orphan unit).",
        "H3", "unit:UNIT-kalman-update", ("ledger", "alm", "human"),
    ),
    DefectSpec(
        "S2", "structural", "dangling-link",
        "SwUnit implements link points at a non-existent artifact id.",
        "H3", "unit:UNIT-compute-ttc", ("ledger", "alm", "policy", "human"),
    ),
    DefectSpec(
        "S3", "structural", "missing-parent-link",
        "SwReq produced without derives-from link and not flagged derived.",
        "H1", "swreq:any", ("ledger", "alm", "human"),
    ),
    DefectSpec(
        "S4", "structural", "asil-inheritance-violation",
        "SwUnit attributed a lower ASIL than its parent SwReq without a "
        "recorded, human-approved decomposition.",
        "H3", "unit:UNIT-radar-match", ("ledger", "human"),
    ),
    DefectSpec(
        "S5", "structural", "unimplemented-requirement",
        "Agent omits a SwUnit, leaving a SwReq with no implementation.",
        "H3", "omit:unit:UNIT-plaus-score", ("ledger", "alm", "human"),
    ),
    DefectSpec(
        "S6", "structural", "unverified-requirement",
        "Agent omits a QualTest, leaving a SwReq with no qualification test.",
        "H6", "omit:qualtest:SWR-005", ("ledger", "alm", "human"),
    ),
    # ---------------- semantic ----------------
    DefectSpec(
        "M1", "semantic", "inverted-inequality",
        "Brake-decision plausibility check uses an inverted inequality "
        "(brakes when TTC > 2.5 s instead of < 2.5 s).",
        "H3", "unit:UNIT-brake-decision", ("critic", "human"),
    ),
    DefectSpec(
        "M2", "semantic", "missing-unit-conversion",
        "Kalman update consumes raw CAN velocity in km/h as if it were m/s "
        "(missing /3.6 conversion); also depresses branch coverage.",
        "H3", "unit:UNIT-kalman-update", ("critic", "human", "coverage"),
    ),
    DefectSpec(
        "M3", "semantic", "dropped-safety-requirement",
        "Requirements agent silently drops a safety requirement (SWR-005).",
        "H1", "omit:swreq:SWR-005", ("ledger", "alm", "human"),
    ),
    DefectSpec(
        "M4", "semantic", "wrong-asil-attribute",
        "Safety-related artifact attributed QM instead of its inherited ASIL.",
        "H1", "swreq:any", ("ledger", "policy", "human"),
    ),
    DefectSpec(
        "M5", "semantic", "contradictory-requirements",
        "Requirement text states a 2.5 s TTC threshold while the formal "
        "parameter is set to 1.0 s.",
        "H1", "swreq:SWR-003", ("critic", "human"),
    ),
    DefectSpec(
        "M6", "semantic", "untestable-requirement",
        "Requirement phrased vaguely ('react as soon as possible'), not testable.",
        "H1", "swreq:any", ("critic", "human"),
    ),
    # ---- link-integrity defects (W1/W2/R1): links are PRESENT and type-valid,
    # so link-existence invariants (I1/I4/I7) and ALM-style checks cannot see
    # them. Only the critic (probabilistically, and not under correlated
    # failure) or human review can catch them. This breaks the earlier
    # "faults map 1:1 to invariants" circularity.
    DefectSpec(
        "W1", "link-integrity", "wrong-target-link",
        "Trace link exists but points at the wrong detailed-design element "
        "(a test's verifies-design link targets a design it does not "
        "exercise). Invisible to link-existence invariants.",
        "H4", "unittest:any", ("critic", "human"),
    ),
    DefectSpec(
        "W2", "link-integrity", "spurious-link",
        "Fabricated derives-from link to an unrelated but real system "
        "requirement. Existence and dangling checks pass; the fabrication "
        "is invisible to graph queries.",
        "H1", "swreq:any", ("critic", "human"),
    ),
    DefectSpec(
        "R1", "link-integrity", "hallucinated-rationale",
        "Plausible-sounding but false justification text attached to an "
        "artifact ('verified against SYS-REQ-004', which does not exist).",
        "H1", "swreq:any", ("critic", "human"),
    ),
]

BY_ID: Dict[str, DefectSpec] = {d.defect_id: d for d in CATALOG}


def get(defect_id: str) -> DefectSpec:
    return BY_ID[defect_id]


def is_omission(defect_id: str) -> bool:
    return BY_ID[defect_id].target.startswith("omit:")


def apply_mutation(payload: dict, links: List[Link], defect_id: str,
                   alt_targets: tuple = ()) -> str | None:
    """Apply a defect's payload/link mutation in place.

    Returns a replacement ASIL if the defect changes it, else None.
    Raises for omission defects (handled by the experiment, not by mutation).

    ``alt_targets``: candidate artifact ids for the W1 wrong-target defect;
    the verifies link is repointed at the first id that differs from its
    current target (guaranteeing the target is wrong *for this artifact*).
    """
    if defect_id == "S1":  # orphan unit: drop implements links
        links[:] = [l for l in links if l.link_type != "implements"]
    elif defect_id == "S2":  # dangling link
        links.append(Link("implements", "GHOST-ARTIFACT-999"))
    elif defect_id == "S3":  # missing parent link
        links[:] = [l for l in links if l.link_type != "derives-from"]
        payload.pop("derived", None)
    elif defect_id == "S4":  # ASIL inheritance violation: downgrade one rank
        return "A"  # parent is ASIL B; no decomposition record is added
    elif defect_id == "M1":  # inverted inequality / inverted selection rule
        payload["brake_condition"] = "ttc_s > 2.5"  # correct: "ttc_s < 2.5"
        if "rule" in payload:  # asild fixture: invert min->max arbitration
            payload["rule"] = "max(driver_req, adas_req)"
        payload["defect_note"] = "inverted comparison/selection (seeded defect M1)"
    elif defect_id == "M2":  # missing km/h -> m/s conversion / wrong scale factor
        payload["velocity_unit"] = "km/h-as-m/s"
        if "limit_nm" in payload:  # asild fixture: 10x scale error on limiter
            payload["limit_nm"] = 80.0
        payload["defect_note"] = "wrong scale factor (seeded M2)"
    elif defect_id == "M4":  # wrong ASIL attribute
        return "QM"
    elif defect_id == "M5":  # contradictory requirement
        payload["ttc_threshold_param_s"] = 1.0  # text still says 2.5 s
        payload["defect_note"] = "parameter 1.0 s contradicts requirement text 2.5 s (seeded M5)"
    elif defect_id == "M6":  # untestable requirement
        payload["text"] = (
            "The software shall react as soon as possible when the situation looks dangerous."
        )
        payload["defect_note"] = "vague, untestable phrasing (seeded M6)"
    elif defect_id == "W1":  # wrong-target link: repoint verifies-design at a wrong SwDesign
        # The link EXISTS and is type-valid (verifies-design -> SwDesign), so
        # I7 link-existence passes; the verifies link is untouched so I5 is
        # unaffected. Only the critic or human can catch the wrong target.
        cur = next((l.target_id for l in links if l.link_type == "verifies-design"), None)
        wrong = next((t for t in alt_targets if t != cur), cur)
        for l in links:
            if l.link_type == "verifies-design":
                links[links.index(l)] = Link("verifies-design", wrong)
                break
        payload["defect_note"] = f"verifies-design repointed at wrong design {wrong} (seeded W1)"
    elif defect_id == "W2":  # spurious link: fabricated derives-from to an unrelated REAL SysReq
        # The target exists, so I1's dangling check passes and I1 existence
        # passes; the fabrication (wrong parent) is invisible to graph
        # queries. Only the critic or human can catch it.
        parents = {l.target_id for l in links if l.link_type == "derives-from"}
        spurious = next((t for t in alt_targets if t not in parents), None)
        if spurious is None:
            spurious = next(iter(parents), "SYS-001")  # degenerate fallback
        links.append(Link("derives-from", spurious))
        payload["defect_note"] = f"fabricated derives-from link -> {spurious} (seeded W2)"
    elif defect_id == "R1":  # hallucinated rationale
        payload["rationale"] = (
            "Verified against SYS-REQ-004 per ASPICE SWE.1 output information item; "
            "allocation confirmed by design authority."
        )
        payload["defect_note"] = "plausible-but-false justification text (seeded R1)"
    else:
        raise ValueError(f"defect {defect_id!r} is an omission or unknown; cannot mutate")
    return None
