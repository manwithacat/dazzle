"""DSL conformance testing framework."""

from .generator import generate_toml_files
from .models import ConformanceCase, ConformanceFixtures, ScopeOutcome
from .plugin import build_conformance_report, collect_conformance_cases

__all__ = [
    "ConformanceCase",
    "ConformanceFixtures",
    "ScopeOutcome",
    "collect_conformance_cases",
    "build_conformance_report",
    "generate_toml_files",
]
