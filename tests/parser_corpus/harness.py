"""
Shared test harness for parser corpus tests.

Provides utilities for parsing DSL files and extracting structured outputs
for snapshot testing.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.errors import DazzleError
from dazzle.core.ir import ModuleFragment


class EmitMode(Enum):
    """Output modes for corpus file parsing."""

    AST = "ast"  # Token stream / parse tree (not implemented yet)
    IR = "ir"  # Normalized IR (ModuleFragment)
    DIAG = "diag"  # Diagnostics only (errors/warnings)
    ALL = "all"  # All outputs


@dataclass
class DiagnosticEntry:
    """Structured diagnostic entry for snapshot testing."""

    severity: str  # "error" | "warning"
    error_type: str  # "ParseError", "LinkError", "ValidationError"
    message: str  # Human-readable message
    line: int | None = None  # Line number (1-indexed)
    column: int | None = None  # Column number (1-indexed)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict, excluding None values."""
        d = asdict(self)
        return {k: v for k, v in d.items() if v is not None}


def parse_corpus_file(
    path: Path,
    emit: EmitMode = EmitMode.IR,
) -> dict[str, Any]:
    """
    Parse a corpus file and return structured output.

    Args:
        path: Path to DSL file
        emit: Output mode (IR, DIAG, or ALL)

    Returns:
        Dict with:
        - snapshot_version: int (for versioning)
        - file: str (relative filename)
        - emit_mode: str
        - result: dict (IR) or None if error
        - diagnostics: list[dict] (errors/warnings)
    """
    diagnostics: list[DiagnosticEntry] = []
    result: dict[str, Any] | None = None

    try:
        # Parse DSL file
        module_name, app_name, app_title, app_config, uses, fragment = parse_dsl(
            path.read_text(), path
        )

        # Convert fragment to dict for snapshot
        if emit in (EmitMode.IR, EmitMode.ALL):
            result = _canonicalize_fragment(fragment)

    except DazzleError as e:
        # Capture error as diagnostic
        diag = DiagnosticEntry(
            severity="error",
            error_type=type(e).__name__,
            message=e.message,
            line=e.context.line if e.context else None,
            column=e.context.column if e.context else None,
        )
        diagnostics.append(diag)

    except Exception as e:
        # Unexpected error - still capture for diagnostics
        diag = DiagnosticEntry(
            severity="error",
            error_type="UnexpectedError",
            message=str(e),
        )
        diagnostics.append(diag)

    return {
        "snapshot_version": 1,
        "file": path.name,
        "emit_mode": emit.value,
        "result": result,
        "diagnostics": [d.to_dict() for d in diagnostics],
    }


def _canonicalize_fragment(fragment: ModuleFragment) -> dict[str, Any]:
    """
    Convert ModuleFragment to canonical dict for snapshot comparison.

    - Uses mode="json" for JSON-serializable output
    - Sorts keys for deterministic ordering
    - Excludes None/empty values to reduce noise
    """
    # Get JSON-serializable dict
    raw = fragment.model_dump(mode="json")

    # Canonicalize by sorting keys and removing empty values
    return _sort_keys_recursive(_remove_empty(raw))


def _remove_empty(obj: Any) -> Any:
    """Recursively remove None and empty list/dict values."""
    if isinstance(obj, dict):
        return {
            k: _remove_empty(v)
            for k, v in obj.items()
            if v is not None and v != [] and v != {}
        }
    elif isinstance(obj, list):
        return [_remove_empty(item) for item in obj if item is not None]
    return obj


def _sort_keys_recursive(obj: Any) -> Any:
    """Recursively sort dict keys for deterministic output."""
    if isinstance(obj, dict):
        return {k: _sort_keys_recursive(v) for k, v in sorted(obj.items())}
    elif isinstance(obj, list):
        return [_sort_keys_recursive(item) for item in obj]
    return obj


def parse_streamspec_file(
    path: Path,
    emit: EmitMode = EmitMode.IR,
) -> dict[str, Any]:
    """
    Parse a HLESS StreamSpec corpus file.

    Args:
        path: Path to .streamspec file (or .dsl with stream definitions)
        emit: Output mode

    Returns:
        Same structure as parse_corpus_file but for streams
    """
    diagnostics: list[DiagnosticEntry] = []
    result: dict[str, Any] | None = None

    try:
        # Parse DSL file - streams are part of ModuleFragment
        _, _, _, _, _, fragment = parse_dsl(path.read_text(), path)

        # Extract streams from fragment
        if emit in (EmitMode.IR, EmitMode.ALL):
            streams_data = []
            for stream in fragment.streams:
                stream_dict = stream.model_dump(mode="json")
                streams_data.append(_sort_keys_recursive(_remove_empty(stream_dict)))

            result = {
                "stream_count": len(fragment.streams),
                "streams": streams_data,
            }

    except DazzleError as e:
        diag = DiagnosticEntry(
            severity="error",
            error_type=type(e).__name__,
            message=e.message,
            line=e.context.line if e.context else None,
            column=e.context.column if e.context else None,
        )
        diagnostics.append(diag)

    except Exception as e:
        diag = DiagnosticEntry(
            severity="error",
            error_type="UnexpectedError",
            message=str(e),
        )
        diagnostics.append(diag)

    return {
        "snapshot_version": 1,
        "file": path.name,
        "emit_mode": emit.value,
        "result": result,
        "diagnostics": [d.to_dict() for d in diagnostics],
    }
