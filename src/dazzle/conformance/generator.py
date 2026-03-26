"""TOML file generator for conformance test cases.

Writes one TOML file per entity into the output directory.
Uses manual TOML formatting to avoid external dependencies.
"""

from collections import defaultdict
from pathlib import Path
from typing import Any

from .models import ConformanceCase, ScopeOutcome

_HEADER = "# AUTO-GENERATED — do not edit. Regenerate with: dazzle conformance generate\n"

_SCOPE_TYPE_KEYS = [o.value for o in ScopeOutcome]


def _escape_toml_string(value: str) -> str:
    """Return value as a quoted TOML basic string."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{escaped}"'


def _format_inline_table(mapping: dict[str, Any]) -> str:
    """Format a dict as a TOML inline table { k = v, ... }."""
    parts = []
    for k, v in mapping.items():
        if isinstance(v, str):
            parts.append(f"{k} = {_escape_toml_string(v)}")
        else:
            parts.append(f"{k} = {v}")
    return "{ " + ", ".join(parts) + " }"


def _build_entity_toml(entity_name: str, cases: list[ConformanceCase]) -> str:
    """Render a single entity's TOML content."""
    lines: list[str] = [_HEADER, ""]

    # [entity]
    lines.append("[entity]")
    lines.append(f"name = {_escape_toml_string(entity_name)}")
    lines.append("")

    # [coverage]
    scope_counts: dict[str, int] = defaultdict(int)
    for case in cases:
        st = case.scope_type.value if hasattr(case.scope_type, "value") else str(case.scope_type)
        scope_counts[st] += 1

    # Only include scope types that are present, but order by canonical enum order
    scope_table_parts: dict[str, int] = {}
    for key in _SCOPE_TYPE_KEYS:
        if key in scope_counts:
            scope_table_parts[key] = scope_counts[key]

    lines.append("[coverage]")
    lines.append(f"total_cases = {len(cases)}")
    lines.append(f"scope_types = {_format_inline_table(scope_table_parts)}")
    lines.append("")

    # [[cases]]
    for case in cases:
        lines.append("[[cases]]")
        lines.append(f"persona = {_escape_toml_string(case.persona)}")
        lines.append(f"operation = {_escape_toml_string(case.operation)}")
        lines.append(f"expected_status = {case.expected_status}")
        if case.expected_rows is not None:
            lines.append(f"expected_rows = {case.expected_rows}")
        if case.row_target:
            lines.append(f"row_target = {_escape_toml_string(case.row_target)}")
        st = case.scope_type.value if hasattr(case.scope_type, "value") else str(case.scope_type)
        lines.append(f"scope_type = {_escape_toml_string(st)}")
        lines.append(f"description = {_escape_toml_string(case.description)}")
        lines.append("")

    return "\n".join(lines)


def generate_toml_files(
    cases: list[ConformanceCase],
    output_dir: Path,
) -> list[Path]:
    """Write one TOML file per entity into output_dir.

    Args:
        cases: Conformance cases from derive_conformance_cases() or
               collect_conformance_cases().
        output_dir: Directory to write TOML files into. Created if absent.

    Returns:
        List of Path objects for the files written.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Group by entity
    by_entity: dict[str, list[ConformanceCase]] = defaultdict(list)
    for case in cases:
        by_entity[case.entity].append(case)

    written: list[Path] = []
    for entity_name in sorted(by_entity):
        entity_cases = by_entity[entity_name]
        content = _build_entity_toml(entity_name, entity_cases)
        out_path = output_dir / f"{entity_name}.toml"
        out_path.write_text(content, encoding="utf-8")
        written.append(out_path)

    return written
