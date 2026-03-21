"""DSL conformance testing framework."""

from .executor import CaseResult, ConformanceExecutor
from .generator import generate_toml_files
from .models import ConformanceCase, ConformanceFixtures, ScopeOutcome
from .plugin import build_conformance_report, collect_conformance_cases, run_conformance_session
from .stage_invariants import InvariantResult, StageVerification

__all__ = [
    "CaseResult",
    "ConformanceCase",
    "ConformanceExecutor",
    "ConformanceFixtures",
    "InvariantResult",
    "ScopeOutcome",
    "StageVerification",
    "build_conformance_report",
    "collect_conformance_cases",
    "generate_toml_files",
    "run_conformance_session",
]
