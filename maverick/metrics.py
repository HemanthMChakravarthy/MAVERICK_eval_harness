"""Metrics for the MAVERICK evaluation harness.

- Traceability completeness TC and per-gate I1-I11 violations (via invariants).
- Seeded-defect leakage per gate.
- Structural coverage via a deterministic *tool stub* with seeded gaps.
- Reviewer-minutes model: lognormal per (artifact type x ASIL), scaled by
  configuration effort and finding count; plus an authoring-cost model so
  human-authored (B0/B3) and LLM-drafted (others) configurations are
  comparable in simulated reviewer-minutes.
- Critic precision/recall against the seeded semantic-fault ground truth.

The coverage stub, the reviewer-minutes model and the authoring model are
*simulation models*, not measurements. Coverage values are deterministic
pseudo-measurements derived from (seed, unit id) *and from the pipeline
rigor of the configuration* (documented assumption): a configuration that
generates and passes more verification (M-full) measures higher achieved
coverage than one that skips verification (B1/B2), because the stub models
achieved coverage as a function of which tests the configuration actually
generates and passes. A seeded shortfall appears wherever the M2 defect
(missing km/h->m/s conversion) is present and undetected. Reviewer minutes
are lognormal samples around documented base values.
"""
from __future__ import annotations

import hashlib
import math
import random
from typing import Dict, Optional, Tuple

#: Base review minutes per artifact type (single reviewer, ASIL B, no findings).
BASE_MINUTES: Dict[str, float] = {
    "SwReq": 45.0,
    "SwArch": 60.0,
    "SwDesign": 50.0,
    "SwUnit": 40.0,
    "UnitTest": 30.0,
    "CompTest": 30.0,
    "IntTest": 35.0,
    "QualTest": 50.0,
    "Result": 10.0,
    "SysReq": 20.0,
}

#: Base *authoring* minutes per artifact type (single author, ASIL B).
#: Human authoring (B0/B3) is charged at full rate; LLM drafting (all other
#: configurations) is charged at ``authoring_scale`` (default 0.05) of this
#: base -- a documented assumption, not a measured LLM cost.
AUTHORING_MINUTES: Dict[str, float] = {
    "SwReq": 120.0,
    "SwArch": 180.0,
    "SwDesign": 150.0,
    "SwUnit": 240.0,
    "UnitTest": 60.0,
    "CompTest": 60.0,
    "IntTest": 90.0,
    "QualTest": 120.0,
    "Result": 5.0,
    "SysReq": 40.0,
}

#: ASIL multiplier on review effort.
ASIL_MULT: Dict[str, float] = {"QM": 0.7, "A": 0.85, "B": 1.0, "C": 1.25, "D": 1.5}


def sample_authoring_minutes(
    rng: random.Random,
    atype: str,
    asil: str,
    authoring_scale: float,
) -> float:
    """Sample authoring minutes for one artifact.

    Lognormal around ``AUTHORING_MINUTES[atype] * asil_mult * authoring_scale``.
    """
    base = AUTHORING_MINUTES.get(atype, 60.0) * ASIL_MULT.get(asil, 1.0) * authoring_scale
    mu = math.log(max(base, 1e-6))
    return rng.lognormvariate(mu, 0.4)


def sample_review_minutes(
    rng: random.Random,
    atype: str,
    asil: str,
    n_findings: int,
    effort_scale: float,
) -> float:
    """Sample reviewer minutes for one artifact review.

    Lognormal around ``base * asil_mult * effort_scale``; each finding under
    review adds effort (disposition, re-check).
    """
    base = BASE_MINUTES.get(atype, 30.0) * ASIL_MULT.get(asil, 1.0) * effort_scale
    mu = math.log(max(base, 1e-6)) + 0.25 * n_findings
    return rng.lognormvariate(mu, 0.5)


def _pseudo_uniform(*parts: str) -> float:
    """Deterministic pseudo-random value in [0, 1) from string parts."""
    digest = hashlib.sha256("|".join(parts).encode()).hexdigest()
    return int(digest, 16) / 2**256


def simulate_coverage(
    seed: int,
    unit_id: str,
    has_defect: bool,
    rng: random.Random,
    rigor: float = 1.0,
) -> Dict[str, float]:
    """Deterministic structural-coverage stub for one unit (percent).

    The stub models *achieved* coverage as a function of the pipeline's
    verification rigor (documented assumption): ``rigor`` in [0, 1] reflects
    how much verification the configuration actually generates and passes
    (M-full = 1.0; B1/B2 ~ 0.2-0.3). This is why the stub's output varies by
    configuration -- it is *explained* variation, not noise: a pipeline that
    skips unit verification cannot measure high coverage.

    Clean units measure high with small deterministic variation; a unit with
    an undetected seeded defect (e.g. M2, missing unit conversion) shows a
    branch/statement shortfall. A small flaky-gap rate exercises the retry
    path even on clean units.
    """
    base = 96.0 + 3.9 * _pseudo_uniform(str(seed), unit_id, "branch")
    rigor_gap = (1.0 - rigor) * 6.0  # skipped verification -> lower achieved coverage
    branch = base - rigor_gap + rng.uniform(-0.5, 0.5)
    stmt = min(100.0, branch + 1.5 + rng.uniform(0, 0.5))
    mcdc = branch - 1.0 + rng.uniform(-0.5, 0.5)
    if has_defect:
        stmt, branch, mcdc = 88.0, 72.0, 65.0  # seeded shortfall
    elif rng.random() < 0.08:
        branch = min(branch, 75.0)  # flaky tool-measured gap on a clean unit
    return {"statement": stmt, "branch": branch, "mcdc": mcdc}


def simulate_interface_coverage(
    seed: int, if_id: str, rng: random.Random, rigor: float = 1.0
) -> Dict[str, float]:
    function = 95.0 + 5.0 * _pseudo_uniform(str(seed), if_id, "function")
    call = 94.0 + 6.0 * _pseudo_uniform(str(seed), if_id, "call") - (1.0 - rigor) * 4.0
    if rng.random() < 0.08:
        call = min(call, 82.0)
    return {"function": function, "call": call}
