"""#1399 slice 1 — workspace SSE live push (IR + parser + wiring + renderer)."""

from __future__ import annotations

from pathlib import Path

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.ir.workspaces import WorkspaceSpec


class TestWorkspaceLiveIR:
    def test_live_defaults_false(self) -> None:
        ws = WorkspaceSpec(name="ops")
        assert ws.live is False

    def test_live_can_be_set(self) -> None:
        ws = WorkspaceSpec(name="ops", live=True)
        assert ws.live is True


_LIVE_DSL = """module t
app t "Test"
entity Job "Job":
  id: uuid pk
  status: str(20) = "queued"
workspace ops "Ops":
  live: on
  jobs:
    source: Job
    display: list
    refresh: every 10s
"""

_NOLIVE_DSL = _LIVE_DSL.replace("  live: on\n", "")


def _workspace(dsl: str) -> WorkspaceSpec:
    module = parse_dsl(dsl, Path("test.dsl"))[5]
    return next(w for w in module.workspaces if w.name == "ops")


class TestWorkspaceLiveParse:
    def test_live_on_sets_flag(self) -> None:
        assert _workspace(_LIVE_DSL).live is True

    def test_absent_live_defaults_false(self) -> None:
        assert _workspace(_NOLIVE_DSL).live is False
