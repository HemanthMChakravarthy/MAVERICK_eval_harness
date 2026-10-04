# MAVERICK evaluation harness

This harness implements Sections III–V of the paper so you can produce the real numbers for Table V.
`selftest.py` checks the harness on a made-up example. Its output is **not** experimental data.

| Module | Paper element |
|---|---|
| ledger.py | Handoff envelope with version hashes (Eq. 1), marking dependent artifacts as suspect after a change, invariants C1–C6, TC (Eq. 2) |
| supervisor.py | Gate policy (Table III, which you can change in config) and the promote() rule (Eq. 3) |
| agents.py | Agent classes for RA, AA, DCA, CA, TSA-I and TSA-Q. Plug in your own LLM client and parse() |
| seeding.py | Fault list for RQ2 and the leakage metric |
| stats.py | Median with 95% bootstrap confidence interval, and Wilcoxon tests with Holm correction |

## What you still need to supply to fill in Table V
1. Your frozen system requirements and safety requirements (N_S, N_F), plus your item definition, hazard analysis (HARA) and ASIL assignment.
2. An LLM client (on-premise if your requirements are confidential). Record the model version.
3. Configurations B1, B2, M and the three ablations, each run at least 10 times with logged seeds. B0 is done manually by engineers.
4. A coverage tool on the generated C code, feeding results into supervisor.promote(..., "H4", coverage=...).
5. Human reviewers at gates H1–H6. Log minutes spent per artifact and NASA-TLX workload ratings.
6. Semantic faults (inverted inequality, missing unit conversion). These are caught by running tests or by human review, not by the graph checks.
7. Certified ASPICE assessors who rate the evidence blind (N/P/L/F).
8. Before you run anything, check the INDEPENDENCE and COVERAGE tables in supervisor.py against your licensed ISO 26262 text.
