#!/usr/bin/env python3
"""Minimal mutation-testing POC (#1342 fuzz-leverage #5).

Measures *test strength* — what fraction of synthetic bugs ("mutants") the tests KILL —
for a single module, as a proxy for "is this code actually pinned by its tests, or just
covered?". Coverage says a line ran; mutation says a wrong version of that line fails a test.

This is a deliberately small, dependency-free harness (mutmut 3.x's baseline pytest
invocation is incompatible with this repo's pytest config + conftest from its `mutants/`
working dir — see the fuzz-harness evaluation). It applies a fixed catalogue of
operator/keyword mutations to the target source — at the TOKEN level, so strings,
docstrings, and comments are never mutated — runs a scoped test command per mutant, and
reports killed / survived / kill-rate. Survivors point at behaviour the tests cover but
don't pin (e.g. an untested boundary or fallback).

Usage:
    python scripts/mutation_poc.py <module.py> -- <pytest args...>

Example (the SSRF-guarded metadata fetcher — 86% kill-rate, the 2 survivors are a
cosmetic error-message fallback and an untested explicit-port path):
    python scripts/mutation_poc.py src/dazzle/back/runtime/auth/saml_metadata.py -- \
        tests/unit/test_saml_metadata.py \
        tests/unit/test_fuzz_small_parsers.py::TestValidateMetadataUrl
"""

from __future__ import annotations

import io
import subprocess
import sys
import tokenize
from dataclasses import dataclass
from pathlib import Path

# token-text → replacement. Token-level (not textual) so we never mutate strings/comments.
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


@dataclass
class _Mutant:
    line_no: int
    before: str
    after: str


def _generate_mutants(source: str) -> list[tuple[str, _Mutant]]:
    """Yield (mutated_source, mutant) per single operator/keyword swap — token-level, so
    strings, docstrings, and comments are never mutated (only real code operators)."""
    lines = source.splitlines(keepends=True)
    out: list[tuple[str, _Mutant]] = []
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
        out.append(("".join(mutant_lines), _Mutant(srow, line.strip(), mutated_line.strip())))
    return out


def _tests_pass(pytest_args: list[str]) -> bool:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", *pytest_args],
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0


def main(argv: list[str]) -> int:
    if "--" not in argv:
        print(__doc__)
        return 2
    sep = argv.index("--")
    targets = argv[:sep]
    pytest_args = argv[sep + 1 :]
    if len(targets) != 1 or not pytest_args:
        print(__doc__)
        return 2

    target = Path(targets[0])
    original = target.read_text(encoding="utf-8")

    # Sanity: the baseline tests must pass before mutating, else results are meaningless.
    if not _tests_pass(pytest_args):
        print("BASELINE FAILED — the scoped tests must pass before mutation.")
        return 1

    mutants = _generate_mutants(original)
    killed = 0
    survivors: list[_Mutant] = []
    try:
        for src, mut in mutants:
            target.write_text(src, encoding="utf-8")
            if _tests_pass(pytest_args):
                survivors.append(mut)  # tests still pass → bug NOT caught
            else:
                killed += 1
    finally:
        target.write_text(original, encoding="utf-8")  # always restore

    total = len(mutants)
    rate = (killed / total * 100) if total else 0.0
    print(f"\nModule: {target}")
    print(f"Mutants: {total}  Killed: {killed}  Survived: {len(survivors)}")
    print(f"Kill rate: {rate:.0f}%")
    if survivors:
        print("\nSurvivors (tests did NOT catch these mutations):")
        for s in survivors:
            print(f"  L{s.line_no}: {s.before!r} → {s.after!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
