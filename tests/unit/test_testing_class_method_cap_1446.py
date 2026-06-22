"""#1446: per-class method-count ratchet for the agent-E2E harness.

The `DazzleClient` / `TestRunner` god classes accreted every concern in their domain
(each new capability added as one more method rather than a collaborator). #1446 split
`DazzleClient` (25 → 14 methods) into `DataGenerator`, `CleanupManager`, and
`EntityClient` collaborators. This gate freezes that win and ratchets the rest down:
each class's method count may only **shrink** below its cap. A class that regrows past
its cap fails here — the fix is to extract a collaborator, not raise the cap.

Both god classes now meet the issue's ~15 done-criteria: `DazzleClient` is 14
(DataGenerator/CleanupManager/EntityClient extracted) and `TestRunner` is 9 (the
`_execute_*_step` ladder extracted to `StepExecutor`, which carries the cohesive
handler collection and is capped separately).
"""

from __future__ import annotations

import ast
from pathlib import Path

_TESTING = Path(__file__).resolve().parents[2] / "src" / "dazzle" / "testing"

# class name → max methods. Only shrinks. Adding a method to a capped class must be
# offset by extracting a collaborator (the #1446 lesson), not by bumping the number.
_CAPS: dict[str, int] = {
    "DazzleClient": 15,  # done-criteria (currently 14)
    "TestRunner": 12,  # done-criteria (currently 9 — orchestration only)
    "EntityClient": 8,  # currently 6
    "CleanupManager": 8,  # currently 6
    "DataGenerator": 4,  # currently 2
    "StepExecutor": 40,  # the cohesive _execute_*_step handler collection (currently 39)
}

_FILES = {
    "DazzleClient": "test_runner.py",
    "TestRunner": "test_runner.py",
    "EntityClient": "entity_client.py",
    "CleanupManager": "cleanup_manager.py",
    "DataGenerator": "data_generator.py",
    "StepExecutor": "step_executor.py",
}


def _method_count(file_name: str, class_name: str) -> int | None:
    tree = ast.parse((_TESTING / file_name).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return sum(
                1 for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            )
    return None


def test_harness_classes_within_method_cap() -> None:
    offenders: list[str] = []
    for cls, cap in _CAPS.items():
        count = _method_count(_FILES[cls], cls)
        assert count is not None, f"{cls} not found in {_FILES[cls]} — update this gate"
        if count > cap:
            offenders.append(f"{cls} has {count} methods (cap {cap})")
    assert not offenders, (
        "Agent-E2E harness class regrew past its #1446 method cap. Extract a collaborator "
        "(the god-class fix), don't raise the cap:\n  " + "\n  ".join(offenders)
    )
