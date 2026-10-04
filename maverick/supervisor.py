"""Safety Supervisor: ASIL-indexed gate policy (Table III) and decision rule (Eq. 3)."""
import json
from .ledger import ASIL_RANK

COVERAGE = {"QM": [], "A": ["statement"], "B": ["statement", "branch"], "C": ["branch"], "D": ["mcdc"]}
INDEPENDENCE = {  # gate -> ASIL -> required level (0..3); must be verified against ISO 26262-2
    "H1": {"QM": 0, "A": 0, "B": 0, "C": 1, "D": 2}, "H2": {"QM": 0, "A": 0, "B": 0, "C": 1, "D": 2},
    "H3": {"QM": 0, "A": 0, "B": 0, "C": 0, "D": 1}, "H4": {"QM": 0, "A": 0, "B": 0, "C": 0, "D": 0},
    "H5": {"QM": 0, "A": 0, "B": 0, "C": 1, "D": 2}, "H6": {"QM": 0, "A": 0, "B": 0, "C": 0, "D": 3}}
HUMAN_REQUIRED = lambda gate, asil: not (asil == "QM" and gate in ("H2", "H4", "H5"))

def load_policy(path=None):
    return json.load(open(path)) if path else {"coverage": COVERAGE, "independence": INDEPENDENCE}

class Approval:
    def __init__(self, reviewer, independence, authored_ids=()):
        self.reviewer, self.independence, self.authored = reviewer, independence, set(authored_ids)

class SafetySupervisor:
    def __init__(self, ledger, policy=None, critic=None):
        self.L, self.p, self.critic = ledger, policy or load_policy(), critic   # critic: fn(env)->list[str]
        self.log = []

    def promote(self, env, gate, coverage=None, approval=None, dispositions=None):
        reasons = []
        inv = [v for v in self.L.violations() if v[1].split(":")[0] == env.id]
        if inv: reasons.append(f"Inv:{inv}")
        if gate == "H4":
            need = {"statement": 1.0, "branch": 1.0, "mcdc": 1.0}
            for m in self.p["coverage"][env.asil]:
                if (coverage or {}).get(m, 0) < need[m] and not (coverage or {}).get(f"{m}_justified_gap"):
                    reasons.append(f"Cov:{m}")
        findings = self.critic(env) if self.critic else []
        if findings and not (dispositions and set(findings) <= set(dispositions)):
            reasons.append(f"Crit:undispositioned {findings}")
        if HUMAN_REQUIRED(gate, env.asil):
            if approval is None: reasons.append("Approve:missing")
            else:
                if approval.independence < self.p["independence"][gate][env.asil]: reasons.append("Approve:independence")
                if env.id in approval.authored: reasons.append("Approve:reviewer-is-author")
        ok = not reasons
        if ok: env.status = "baselined"
        self.log.append({"id": env.id, "gate": gate, "asil": env.asil, "promoted": ok, "reasons": reasons})
        return ok, reasons
