"""Traceability invariants I1-I11 as deterministic graph queries over the ledger.

I1  Upward completeness:   every SwReq derives-from a SysReq (or is flagged derived).
I2  Downward completeness: (a) every safety SysReq has a deriving SwReq;
                            (b) every SwReq is implemented by >= 1 SwUnit.
I3  Allocation:             every SwReq is allocated-to a SwArch element.
I4  Implementation:         no orphan units (every SwUnit implements a SwReq
                            *and* realizes a SwDesign detailed-design element).
I5  Verification:           every SwReq has a QualTest, every SwUnit a UnitTest,
                            every interface a IntTest.
I6  ASIL inheritance:       downward links never lower ASIL without a recorded,
                            human-approved decomposition.
I7  Design linkage:         every test case (UnitTest, CompTest, IntTest,
                            QualTest) links to a detailed-design element via
                            ``verifies-design``. Existence only: a link to the
                            *wrong* design element is invisible here (defect
                            classes W1/W2) and needs the critic/human review.
I8  Component verification: every SwUnit has >= 1 CompTest (SWE.5 component
                            verification, distinct from interface integration).
I9  Result recorded:        every test case has a recorded Result.
I10 Result linkage:         every Result links back to its test specification
                            via ``result-of``.
I11 Result pass gate:       the latest Result linked to a test must have
                            verdict "pass" for the test to be promotable.

Each check returns a list of Violation records. TC (traceability completeness)
is the fraction of artifacts satisfying all invariants applicable to them;
the paper requires TC = 1 at the final gate.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from .ledger import ASIL_RANK, Ledger


@dataclass(frozen=True)
class Violation:
    check: str  # "I1" .. "I11"
    key: str  # envelope key
    artifact_id: str  # logical artifact id the violation is attributed to
    detail: str


def _latest(ledger: Ledger):
    return ledger.latest_map()


def _has_link_to(env, link_type: str, target_id: str) -> bool:
    return any(l.link_type == link_type and l.target_id == target_id for l in env.links)


def c1_upward(ledger: Ledger) -> List[Violation]:
    out: List[Violation] = []
    latest = _latest(ledger)
    for lid, env in latest.items():
        if env.atype != "SwReq":
            continue
        derives = [l for l in env.links if l.link_type == "derives-from"]
        reaches_sysreq = False
        for link in derives:
            tgt = latest.get(link.target_id)
            if tgt is None:
                out.append(
                    Violation("I1", env.key, lid,
                              f"dangling derives-from link -> {link.target_id!r}")
                )
            elif tgt.atype == "SysReq":
                reaches_sysreq = True
        if not derives and not env.payload.get("derived"):
            out.append(
                Violation("I1", env.key, lid,
                          "no derives-from link and not flagged as derived")
            )
        elif derives and not reaches_sysreq and not env.payload.get("derived"):
            out.append(
                Violation("I1", env.key, lid,
                          "derives-from links do not reach any SysReq")
            )
    return out


def c2_downward(ledger: Ledger) -> List[Violation]:
    out: List[Violation] = []
    latest = _latest(ledger)
    # (a) every safety-related SysReq must have at least one deriving SwReq
    for lid, env in latest.items():
        if env.atype == "SysReq" and env.payload.get("safety"):
            deriving = [
                s for s in latest.values()
                if s.atype == "SwReq" and _has_link_to(s, "derives-from", lid)
            ]
            if not deriving:
                out.append(
                    Violation("I2", env.key, lid,
                              "safety SysReq has no deriving SwReq")
                )
    # (b) every SwReq must be implemented by at least one SwUnit
    for lid, env in latest.items():
        if env.atype != "SwReq":
            continue
        impl = [
            s for s in latest.values()
            if s.atype == "SwUnit" and _has_link_to(s, "implements", lid)
        ]
        if not impl:
            out.append(
                Violation("I2", env.key, lid, "SwReq has no implementing SwUnit")
            )
    return out


def c3_allocation(ledger: Ledger) -> List[Violation]:
    out: List[Violation] = []
    latest = _latest(ledger)
    for lid, env in latest.items():
        if env.atype != "SwReq":
            continue
        alloc = [l for l in env.links if l.link_type == "allocated-to"]
        if not alloc:
            out.append(
                Violation("I3", env.key, lid, "SwReq not allocated to any SwArch element")
            )
            continue
        for link in alloc:
            tgt = latest.get(link.target_id)
            if tgt is None:
                out.append(
                    Violation("I3", env.key, lid,
                              f"dangling allocated-to link -> {link.target_id!r}")
                )
            elif tgt.atype != "SwArch":
                out.append(
                    Violation("I3", env.key, lid,
                              f"allocated-to target {link.target_id!r} is not a SwArch element")
                )
    return out


def c4_implementation(ledger: Ledger) -> List[Violation]:
    out: List[Violation] = []
    latest = _latest(ledger)
    for lid, env in latest.items():
        if env.atype != "SwUnit":
            continue
        impl = [l for l in env.links if l.link_type == "implements"]
        if not impl:
            out.append(Violation("I4", env.key, lid, "orphan SwUnit: no implements link"))
        for link in impl:
            tgt = latest.get(link.target_id)
            if tgt is None:
                out.append(
                    Violation("I4", env.key, lid,
                              f"dangling implements link -> {link.target_id!r}")
                )
            elif tgt.atype != "SwReq":
                out.append(
                    Violation("I4", env.key, lid,
                              f"implements target {link.target_id!r} is not a SwReq")
                )
        # Every unit must additionally realize a detailed-design element.
        real = [l for l in env.links if l.link_type == "realizes"]
        if not real:
            out.append(
                Violation("I4", env.key, lid,
                          "SwUnit has no realizes link to a SwDesign element")
            )
        for link in real:
            tgt = latest.get(link.target_id)
            if tgt is None:
                out.append(
                    Violation("I4", env.key, lid,
                              f"dangling realizes link -> {link.target_id!r}")
                )
            elif tgt.atype != "SwDesign":
                out.append(
                    Violation("I4", env.key, lid,
                              f"realizes target {link.target_id!r} is not a SwDesign element")
                )
    return out


TEST_TYPES = ("UnitTest", "CompTest", "IntTest", "QualTest")


def _latest_result_for_test(ledger: Ledger, test_id: str):
    """Latest Result envelope whose result-of link points at ``test_id``."""
    latest = _latest(ledger)
    cands = [
        e for e in latest.values()
        if e.atype == "Result" and _has_link_to(e, "result-of", test_id)
    ]
    if not cands:
        return None
    return max(cands, key=lambda e: e.ver)


def i7_test_design_link(ledger: Ledger) -> List[Violation]:
    """I7: every test case links to a detailed-design element (existence)."""
    out: List[Violation] = []
    latest = _latest(ledger)
    for lid, env in latest.items():
        if env.atype not in TEST_TYPES:
            continue
        dlinks = [l for l in env.links if l.link_type == "verifies-design"]
        if not dlinks:
            out.append(
                Violation("I7", env.key, lid,
                          f"{env.atype} has no verifies-design link to a SwDesign element")
            )
            continue
        for link in dlinks:
            tgt = latest.get(link.target_id)
            if tgt is None:
                out.append(
                    Violation("I7", env.key, lid,
                              f"dangling verifies-design link -> {link.target_id!r}")
                )
            elif tgt.atype != "SwDesign":
                out.append(
                    Violation("I7", env.key, lid,
                              f"verifies-design target {link.target_id!r} is not a SwDesign element")
                )
    return out


def i8_component_test(ledger: Ledger) -> List[Violation]:
    """I8: every SwUnit has >= 1 CompTest (SWE.5 component verification)."""
    out: List[Violation] = []
    latest = _latest(ledger)
    for lid, env in latest.items():
        if env.atype != "SwUnit":
            continue
        covered = any(
            s.atype == "CompTest" and _has_link_to(s, "verifies", lid)
            for s in latest.values()
        )
        if not covered:
            out.append(
                Violation("I8", env.key, lid, "SwUnit has no verifying CompTest")
            )
    return out


def i9_result_recorded(ledger: Ledger) -> List[Violation]:
    """I9: every test case has a recorded Result."""
    out: List[Violation] = []
    latest = _latest(ledger)
    for lid, env in latest.items():
        if env.atype not in TEST_TYPES:
            continue
        if _latest_result_for_test(ledger, lid) is None:
            out.append(
                Violation("I9", env.key, lid, f"{env.atype} has no recorded Result")
            )
    return out


def i10_result_link(ledger: Ledger) -> List[Violation]:
    """I10: every Result links back to its test specification."""
    out: List[Violation] = []
    latest = _latest(ledger)
    for lid, env in latest.items():
        if env.atype != "Result":
            continue
        rlinks = [l for l in env.links if l.link_type == "result-of"]
        if not rlinks:
            out.append(
                Violation("I10", env.key, lid, "Result has no result-of link to a test")
            )
            continue
        for link in rlinks:
            tgt = latest.get(link.target_id)
            if tgt is None:
                out.append(
                    Violation("I10", env.key, lid,
                              f"dangling result-of link -> {link.target_id!r}")
                )
            elif tgt.atype not in TEST_TYPES:
                out.append(
                    Violation("I10", env.key, lid,
                              f"result-of target {link.target_id!r} is not a test case")
                )
    return out


def i11_result_pass(ledger: Ledger) -> List[Violation]:
    """I11: the latest Result linked to a test must have verdict "pass"."""
    out: List[Violation] = []
    latest = _latest(ledger)
    for lid, env in latest.items():
        if env.atype not in TEST_TYPES:
            continue
        res = _latest_result_for_test(ledger, lid)
        if res is None:
            continue  # missing result is an I9 violation, not I11
        if res.payload.get("verdict") != "pass":
            out.append(
                Violation("I11", env.key, lid,
                          f"{env.atype} latest result verdict is "
                          f"{res.payload.get('verdict')!r}, not 'pass'")
            )
    return out


def c5_verification(ledger: Ledger) -> List[Violation]:
    out: List[Violation] = []
    latest = _latest(ledger)

    def verified_by(lid: str, test_type: str) -> bool:
        return any(
            s.atype == test_type and _has_link_to(s, "verifies", lid)
            for s in latest.values()
        )

    for lid, env in latest.items():
        if env.atype == "SwReq" and not verified_by(lid, "QualTest"):
            out.append(Violation("I5", env.key, lid, "SwReq has no verifying QualTest"))
        elif env.atype == "SwUnit" and not verified_by(lid, "UnitTest"):
            out.append(Violation("I5", env.key, lid, "SwUnit has no verifying UnitTest"))
        elif (
            env.atype == "SwArch"
            and env.payload.get("kind") == "interface"
            and not verified_by(lid, "IntTest")
        ):
            out.append(
                Violation("I5", env.key, lid, "interface has no verifying IntTest")
            )
    return out


def c6_asil(ledger: Ledger) -> List[Violation]:
    out: List[Violation] = []
    latest = _latest(ledger)
    for lid, env in latest.items():
        if env.atype == "SysReq":
            continue
        for link in env.links:
            tgt = latest.get(link.target_id)
            if tgt is None:
                continue  # dangling links are reported by I1/I3/I4
            if ASIL_RANK[env.asil] < ASIL_RANK[tgt.asil] and not env.payload.get(
                "decomposition_approved"
            ):
                out.append(
                    Violation(
                        "I6", env.key, lid,
                        f"ASIL {env.asil} lower than parent {tgt.asil} "
                        f"({link.link_type} -> {link.target_id}) without approved decomposition",
                    )
                )
    return out


CHECKS = {
    "I1": c1_upward,
    "I2": c2_downward,
    "I3": c3_allocation,
    "I4": c4_implementation,
    "I5": c5_verification,
    "I6": c6_asil,
    "I7": i7_test_design_link,
    "I8": i8_component_test,
    "I9": i9_result_recorded,
    "I10": i10_result_link,
    "I11": i11_result_pass,
}

#: Ordered check names (for CSVs and reports).
CHECK_ORDER = ("I1", "I2", "I3", "I4", "I5", "I6", "I7", "I8", "I9", "I10", "I11")


def check_all(ledger: Ledger) -> Dict[str, List[Violation]]:
    """Run every invariant; returns {check_name: [violations]}.

    Deduplicates identical (check, key, artifact, detail) tuples so repeated
    links to the same bad target cannot inflate counts.
    """
    out: Dict[str, List[Violation]] = {}
    for name, fn in CHECKS.items():
        seen = set()
        uniq: List[Violation] = []
        for v in fn(ledger):
            if v not in seen:
                seen.add(v)
                uniq.append(v)
        out[name] = uniq
    return out


def check_envelope(ledger: Ledger, key: str, only: tuple = ()) -> List[Violation]:
    """Violations attributed to a single envelope (pre-promotion gate).

    ``only`` restricts to a subset of checks -- used for gate-scoped
    pre-promotion checks (a SwReq at H1 cannot yet satisfy downstream
    completeness I2/I5; those are closure checks, not promotion blockers).
    """
    checks = CHECKS.items() if not only else [(n, CHECKS[n]) for n in only]
    out: List[Violation] = []
    for name, fn in checks:
        out.extend(v for v in fn(ledger) if v.key == key)
    seen = set()
    return [v for v in out if not (v in seen or seen.add(v))]


#: Which invariants apply to each artifact type (for TC attribution).
APPLICABLE = {
    "SwReq": ("I1", "I2", "I3", "I5", "I6"),
    "SwArch": ("I6",),
    "SwDesign": ("I6",),
    "SwUnit": ("I4", "I5", "I6", "I8"),
    "UnitTest": ("I6", "I7", "I9", "I11"),
    "CompTest": ("I6", "I7", "I9", "I11"),
    "IntTest": ("I6", "I7", "I9", "I11"),
    "QualTest": ("I6", "I7", "I9", "I11"),
    "Result": ("I6", "I10"),
    "SysReq": (),
}


def traceability_completeness(ledger: Ledger) -> float:
    """TC = fraction of artifacts satisfying all applicable invariants.

    Computed over latest versions, excluding SysReq process inputs.
    Vacuous (no artifacts) -> 1.0.
    """
    latest = _latest(ledger)
    artifacts = [e for e in latest.values() if e.atype != "SysReq"]
    if not artifacts:
        return 1.0
    by_check = check_all(ledger)
    bad_ids = set()
    for check, vs in by_check.items():
        for v in vs:
            env = latest.get(v.artifact_id)
            if env is not None and check in APPLICABLE.get(env.atype, ()):
                bad_ids.add(v.artifact_id)
    ok = sum(1 for e in artifacts if e.id not in bad_ids)
    return ok / len(artifacts)
