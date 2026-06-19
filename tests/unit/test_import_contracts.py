"""Framework structural-fitness (B) — import-linter layer contracts.

Locks the framework's layer boundaries (gated absolute on NEW violations; the 2 pre-existing
structural edges — combined_server's composition imports, eventbus_adapter's bridge — and the
transitive MCP/perf SQLite reaches are documented allow-list entries in [tool.importlinter]):
  - core stays backend- and UI-agnostic (the IR/parser/linker stays pure)
  - ui must not reach into the runtime
  - back is Postgres-only (ADR-0008) — no DIRECT sqlite/aiosqlite in back

Reducing an allow-list entry (relocating combined_server, injecting the eventbus deps) only
tightens the ratchet — like every other drift gate.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_layer_import_contracts_hold() -> None:
    lint_imports = Path(sys.executable).parent / "lint-imports"
    if not lint_imports.exists():
        import pytest

        pytest.skip("import-linter (lint-imports) not installed in this env")
    result = subprocess.run(
        [str(lint_imports)],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        "Framework layer import contract(s) broken — a new cross-layer import was added. "
        "Relocate the code across the boundary instead of importing across it (or, if the "
        "edge is genuinely structural, add a documented allow-list entry in "
        "[tool.importlinter]).\n\n" + result.stdout + result.stderr
    )
