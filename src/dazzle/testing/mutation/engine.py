"""Token-level mutation engine.

Applies a fixed catalogue of operator/keyword swaps to a target module — at the TOKEN
level, so strings, docstrings, and comments are never mutated (only real code operators) —
runs a scoped pytest command per mutant, and reports killed / survived / kill-rate. A
*surviving* mutant is behaviour no test constrains; a low kill-rate means coverage without
strength.
"""

from __future__ import annotations

import io
import os
import subprocess
import sys
import tokenize
from dataclasses import dataclass, field
from pathlib import Path

# token-text → replacement. Token-level (not textual) so strings/docstrings/comments are
# never mutated. These are the highest-signal comparison/arithmetic/boolean flips.
_OP_SWAPS: dict[str, str] = {
    "==": "!=",
    "!=": "==",
    ">=": ">",
    "<=": "<",
    ">": ">=",
    "<": "<=",
    "+": "-",
    "-": "+",
}
_NAME_SWAPS: dict[str, str] = {
    "and": "or",
    "or": "and",
    "True": "False",
    "False": "True",
}


class BaselineError(RuntimeError):
    """The scoped tests don't pass on the unmutated source — mutation results would be
    meaningless, so the run is aborted."""


@dataclass(frozen=True)
class Mutant:
    """One single-site operator/keyword swap."""

    line_no: int
    before: str
    after: str


@dataclass
class MutationResult:
    module: str
    total: int
    killed: int
    survivors: list[Mutant] = field(default_factory=list)

    @property
    def kill_rate(self) -> float:
        """Percentage of mutants the tests caught (0.0 when there were no mutants)."""
        return (self.killed / self.total * 100.0) if self.total else 0.0


def generate_mutants(source: str) -> list[tuple[str, Mutant]]:
    """Yield ``(mutated_source, mutant)`` per single operator/keyword swap. Token-level:
    strings, docstrings, and comments are never mutated."""
    lines = source.splitlines(keepends=True)
    out: list[tuple[str, Mutant]] = []
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except tokenize.TokenError:
        return out
    for tok in toks:
        if tok.type == tokenize.OP:
            repl = _OP_SWAPS.get(tok.string)
        elif tok.type == tokenize.NAME:
            repl = _NAME_SWAPS.get(tok.string)
        else:
            repl = None
        if repl is None:
            continue
        (srow, scol), (erow, ecol) = tok.start, tok.end
        if srow != erow:
            continue  # single-line tokens only
        line = lines[srow - 1]
        mutated_line = line[:scol] + repl + line[ecol:]
        if mutated_line == line:
            continue
        mutant_lines = list(lines)
        mutant_lines[srow - 1] = mutated_line
        out.append(("".join(mutant_lines), Mutant(srow, line.strip(), mutated_line.strip())))
    return out


def _tests_pass(pytest_args: list[str], *, python_exe: str = sys.executable) -> bool:
    # PYTHONDONTWRITEBYTECODE: a mutant that is the SAME byte-length as the original
    # (e.g. `+`→`-`, `==`→`!=`) leaves the source mtime unchanged within the filesystem's
    # mtime granularity, so a cached .pyc from the previous run would be re-imported and the
    # mutant would falsely "survive". Suppressing bytecode caching forces every run to read
    # the current source. (Also disables pytest's assertion-rewrite cache, same reason.)
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    proc = subprocess.run(
        [python_exe, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", *pytest_args],
        capture_output=True,
        text=True,
        env=env,
    )
    return proc.returncode == 0


def run_mutation(
    module: Path,
    pytest_args: list[str],
    *,
    python_exe: str = sys.executable,
) -> MutationResult:
    """Mutate ``module`` and report how many mutants ``pytest_args`` kills.

    Raises :class:`BaselineError` if the scoped tests don't pass before mutation. The
    original source is always restored, even on error.
    """
    if not pytest_args:
        raise ValueError("pytest_args must name at least one test target")
    original = module.read_text(encoding="utf-8")
    if not _tests_pass(pytest_args, python_exe=python_exe):
        raise BaselineError(f"baseline tests fail for {module} — fix them before mutating")

    mutants = generate_mutants(original)
    killed = 0
    survivors: list[Mutant] = []
    try:
        for src, mut in mutants:
            module.write_text(src, encoding="utf-8")
            if _tests_pass(pytest_args, python_exe=python_exe):
                survivors.append(mut)  # tests still pass → bug NOT caught
            else:
                killed += 1
    finally:
        module.write_text(original, encoding="utf-8")  # always restore

    return MutationResult(
        module=str(module), total=len(mutants), killed=killed, survivors=survivors
    )
