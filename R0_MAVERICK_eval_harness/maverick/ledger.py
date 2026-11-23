"""Artifact ledger for the MAVERICK evaluation harness.

Implements the handoff envelope from the MAVERICK paper::

    E = <id, type, ver, ASIL, payload, links, prov, h_prev, h, status>

with SHA-256 hash chaining (``h = SHA-256(canonical(payload) || canonical(links)
|| h_prev)``), a typed link graph (links in {derives-from, allocated-to,
implements, verifies}), the status lifecycle::

    draft -> machine-checked -> human-approved -> baselined

and transitive ``suspect`` propagation: when an upstream artifact changes (a
new version is appended), every transitive descendant is marked ``suspect``
and must be re-verified before the final gate can close.

Only ``baselined`` and non-suspect artifacts are consumable downstream
(``Ledger.consumable``).

Note on simulation honesty: in this harness the Ledger doubles as the
experiment's record store for *all* pipeline configurations. The ablated
element in B1/B2/M-noledger is the *protocol* -- invariant checks
pre-promotion, lifecycle enforcement, hash-chain verification and suspect
propagation -- not the storage itself. See configs.py.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

#: Handoff artifact types. ``SysReq`` is a process *input* (system / safety
#: requirements, pre-V-model) rather than a handoff type, but it is stored in
#: the ledger so upward traceability (I1) has something to point at.
#: ``SwDesign`` is the SWE.3 detailed-design artifact (one per software
#: component); ``CompTest`` is the SWE.5 component-verification test,
#: distinct from the interface integration test (``IntTest``).
ARTIFACT_TYPES = frozenset(
    {
        "SysReq",  # process input, pre-V-model
        "SwReq",  # SWE.1 software requirements
        "SwArch",  # SWE.2 software architecture
        "SwDesign",  # SWE.3 software detailed design (per component)
        "SwUnit",  # SWE.3 detailed design / units
        "UnitTest",  # SWE.4 unit verification
        "CompTest",  # SWE.5 component verification (per unit)
        "IntTest",  # SWE.5 integration verification
        "QualTest",  # SWE.6 qualification verification
        "Result",  # verification result records
    }
)

#: Typed traceability link kinds. ``refines`` connects a detailed design to
#: the architecture element it refines; ``realizes`` connects a unit to its
#: detailed design; ``verifies-design`` connects a test to the detailed
#: design it exercises; ``result-of`` connects a result record back to the
#: test specification it records.
LINK_TYPES = frozenset({"derives-from", "allocated-to", "implements", "verifies",
                        "refines", "realizes", "verifies-design", "result-of"})

#: Status lifecycle; transitions must move exactly one step forward.
STATUS_ORDER = ("draft", "machine-checked", "human-approved", "baselined")

#: ASIL criticality ranking used by invariant I6.
ASIL_RANK = {"QM": 0, "A": 1, "B": 2, "C": 3, "D": 4}

GENESIS = "GENESIS"


@dataclass(frozen=True)
class Link:
    """A typed traceability link from one artifact to another (logical id)."""

    link_type: str
    target_id: str

    def __post_init__(self) -> None:
        if self.link_type not in LINK_TYPES:
            raise ValueError(f"unknown link type: {self.link_type!r}")


@dataclass
class Envelope:
    """Handoff envelope E = <id, type, ver, ASIL, payload, links, prov, h, status>."""

    id: str  # logical artifact id (stable across versions)
    atype: str
    ver: int
    asil: str
    payload: dict = field(default_factory=dict)
    links: List[Link] = field(default_factory=list)
    prov: dict = field(default_factory=dict)  # provenance: author, prompter, model...
    h_prev: str = GENESIS
    h: str = ""
    status: str = "draft"
    suspect: bool = False

    def __post_init__(self) -> None:
        if self.atype not in ARTIFACT_TYPES:
            raise ValueError(f"unknown artifact type: {self.atype!r}")
        if self.asil not in ASIL_RANK:
            raise ValueError(f"unknown ASIL: {self.asil!r}")
        if self.status not in STATUS_ORDER:
            raise ValueError(f"unknown status: {self.status!r}")

    @property
    def key(self) -> str:
        """Unique ledger key for this version."""
        return f"{self.id}#v{self.ver}"

    def canonical(self) -> str:
        """Canonical serialisation hashed into ``h``."""
        body = {
            "payload": self.payload,
            "links": sorted([l.link_type, l.target_id] for l in self.links),
            "h_prev": self.h_prev,
        }
        return json.dumps(body, sort_keys=True, separators=(",", ":"))

    def compute_hash(self) -> str:
        return hashlib.sha256(self.canonical().encode("utf-8")).hexdigest()


class Ledger:
    """Append-only artifact ledger with hash chaining and suspect propagation."""

    def __init__(self) -> None:
        self._envs: Dict[str, Envelope] = {}
        self._order: List[str] = []  # insertion order (hash chain order)
        self._by_logical: Dict[str, List[str]] = {}
        self._reverse: Dict[str, Set[str]] = {}  # target logical id -> source keys
        self.events: List[dict] = []  # audit trail

    # ------------------------------------------------------------------ #
    # basic accessors
    # ------------------------------------------------------------------ #
    @property
    def head_hash(self) -> str:
        return self._envs[self._order[-1]].h if self._order else GENESIS

    def get(self, key: str) -> Envelope:
        return self._envs[key]

    def latest(self, logical_id: str) -> Envelope:
        keys = self._by_logical[logical_id]
        return self._envs[max(keys, key=lambda k: self._envs[k].ver)]

    def latest_map(self) -> Dict[str, Envelope]:
        """Logical id -> latest Envelope."""
        return {lid: self.latest(lid) for lid in self._by_logical}

    def __len__(self) -> int:
        return len(self._envs)

    def __contains__(self, logical_id: str) -> bool:
        return logical_id in self._by_logical

    # ------------------------------------------------------------------ #
    # lifecycle
    # ------------------------------------------------------------------ #
    def append(self, env: Envelope) -> Envelope:
        """Append a new envelope; chains its hash to the ledger head."""
        if env.key in self._envs:
            raise ValueError(f"duplicate envelope key: {env.key}")
        env.h_prev = self.head_hash
        env.h = env.compute_hash()
        env.status = "draft"
        env.suspect = False
        self._envs[env.key] = env
        self._order.append(env.key)
        self._by_logical.setdefault(env.id, []).append(env.key)
        for link in env.links:
            self._reverse.setdefault(link.target_id, set()).add(env.key)
        self.events.append({"event": "append", "key": env.key, "h": env.h})
        return env

    def transition(self, key: str, new_status: str, actor: str = "") -> None:
        """Move an envelope exactly one lifecycle step forward."""
        env = self.get(key)
        i_old = STATUS_ORDER.index(env.status)
        if new_status not in STATUS_ORDER:
            raise ValueError(f"unknown status: {new_status!r}")
        i_new = STATUS_ORDER.index(new_status)
        if i_new != i_old + 1:
            raise ValueError(
                f"illegal transition {env.status!r} -> {new_status!r} for {key}; "
                "lifecycle must advance one step at a time"
            )
        env.status = new_status
        self.events.append(
            {"event": "transition", "key": key, "to": new_status, "actor": actor}
        )

    def promote_to_baselined(self, key: str, approver: str) -> None:
        """Walk an envelope through the remaining lifecycle to baselined."""
        env = self.get(key)
        while env.status != "baselined":
            nxt = STATUS_ORDER[STATUS_ORDER.index(env.status) + 1]
            self.transition(key, nxt, actor=approver)

    def repair_hash(self, key: str) -> None:
        """Recompute hashes after pre-promotion rework.

        Rewrites the hash chain forward from ``key`` so the chain stays
        consistent even when envelopes were appended after ``key`` (e.g. a
        test's Result envelope recorded before the test finished
        processing). Models in-draft rework before promotion; post-baseline
        change must use new_version.
        """
        env = self.get(key)
        if env.status == "baselined":
            raise ValueError("cannot rework a baselined envelope; use new_version")
        idx = self._order.index(key)
        prev = self._envs[self._order[idx - 1]].h if idx > 0 else GENESIS
        for k in self._order[idx:]:
            e = self._envs[k]
            e.h_prev = prev
            e.h = e.compute_hash()
            prev = e.h
        self.events.append({"event": "repair", "key": key,
                            "h": self.get(key).h})

    def new_version(
        self,
        logical_id: str,
        *,
        payload: dict,
        links: List[Link],
        prov: dict,
        asil: Optional[str] = None,
        change_note: str = "",
    ) -> Envelope:
        """Append a new version of an upstream artifact.

        Transitive descendants (latest versions) are marked ``suspect`` and
        must be re-verified before gate closure.
        """
        old = self.latest(logical_id)
        new = Envelope(
            id=logical_id,
            atype=old.atype,
            ver=old.ver + 1,
            asil=asil or old.asil,
            payload=payload,
            links=list(links),
            prov={**prov, "change_note": change_note, "supersedes": old.key},
        )
        self.append(new)
        impacted = self.descendants(logical_id)
        for desc_key in impacted:
            self._envs[desc_key].suspect = True
        self.events.append(
            {
                "event": "new_version",
                "key": new.key,
                "note": change_note,
                "suspect_marked": sorted(impacted),
            }
        )
        return new

    # ------------------------------------------------------------------ #
    # graph queries
    # ------------------------------------------------------------------ #
    def descendants(self, logical_id: str) -> Set[str]:
        """Keys of latest-version artifacts transitively linking to logical_id."""
        seen: Set[str] = set()
        frontier = [logical_id]
        while frontier:
            current = frontier.pop()
            for src_key in self._reverse.get(current, ()):
                src = self._envs[src_key]
                if src.key != self.latest(src.id).key:
                    continue  # only follow latest versions
                if src.key not in seen:
                    seen.add(src.key)
                    frontier.append(src.id)
        return seen

    def consumable(self, logical_id: str) -> bool:
        """True iff the latest version is baselined and not suspect."""
        env = self.latest(logical_id)
        return env.status == "baselined" and not env.suspect

    def verify_chain(self) -> bool:
        """Recompute every hash link; True iff the chain is intact."""
        prev = GENESIS
        for key in self._order:
            env = self._envs[key]
            if env.h_prev != prev:
                return False
            if env.h != env.compute_hash():
                return False
            prev = env.h
        return True
