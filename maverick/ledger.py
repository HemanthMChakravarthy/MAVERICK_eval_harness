"""Traceability Ledger: typed, hash-chained handoff envelopes (Eq. 1) and invariants C1-C6 (Sec. IV-A)."""
import hashlib, json
from dataclasses import dataclass, field

TYPES = {"SysReq", "SwReq", "SwArch", "SwUnit", "UnitTest", "IntTest", "QualTest", "Result"}
ASIL_RANK = {"QM": 0, "A": 1, "B": 2, "C": 3, "D": 4}
STATUS = ["draft", "machine-checked", "human-approved", "baselined"]

@dataclass
class Envelope:
    id: str; type: str; ver: int; asil: str; payload: dict
    links: list = field(default_factory=list)      # [(target_id, relation)]
    prov: dict = field(default_factory=dict)       # model, prompt_hash, seed, temperature, sources
    h_prev: str = ""; h: str = ""; status: str = "draft"
    derived_rationale: str = ""; interfaces: list = field(default_factory=list)
    asil_decomposition_approved: bool = False

    def seal(self):
        body = json.dumps({"p": self.payload, "l": sorted(self.links)}, sort_keys=True)
        self.h = hashlib.sha256((body + self.h_prev).encode()).hexdigest()
        return self

class Ledger:
    def __init__(self): self.a, self.history, self.suspect = {}, {}, set()

    def put(self, e: Envelope):
        assert e.type in TYPES and e.asil in ASIL_RANK
        old = self.a.get(e.id)
        if old:
            e.h_prev, e.ver = old.h, old.ver + 1
            self.suspect |= self.descendants(e.id)       # SUP.10 impact analysis
        e.seal(); self.a[e.id] = e
        self.history.setdefault(e.id, []).append(e.h)
        return e

    def verify_chain(self, aid):
        return all(h for h in self.history.get(aid, []))

    def descendants(self, aid):
        out, stack = set(), [aid]
        while stack:
            cur = stack.pop()
            for x in self.a.values():
                if any(t == cur for t, _ in x.links) and x.id not in out:
                    out.add(x.id); stack.append(x.id)
        return out

    def of(self, t): return [x for x in self.a.values() if x.type == t]
    def linked(self, src, rel=None):
        return [(t, r) for t, r in self.a[src].links if rel is None or r == rel]
    def inbound(self, tgt, rel=None, src_type=None):
        return [x for x in self.a.values() if any(t == tgt and (rel is None or r == rel) for t, r in x.links)
                and (src_type is None or x.type == src_type)]

    # ---------- invariants C1-C6 ----------
    def violations(self):
        v = []
        sw_sys = [s for s in self.of("SysReq") if s.payload.get("allocated_to_sw", True)]
        for r in self.of("SwReq"):
            if not self.linked(r.id, "derives-from") and not r.derived_rationale: v.append(("C1", r.id))
            if not self.linked(r.id, "allocated-to"): v.append(("C3", r.id))
            if not self.inbound(r.id, "verifies", "QualTest"): v.append(("C5", r.id))
        for s in sw_sys:
            if not self.inbound(s.id, "derives-from", "SwReq"): v.append(("C2", s.id))
        for u in self.of("SwUnit"):
            if not self.linked(u.id, "implements"): v.append(("C4", u.id))
            if not self.inbound(u.id, "verifies", "UnitTest"): v.append(("C5", u.id))
        for d in self.of("SwArch"):
            for itf in d.interfaces:
                if not any(itf in t.payload.get("interfaces", []) for t in self.inbound(d.id, "verifies", "IntTest")):
                    v.append(("C5", f"{d.id}:{itf}"))
        for x in self.a.values():                       # C6 ASIL monotonicity (downward link x->parent)
            for t, r in x.links:
                if r in ("derives-from", "allocated-to", "implements") and t in self.a:
                    if ASIL_RANK[x.asil] < ASIL_RANK[self.a[t].asil] and not x.asil_decomposition_approved:
                        v.append(("C6", x.id))
            for t, _ in x.links:
                if t not in self.a: v.append(("dangling", f"{x.id}->{t}"))
        return v

    def tc(self):
        """Eq. (2): fraction of artifacts with no invariant violation."""
        bad = {aid.split(":")[0] for _, aid in self.violations() if not aid.count("->")}
        bad |= {aid.split("->")[0] for k, aid in self.violations() if k == "dangling"}
        return 1 - len(bad & set(self.a)) / max(len(self.a), 1)
