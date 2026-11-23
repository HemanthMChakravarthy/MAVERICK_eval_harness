"""Fault catalog (15 classes) and graph mutators.

Structural and link-integrity faults MUTATE the ledger graph; whether an
invariant fires is then computed by Ledger.violations(), not assumed.
Semantic faults change payload content only (invisible to graph queries).
"""
from __future__ import annotations

# name, category, stage(gate H1..H6 where first reviewed), test_detect (prob that an
# independently derived, executed test reveals it)
CATALOG = [
    ("dropped_parent_link",     "St", 1, 0.0),
    ("wrong_asil_attr",         "St", 3, 0.0),
    ("dropped_allocation",      "St", 2, 0.0),
    ("orphan_unit",             "St", 3, 0.0),
    ("dangling_link",           "St", 6, 0.0),
    ("dropped_qual_test",       "St", 6, 0.0),
    ("dropped_safety_req",      "Sm", 1, 0.0),
    ("contradictory_reqs",      "Sm", 1, 0.0),
    ("untestable_req",          "Sm", 1, 0.2),
    ("wrong_asil_derived",      "Sm", 1, 0.0),
    ("inverted_inequality",     "Sm", 3, 0.5),
    ("missing_unit_conversion", "Sm", 3, 0.5),
    ("wrong_target_link",       "LI", 1, 0.0),
    ("spurious_link",           "LI", 6, 0.0),
    ("hallucinated_rationale",  "LI", 1, 0.0),
]
NAMES = [c[0] for c in CATALOG]
CAT = {c[0]: c[1] for c in CATALOG}
STAGE = {c[0]: c[2] for c in CATALOG}
TEST_P = {c[0]: c[3] for c in CATALOG}
EXISTENCE_INV = {"I1", "I2", "I3", "I4", "I5", "I7", "I8", "I9", "I10"}   # what ALM link-existence checks see


def targets(L, name):
    """Enumerate the admissible targets of a fault class in ledger L."""
    R = [x.id for x in L.of("SwReq")]
    Rp = [x.id for x in L.of("SwReq") if not x.payload.get("derived")]
    Rd = [x.id for x in L.of("SwReq") if x.payload.get("derived")]
    U = [x.id for x in L.of("SwUnit") if x.asil != "QM"]
    Uall = [x.id for x in L.of("SwUnit")]
    QT = [x.id for x in L.of("QualTest")]
    return {
        "dropped_parent_link": Rp, "wrong_asil_attr": U, "dropped_allocation": R,
        "orphan_unit": Uall, "dangling_link": QT, "dropped_qual_test": QT,
        "dropped_safety_req": R, "contradictory_reqs": R, "untestable_req": R,
        "wrong_asil_derived": Rd or R, "inverted_inequality": Uall, "missing_unit_conversion": Uall,
        "wrong_target_link": Rp, "spurious_link": QT, "hallucinated_rationale": Rd or Rp,
    }[name]


def mutate(L, name, tgt, rng_pick=0):
    """Apply fault `name` to target `tgt` in-place. rng_pick selects among alternatives deterministically."""
    a = L.a[tgt]
    if name == "dropped_parent_link":
        a.links = [l for l in a.links if l[0] != "derives-from"]
    elif name == "wrong_asil_attr":
        a.asil = "QM"
    elif name == "dropped_allocation":
        a.links = [l for l in a.links if l[0] != "allocated-to"]
    elif name == "orphan_unit":
        a.links = [l for l in a.links if l[0] != "realizes"]
    elif name == "dangling_link":
        a.links = [("verifies", "R99") if l[0] == "verifies" else l for l in a.links]
    elif name == "dropped_qual_test":
        del L.a[tgt]
        L.a.pop(f"RES-{tgt}", None)
    elif name in ("dropped_safety_req", "contradictory_reqs", "untestable_req",
                  "inverted_inequality", "missing_unit_conversion"):
        a.payload = dict(a.payload, **{"sem_" + name: True})
    elif name == "wrong_asil_derived":
        a.payload = dict(a.payload, sem_wrong_asil_derived=True)   # wrong but internally consistent label
    elif name == "wrong_target_link":
        S = sorted(x.id for x in L.of("SysReq"))
        cur = [t for r, t in a.links if r == "derives-from"]
        alts = [s for s in S if s not in cur]
        new = alts[rng_pick % len(alts)]
        a.links = [("derives-from", new) if l[0] == "derives-from" else l for l in a.links]
    elif name == "spurious_link":
        R = sorted(x.id for x in L.of("SwReq"))
        cur = [t for r, t in a.links if r == "verifies"]
        alts = [r for r in R if r not in cur]
        a.links = a.links + [("verifies", alts[rng_pick % len(alts)])]
    elif name == "hallucinated_rationale":
        if a.payload.get("derived"):
            a.payload = dict(a.payload, rationale="per ISO 26262-6 Annex Z (non-existent clause)")
        else:
            a.payload = dict(a.payload, sem_hallucinated_rationale=True)
    else:
        raise KeyError(name)


def profile(L0, name, tgt, pick=0):
    """Deterministic detection profile of one fault instance on the clean fixture."""
    L = L0.copy()
    base = L0.violations()
    mutate(L, name, tgt, pick)
    V = L.violations()
    fired = {k for k in V if V[k] - base[k]}
    affected = set().union(*[V[k] - base[k] for k in fired]) if fired else set()
    # a deleted artifact counts as a missing (non-compliant) element of A
    if name == "dropped_qual_test":
        affected |= {tgt}
    return {"inv": bool(fired), "alm": bool(fired & EXISTENCE_INV), "fired": sorted(fired),
            "affected": affected}
