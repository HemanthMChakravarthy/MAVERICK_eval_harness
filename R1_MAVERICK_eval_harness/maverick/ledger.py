"""Executable Traceability Ledger: typed artifact graph, hash chain, I1-I11.

Invariant verdicts here are computed by graph queries; they are NOT sampled.
This is the part of the harness that demonstrates that the mechanisms
operate as designed (Type-A evidence in the revised manuscript).
"""
from __future__ import annotations
import copy, hashlib, json
from dataclasses import dataclass, field

ASIL_ORDER = {"QM": 0, "A": 1, "B": 2, "C": 3, "D": 4}
DOWNWARD = {"derives-from": "rev", "allocated-to": "fwd", "refines": "rev", "realizes": "rev"}
# derives-from: child(R) -> parent(S)            => downward edge parent->child
# allocated-to: R -> D                           => downward R->D
# refines:      DD -> D                          => downward D->DD
# realizes:     U -> DD                          => downward DD->U


@dataclass
class Artifact:
    id: str
    type: str                     # SysReq, SwReq, SwArch, SwDesign, SwUnit, UnitTest, CompTest, IntTest, QualTest, Result
    asil: str = "QM"
    kind: str = ""                # for SwArch: component | interface
    payload: dict = field(default_factory=dict)
    links: list = field(default_factory=list)   # list of (relation, target_id)
    ver: int = 1
    h_prev: str = ""
    h: str = ""
    status: str = "baselined"


class Ledger:
    def __init__(self):
        self.a: dict[str, Artifact] = {}

    # ---------------- construction / hash chain ----------------
    def add(self, art: Artifact):
        art.h = self._hash(art)
        self.a[art.id] = art

    @staticmethod
    def _hash(art: Artifact) -> str:
        body = json.dumps({"payload": art.payload, "links": sorted(art.links), "asil": art.asil},
                          sort_keys=True) + art.h_prev
        return hashlib.sha256(body.encode()).hexdigest()

    def revise(self, aid: str, **changes):
        """Create a new version of an artifact (hash-chained) and mark descendants suspect."""
        art = self.a[aid]
        new = copy.deepcopy(art)
        for k, v in changes.items():
            setattr(new, k, v)
        new.ver = art.ver + 1
        new.h_prev = art.h
        new.h = self._hash(new)
        self.a[aid] = new
        for d in self.descendants(aid):
            self.a[d].status = "suspect"
        return new

    def chain_ok(self, art: Artifact) -> bool:
        return art.h == self._hash(art)

    def copy(self) -> "Ledger":
        L = Ledger(); L.a = copy.deepcopy(self.a); return L

    # ---------------- queries ----------------
    def of(self, t, kind=None):
        return [x for x in self.a.values() if x.type == t and (kind is None or x.kind == kind)]

    def valid_targets(self, art, rel, ttype=None):
        out = []
        for r, t in art.links:
            if r == rel and t in self.a and (ttype is None or self.a[t].type in ttype):
                out.append(t)
        return out

    def incoming(self, tid, rel, stype=None):
        return [x.id for x in self.a.values() if (stype is None or x.type in stype)
                and (rel, tid) in x.links]

    def descendants(self, aid):
        """Transitively linked downstream artifacts (V-model direction)."""
        up_rel = {"derives-from", "refines", "realizes", "verifies", "verifies-design", "result-of"}
        out, stack = set(), [aid]
        while stack:
            cur = stack.pop()
            nxt = [x.id for x in self.a.values() for r, t in x.links if t == cur and r in up_rel]
            nxt += [t for r, t in self.a[cur].links if r == "allocated-to" and t in self.a]
            for n in nxt:
                if n not in out and n != aid:
                    out.add(n); stack.append(n)
        return out

    # ---------------- invariants I1-I11 ----------------
    def violations(self) -> dict[str, set]:
        V = {f"I{i}": set() for i in range(1, 12)}
        S, R = self.of("SysReq"), self.of("SwReq")
        comps, ifaces = self.of("SwArch", "component"), self.of("SwArch", "interface")
        DD, U = self.of("SwDesign"), self.of("SwUnit")
        UT, CT, IT, QT = self.of("UnitTest"), self.of("CompTest"), self.of("IntTest"), self.of("QualTest")
        RES = self.of("Result")
        # I1 upward completeness
        for r in R:
            if not self.valid_targets(r, "derives-from", {"SysReq"}):
                if not (r.payload.get("derived") and r.payload.get("rationale")):
                    V["I1"].add(r.id)
        # I2 downward completeness
        for s in S:
            if s.payload.get("alloc_sw", True) and not self.incoming(s.id, "derives-from", {"SwReq"}):
                V["I2"].add(s.id)
        # I3 allocation
        for r in R:
            if not self.valid_targets(r, "allocated-to", {"SwArch"}):
                V["I3"].add(r.id)
        # I4 implementation: unit realizes DD which refines a component
        for u in U:
            ok = False
            for dd in self.valid_targets(u, "realizes", {"SwDesign"}):
                if self.valid_targets(self.a[dd], "refines", {"SwArch"}):
                    ok = True
            if not ok:
                V["I4"].add(u.id)
        # I5 verification
        for r in R:
            if not self.incoming(r.id, "verifies", {"QualTest"}):
                V["I5"].add(r.id)
        for u in U:
            if not self.incoming(u.id, "verifies", {"UnitTest"}):
                V["I5"].add(u.id)
        for i in ifaces:
            if not self.incoming(i.id, "verifies", {"IntTest"}):
                V["I5"].add(i.id)
        for t in QT + UT + IT:   # a verifies link must resolve
            if not self.valid_targets(t, "verifies"):
                V["I5"].add(t.id)
        # I6 ASIL inheritance along downward edges
        for x in self.a.values():
            for rel, t in x.links:
                if rel not in DOWNWARD or t not in self.a:
                    continue
                parent, child = (self.a[t], x) if DOWNWARD[rel] == "rev" else (x, self.a[t])
                if ASIL_ORDER[child.asil] < ASIL_ORDER[parent.asil] and not child.payload.get("asil_decomp_approved"):
                    V["I6"].add(child.id)
        # I7 design verification linkage
        for t in UT + CT:
            if not self.valid_targets(t, "verifies-design", {"SwDesign"}):
                V["I7"].add(t.id)
        # I8 component verification
        for c in comps:
            if not self.incoming(c.id, "verifies", {"CompTest"}):
                V["I8"].add(c.id)
        # I9 result completeness
        for t in UT + CT + IT + QT:
            if not self.incoming(t.id, "result-of", {"Result"}):
                V["I9"].add(t.id)
        # I10 result traceability
        for res in RES:
            if not self.valid_targets(res, "result-of"):
                V["I10"].add(res.id)
        # I11 pass requirement
        for res in RES:
            if res.payload.get("verdict", "pass") != "pass":
                V["I11"].add(res.id)
        return V

    def violating_artifacts(self) -> set:
        out = set()
        for s in self.violations().values():
            out |= s
        return out

    def tc(self) -> float:
        return 1.0 - len(self.violating_artifacts()) / len(self.a)


# ---------------------------------------------------------------- fixtures
def _test_block(L, prefix, n, ttype, verifies, design=None, asil="B"):
    for i in range(n):
        links = [("verifies", verifies[i])]
        if design:
            links.append(("verifies-design", design[i]))
        tid = f"{prefix}{i+1}"
        L.add(Artifact(tid, ttype, asil, links=links))
        L.add(Artifact(f"RES-{tid}", "Result", asil, payload={"verdict": "pass"}, links=[("result-of", tid)]))


def aeb_fixture() -> Ledger:
    """ASIL-B AEB post-processing fixture (Section V-A): 4 S, 8 R, 6 comp + 3 IF, 6 DD, 8 U."""
    L = Ledger()
    for sid, asil in [("S1", "B"), ("S2", "B"), ("S3", "QM"), ("S4", "QM")]:
        L.add(Artifact(sid, "SysReq", asil))
    par = {"R1": "S1", "R2": "S1", "R3": "S2", "R4": "S2", "R5": "S2", "R6": "S4", "R7": "S3"}
    alloc = {"R1": "C1", "R2": "C2", "R3": "C3", "R4": "C4", "R5": "C5", "R6": "C6", "R7": "C6", "R8": "C4"}
    for i in range(1, 9):
        rid = f"R{i}"
        asil = "QM" if rid == "R7" else "B"
        links = [("allocated-to", alloc[rid])]
        payload = {}
        if rid in par:
            links.append(("derives-from", par[rid]))
        else:
            payload = {"derived": True, "rationale": "radar plausibility gating needed for ASIL-B TTC"}
        L.add(Artifact(rid, "SwReq", asil, payload=payload, links=links))
    for i in range(1, 7):
        L.add(Artifact(f"C{i}", "SwArch", "B", kind="component"))
    for i in range(1, 4):
        L.add(Artifact(f"IF{i}", "SwArch", "B", kind="interface"))
    for i in range(1, 7):
        L.add(Artifact(f"DD{i}", "SwDesign", "B", links=[("refines", f"C{i}")]))
    real = {"U1": "DD1", "U2": "DD2", "U3": "DD3", "U4": "DD4", "U5": "DD4", "U6": "DD5", "U7": "DD6", "U8": "DD6"}
    for i in range(1, 9):
        uid = f"U{i}"
        asil = "QM" if uid == "U8" else "B"
        payload = {"asil_decomp_approved": True} if uid == "U8" else {}
        L.add(Artifact(uid, "SwUnit", asil, payload=payload, links=[("realizes", real[uid])]))
    _test_block(L, "UT", 8, "UnitTest", [f"U{i}" for i in range(1, 9)], [real[f"U{i}"] for i in range(1, 9)])
    _test_block(L, "CT", 6, "CompTest", [f"C{i}" for i in range(1, 7)], [f"DD{i}" for i in range(1, 7)])
    _test_block(L, "IT", 3, "IntTest", [f"IF{i}" for i in range(1, 4)])
    _test_block(L, "QT", 8, "QualTest", [f"R{i}" for i in range(1, 9)])
    return L


def steer_fixture() -> Ledger:
    """ASIL-D steering-torque arbitration fixture: 3 S, 5 R, 4 comp + 2 IF, 4 DD, 5 U."""
    L = Ledger()
    for i in range(1, 4):
        L.add(Artifact(f"S{i}", "SysReq", "D"))
    par = {"R1": "S1", "R2": "S1", "R3": "S2", "R4": "S3", "R5": "S3"}
    alloc = {"R1": "C1", "R2": "C2", "R3": "C3", "R4": "C4", "R5": "C4"}
    for i in range(1, 6):
        rid = f"R{i}"
        L.add(Artifact(rid, "SwReq", "D", links=[("derives-from", par[rid]), ("allocated-to", alloc[rid])]))
    for i in range(1, 5):
        L.add(Artifact(f"C{i}", "SwArch", "D", kind="component"))
    for i in range(1, 3):
        L.add(Artifact(f"IF{i}", "SwArch", "D", kind="interface"))
    for i in range(1, 5):
        L.add(Artifact(f"DD{i}", "SwDesign", "D", links=[("refines", f"C{i}")]))
    real = {"U1": "DD1", "U2": "DD2", "U3": "DD3", "U4": "DD4", "U5": "DD4"}
    for i in range(1, 6):
        L.add(Artifact(f"U{i}", "SwUnit", "D", links=[("realizes", real[f"U{i}"])]))
    _test_block(L, "UT", 5, "UnitTest", [f"U{i}" for i in range(1, 6)], [real[f"U{i}"] for i in range(1, 6)], "D")
    _test_block(L, "CT", 4, "CompTest", [f"C{i}" for i in range(1, 5)], [f"DD{i}" for i in range(1, 5)], "D")
    _test_block(L, "IT", 2, "IntTest", [f"IF{i}" for i in range(1, 3)], None, "D")
    _test_block(L, "QT", 5, "QualTest", [f"R{i}" for i in range(1, 6)], None, "D")
    return L
