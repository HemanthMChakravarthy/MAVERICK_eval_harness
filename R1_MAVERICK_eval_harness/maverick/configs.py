"""Pipeline configurations.  Each flag names a mechanism, so the table of
mechanisms in the manuscript (Table II) is generated from this file."""
C = {}
def cfg(name, **kw):
    d = dict(author="llm", inject="llm", ledger="none", critic=False, human="none",
             independence=True, policy=True, tests="independent", self_review=0.0,
             llm_reviewer=False, release_review=False, audit=False, amplification=False,
             correlated=False, dehallucination=False, blocking=True, coverage_loop=True,
             label=name)
    d.update(kw); C[name] = d

cfg("B0", author="human", inject="manual", human="b0", ledger="none", label="B0 manual")
cfg("B1", inject="llm", correlated=True, self_review=1.0, tests="same_agent", release_review=True,
    coverage_loop=False, label="B1 single agent")
cfg("B2", amplification=True, tests="same_agent", release_review=True, coverage_loop=False,
    label="B2 unsup. MAS (neg. control)")
cfg("B3", author="human", inject="human", ledger="alm", human="dp", label="B3 human+ALM")
cfg("B4", ledger="advisory", human="dp", label="B4 LLM+advisory inv.")
cfg("B5", human="dp", audit=True, label="B5 LLM+post-hoc audit")
cfg("B6", tests="exec_feedback", llm_reviewer=True, release_review=True, coverage_loop=False,
    label="B6 SOP-MAS (MetaGPT-like)")
cfg("B7", tests="exec_feedback", llm_reviewer=True, release_review=True, dehallucination=True,
    coverage_loop=False, label="B7 chat-chain (ChatDev-like)")
cfg("B8", tests="exec_feedback", human="self", coverage_loop=False,
    label="B8 conversable+HIL (AutoGen-like)")
cfg("M", ledger="blocking", critic=True, human="dp", label="M MAVERICK")
cfg("M-ledger", ledger="none", critic=True, human="dp", label="M\u2212ledger")
cfg("M-critic", ledger="blocking", critic=False, human="dp", label="M\u2212critic")
cfg("M-policy", ledger="blocking", critic=True, human="dp", policy=False, label="M\u2212policy")
MAIN = ["B0", "B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8", "M", "M-ledger", "M-critic", "M-policy"]
