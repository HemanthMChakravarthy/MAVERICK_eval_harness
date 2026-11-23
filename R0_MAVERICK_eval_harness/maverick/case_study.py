"""Synthetic worked-example fixtures for the MAVERICK evaluation harness.

*** ILLUSTRATIVE / SYNTHETIC *** -- these fixtures are small, hand-built,
plausible models. They are *not* derived from real products, real
requirements, or real code; they exist so the simulated agents have
realistic-shaped artifacts to produce and link. In the paper they are
"worked examples", never "case studies".

Two fixtures:
- ``aeb``: camera-based pedestrian-detection post-processing and
  plausibility function (ASIL B / QM).
- ``asild``: steering-torque arbitration function (ASIL D) with a stricter
  policy: mandatory independent human review at every gate, branch/MC-DC
  coverage targets of 100%, and a retry budget of k=5.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

SYNTHETIC_NOTICE = (
    "SYNTHETIC/ILLUSTRATIVE fixture: hand-built for simulation, "
    "not derived from any real product or requirements document."
)


@dataclass(frozen=True)
class SysReq:
    rid: str
    text: str
    asil: str
    safety: bool


@dataclass(frozen=True)
class SwReqSpec:
    rid: str
    text: str
    asil: str
    derives_from: Tuple[str, ...]
    safety: bool = False
    derived: bool = False


@dataclass(frozen=True)
class ArchSpec:
    aid: str
    kind: str  # "component" | "interface"
    text: str
    asil: str


@dataclass(frozen=True)
class UnitSpec:
    uid: str
    text: str
    asil: str
    implements: Tuple[str, ...]  # SwReq ids
    arch: str  # owning SwArch component id
    template: Dict  # correct payload the simulated agent starts from


@dataclass(frozen=True)
class CaseStudy:
    notice: str
    fixture_id: str  # "aeb" | "asild"
    retry_budget: int  # ASIL-indexed bounded retry budget (3, or 5 for ASIL-D)
    sys_reqs: Tuple[SysReq, ...]
    sw_reqs: Tuple[SwReqSpec, ...]
    arch: Tuple[ArchSpec, ...]
    units: Tuple[UnitSpec, ...]

    def sw_req(self, rid: str) -> SwReqSpec:
        return next(s for s in self.sw_reqs if s.rid == rid)

    def unit(self, uid: str) -> UnitSpec:
        return next(u for u in self.units if u.uid == uid)


def build_case_study(fixture: str = "aeb") -> CaseStudy:
    """Build a synthetic worked-example fixture.

    ``fixture`` is "aeb" (ASIL B/QM pedestrian post-processing) or "asild"
    (ASIL D steering-torque arbitration, k=5 retries).
    """
    if fixture == "asild":
        return _build_asild()
    if fixture == "aeb":
        return _build_aeb()
    raise ValueError(f"unknown fixture {fixture!r}")


def _build_aeb() -> CaseStudy:
    sys_reqs = (
        SysReq("SYS-001",
               "The perception system shall detect pedestrians in the forward camera field of view.",
               "QM", False),
        SysReq("SYS-002",
               "If a pedestrian is in the ego vehicle path with time-to-collision below 2.5 s, "
               "the system shall request emergency braking within 100 ms.",
               "B", True),
        SysReq("SYS-003",
               "The system shall suppress braking requests for camera detections that are not "
               "confirmed by radar (plausibility check).",
               "B", True),
        SysReq("SYS-004",
               "The tracked object list shall be published to the fusion module at 20 Hz.",
               "QM", False),
    )

    sw_reqs = (
        SwReqSpec("SWR-001",
                  "The software shall discard camera detections with confidence score below 0.6 "
                  "before tracking.", "B", ("SYS-001",)),
        SwReqSpec("SWR-002",
                  "The software shall maintain one constant-velocity Kalman track per pedestrian "
                  "with state [x, y, vx, vy] in m and m/s, associating detections with IoU above 0.3.",
                  "B", ("SYS-001",)),
        SwReqSpec("SWR-003",
                  "The software shall compute time-to-collision as longitudinal_distance_m / "
                  "closing_speed_mps for tracks with closing speed above 0.5 m/s.",
                  "B", ("SYS-002",)),
        SwReqSpec("SWR-004",
                  "The software shall confirm a camera track only if a radar return exists within "
                  "1.5 m lateral distance and the plausibility score is at least 0.7.",
                  "B", ("SYS-003",)),
        SwReqSpec("SWR-005",
                  "If the minimum TTC of a confirmed track in the ego path is below 2.5 s, the "
                  "software shall set brake_request within 100 ms.",
                  "B", ("SYS-002",), safety=True),
        SwReqSpec("SWR-006",
                  "The software shall not set brake_request for tracks with plausibility score below 0.7.",
                  "B", ("SYS-003",), safety=True),
        SwReqSpec("SWR-007",
                  "The software shall publish the tracked object list at 20 Hz.",
                  "QM", ("SYS-004",)),
        SwReqSpec("SWR-008",
                  "The plausibility score shall combine camera confidence and radar cross-section "
                  "with weights 0.6 and 0.4.",
                  "B", ("SYS-003",), derived=True),
    )

    arch = (
        ArchSpec("COMP-Filter", "component", "Detection confidence filtering", "B"),
        ArchSpec("COMP-Tracker", "component", "Kalman multi-object tracking", "B"),
        ArchSpec("COMP-TTC", "component", "Time-to-collision computation", "B"),
        ArchSpec("COMP-Plaus", "component", "Radar plausibility fusion", "B"),
        ArchSpec("COMP-Brake", "component", "Brake request decision", "B"),
        ArchSpec("COMP-Pub", "component", "Object list publisher", "QM"),
        ArchSpec("IF-DetList", "interface", "Detection list: id, bbox, confidence", "B"),
        ArchSpec("IF-TrackList", "interface", "Track list: id, state, plausibility", "B"),
        ArchSpec("IF-BrakeReq", "interface", "Brake request: boolean + timestamp", "B"),
    )

    units = (
        UnitSpec("UNIT-filter-conf",
                 "Confidence filtering of the detection list", "B", ("SWR-001",), "COMP-Filter",
                 {"function": "filter_by_confidence", "threshold": 0.6,
                  "input": "detections", "output": "filtered_detections"}),
        UnitSpec("UNIT-kalman-predict",
                 "Kalman predict step (constant velocity)", "B", ("SWR-002",), "COMP-Tracker",
                 {"function": "kalman_predict", "state": "[x, y, vx, vy]",
                  "dt_s": 0.05, "velocity_unit": "m/s"}),
        UnitSpec("UNIT-kalman-update",
                 "Kalman update step with IoU association", "B", ("SWR-002",), "COMP-Tracker",
                 {"function": "kalman_update", "assoc_iou": 0.3, "velocity_unit": "m/s"}),
        UnitSpec("UNIT-compute-ttc",
                 "Time-to-collision computation", "B", ("SWR-003",), "COMP-TTC",
                 {"function": "compute_ttc", "formula": "dist_m / closing_mps",
                  "min_closing_mps": 0.5}),
        UnitSpec("UNIT-radar-match",
                 "Radar return association within lateral gate", "B", ("SWR-004",), "COMP-Plaus",
                 {"function": "radar_match", "gate_m": 1.5}),
        UnitSpec("UNIT-plaus-score",
                 "Plausibility score fusion", "B", ("SWR-008",), "COMP-Plaus",
                 {"function": "plausibility_score", "w_cam": 0.6, "w_radar": 0.4, "threshold": 0.7}),
        UnitSpec("UNIT-brake-decision",
                 "Brake request decision logic", "B", ("SWR-005", "SWR-006"), "COMP-Brake",
                 {"function": "brake_decision", "brake_condition": "ttc_s < 2.5",
                  "ttc_threshold_s": 2.5, "plaus_min": 0.7, "latency_ms": 100}),
        UnitSpec("UNIT-publish",
                 "Object list publisher (20 Hz)", "QM", ("SWR-007",), "COMP-Pub",
                 {"function": "publish_objlist", "rate_hz": 20}),
    )

    return CaseStudy(
        notice=SYNTHETIC_NOTICE,
        fixture_id="aeb",
        retry_budget=3,
        sys_reqs=sys_reqs,
        sw_reqs=sw_reqs,
        arch=arch,
        units=units,
    )


def _build_asild() -> CaseStudy:
    """ASIL-D steering-torque arbitration worked example (synthetic).

    A (fictional) function arbitrating driver vs. ADAS steering-torque
    requests with a redundant plausibility monitor. Stricter policy than the
    AEB fixture: mandatory independent human review at every gate, 100%
    branch/MC-DC coverage targets, k=5 retries.
    """
    sys_reqs = (
        SysReq("SYS-STR-001",
               "The steering system shall arbitrate driver and ADAS torque requests "
               "such that a driver override is always possible.",
               "D", True),
        SysReq("SYS-STR-002",
               "Torque arbitration shall never command a steering torque above 8 Nm "
               "without explicit driver confirmation.",
               "D", True),
        SysReq("SYS-STR-003",
               "Torque arbitration decisions shall be diagnosable via logged data.",
               "QM", False),
    )
    sw_reqs = (
        SwReqSpec("SWR-S101",
                  "The software shall select the minimum of the driver torque request "
                  "and the ADAS torque request when both inputs are valid.",
                  "D", ("SYS-STR-001",), safety=True),
        SwReqSpec("SWR-S102",
                  "The software shall limit the arbitrated steering torque to 8 Nm.",
                  "D", ("SYS-STR-002",), safety=True),
        SwReqSpec("SWR-S103",
                  "The software shall plausibilize the redundant torque sensor pair; "
                  "a deviation above 0.5 Nm shall trigger the safe state.",
                  "D", ("SYS-STR-002",), safety=True),
        SwReqSpec("SWR-S104",
                  "The software shall log torque arbitration decisions at 100 Hz.",
                  "QM", ("SYS-STR-003",)),
    )
    arch = (
        ArchSpec("COMP-Arb", "component", "Torque arbitration", "D"),
        ArchSpec("COMP-Mon", "component", "Torque plausibility monitor", "D"),
        ArchSpec("COMP-Diag", "component", "Diagnostics logging", "QM"),
        ArchSpec("IF-TorqueBus", "interface", "Torque bus: request, arbitration, limit", "D"),
    )
    units = (
        UnitSpec("UNIT-arb-select",
                 "Torque request selection (min of driver/ADAS)", "D", ("SWR-S101",), "COMP-Arb",
                 {"function": "arb_select", "rule": "min(driver_req, adas_req)",
                  "input_valid": "both_valid"}),
        UnitSpec("UNIT-arb-limit",
                 "Arbitrated torque limiter (8 Nm)", "D", ("SWR-S102",), "COMP-Arb",
                 {"function": "arb_limit", "limit_nm": 8.0}),
        UnitSpec("UNIT-mon-plaus",
                 "Torque sensor pair plausibility", "D", ("SWR-S103",), "COMP-Mon",
                 {"function": "mon_plaus", "deviation_limit_nm": 0.5}),
        UnitSpec("UNIT-mon-shutdown",
                 "Safe-state transition on plausibility failure", "D", ("SWR-S103",), "COMP-Mon",
                 {"function": "mon_shutdown", "safe_state": "torque_free"}),
        UnitSpec("UNIT-log-torque",
                 "Torque arbitration decision logger (100 Hz)", "QM", ("SWR-S104",), "COMP-Diag",
                 {"function": "log_torque_decision", "rate_hz": 100}),
    )
    return CaseStudy(
        notice=SYNTHETIC_NOTICE,
        fixture_id="asild",
        retry_budget=5,
        sys_reqs=sys_reqs,
        sw_reqs=sw_reqs,
        arch=arch,
        units=units,
    )
