"""MAVERICK evaluation harness.

Simulates the multi-agent LLM orchestration pipeline for ASPICE SWE.1-SWE.6
from the MAVERICK paper and compares it against baselines and ablations.

Default mode uses a *simulated* LLM backend (seeded defect injection) and
makes no network calls. See README.md for assumptions and limitations.
"""

__version__ = "2.0.0"

from .ledger import ARTIFACT_TYPES, LINK_TYPES, STATUS_ORDER, Envelope, Ledger, Link
from .configs import CONFIGS, PipelineConfig, get_config

__all__ = [
    "__version__",
    "ARTIFACT_TYPES",
    "LINK_TYPES",
    "STATUS_ORDER",
    "Envelope",
    "Ledger",
    "Link",
    "CONFIGS",
    "PipelineConfig",
    "get_config",
]
