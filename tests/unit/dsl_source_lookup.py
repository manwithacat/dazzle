"""Locate example DSL declarations without assuming which module owns them."""

import re
from pathlib import Path

_EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def project_dsl_text(project: str) -> str:
    """Read every DSL module in a project for cross-module text assertions."""
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((_EXAMPLES / project / "dsl").rglob("*.dsl"))
    )


def declaration_block(project: str, kind: str, name: str) -> str:
    """Return one top-level declaration and its indented body."""
    marker = re.compile(rf"^{re.escape(kind)} {re.escape(name)}(?:\s|:)")
    matches: list[str] = []
    for path in sorted((_EXAMPLES / project / "dsl").rglob("*.dsl")):
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        for start, line in enumerate(lines):
            if not marker.match(line):
                continue
            end = start + 1
            while end < len(lines):
                next_line = lines[end]
                if re.match(r"^[A-Za-z_]", next_line):
                    break
                end += 1
            matches.append("".join(lines[start:end]))
    if len(matches) != 1:
        raise ValueError(f"Expected one {kind} {name} in {project}, found {len(matches)}")
    return matches[0]
