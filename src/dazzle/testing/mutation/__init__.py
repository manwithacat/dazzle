"""Mutation testing — measures test *strength* (do tests fail when code is subtly
broken?), the complement to coverage and fuzzing. Graduated from the #1342 fuzz-leverage
POC. See ``docs/proposals/mutation-audit-findings.md``.

Token-level operator/keyword mutation (strings, docstrings, comments are never mutated),
dependency-free (mutmut 3.x is incompatible with this repo's pytest config)."""

from dazzle.testing.mutation.engine import (
    BaselineError,
    Mutant,
    MutationResult,
    generate_mutants,
    run_mutation,
)
from dazzle.testing.mutation.targets import (
    SECURITY_TARGETS,
    MutationTarget,
)

__all__ = [
    "BaselineError",
    "Mutant",
    "MutationResult",
    "MutationTarget",
    "SECURITY_TARGETS",
    "generate_mutants",
    "run_mutation",
]
