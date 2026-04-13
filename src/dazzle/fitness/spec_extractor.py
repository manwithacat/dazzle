"""Spec extractor — reads spec.md and produces Capability records.

v1 Task 10 pre-creation: this file currently defines only the
``Capability`` dataclass so that ``independence.py`` and
``cross_check.py`` can import it without circular dependencies. Task 8
will expand this module with ``extract_spec_capabilities()`` (LLM-backed
spec.md parsing).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Capability:
    """One capability asserted in the spec (persona + action).

    ``capability`` is a short imperative phrase ("triage incoming ticket").
    ``persona`` is the role name from the spec ("support_agent"). Both are
    compared case-insensitively downstream.
    """

    capability: str
    persona: str
