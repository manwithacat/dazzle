"""#1392 item 3 P3 — the emitted-target build gate (E_DEAD_EMIT_TARGET).

DSL `emits:` resolves against the surface registry; `# dazzle:emits` resolves against
the mounted-route set. A dead target is a build error.
"""

from __future__ import annotations

from pathlib import Path

from dazzle.back.runtime.route_overrides import RouteOverrideDescriptor, verify_emits_paths
from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.ir import ModuleIR
from dazzle.core.linker import build_appspec
from dazzle.core.validation.ux import validate_emits_targets


def _appspec(dsl: str):
    n, a, t, c, u, frag = parse_dsl(dsl, Path("t.dsl"))
    return build_appspec(
        [
            ModuleIR(
                name=n or "t",
                file=Path("t.dsl"),
                app_name=a,
                app_title=t,
                app_config=c,
                uses=u,
                fragment=frag,
            )
        ],
        "t",
    )


_BASE = """module t
app t "T"
entity Task "Task":
  id: uuid pk
  title: str(80)
surface task_detail "Detail":
  uses entity Task
  mode: view
  section main:
    field title "Title"
surface task_board "Board":
  uses entity Task
  mode: custom
  render: kanban_viewer
  emits: [{targets}]
"""


class TestSurfaceEmitsGate:
    def test_resolvable_emits_clean(self) -> None:
        errs, _ = validate_emits_targets(_appspec(_BASE.format(targets="task_detail")))
        assert errs == []

    def test_dead_emit_target_errors(self) -> None:
        errs, _ = validate_emits_targets(_appspec(_BASE.format(targets="nonexistent_surface")))
        assert any("nonexistent_surface" in e and "E_DEAD_EMIT_TARGET" in e for e in errs), errs

    def test_undeclared_emits_unconstrained(self) -> None:
        dsl = """module t
app t "T"
entity Task "Task":
  id: uuid pk
  title: str(80)
surface task_detail "Detail":
  uses entity Task
  mode: view
  section main:
    field title "Title"
"""
        assert validate_emits_targets(_appspec(dsl)) == ([], [])


class TestRouteOverrideEmitsGate:
    def test_override_emits_path_resolves(self) -> None:
        o = RouteOverrideDescriptor(
            method="GET",
            path="/app/board",
            source_path=Path("routes/board.py"),
            handler=lambda request: None,
            emits_paths=("/app/tasks/{id}",),
        )
        assert verify_emits_paths([o], {"/app/board", "/app/tasks/{id}"}) == []

    def test_override_dead_emit_path_violates(self) -> None:
        o = RouteOverrideDescriptor(
            method="GET",
            path="/app/board",
            source_path=Path("routes/board.py"),
            handler=lambda request: None,
            emits_paths=("/app/gone",),
        )
        v = verify_emits_paths([o], {"/app/board"})
        assert len(v) == 1 and "/app/gone" in v[0] and "E_DEAD_EMIT_TARGET" in v[0]
