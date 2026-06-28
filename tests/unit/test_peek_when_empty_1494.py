"""#1494 (UX-maturity 2c/3d) — `peek:` + `when_empty:` declarative-over-htmx-4.

Slice 1: the `peek:` DSL surface — IR field with `None` as the true-unset signal
(`SurfaceSpec.peek` — `None` distinct from explicit `peek: off`), parser keyword,
and the right-by-default resolver (`resolve_peek_mode`, default `off` this slice
→ byte-stable). Render + the default-flip land in later slices.
"""

import pathlib

import pytest

from dazzle.core.errors import DazzleError
from dazzle.core.ir import ModuleIR, PeekMode
from dazzle.core.ir.surfaces import SurfaceSpec
from dazzle.core.linker import build_appspec
from dazzle.core.parser import parse_dsl
from dazzle.page.runtime.peek_resolver import resolve_peek_mode

_DSL = """\
module t
app a "A"
entity Task "Task":
  id: uuid pk
  title: str(100)
surface task_list "Tasks":
  uses entity Task
  mode: list
{peek_line}  section main:
    field title "Title"
"""


def _surface(peek_line: str = "") -> SurfaceSpec:
    dsl = _DSL.format(peek_line=(f"  {peek_line}\n" if peek_line else ""))
    n, a, t, c, u, frag = parse_dsl(dsl, pathlib.Path("t.dsl"))
    spec = build_appspec(
        [
            ModuleIR(
                name=n or "t",
                file=pathlib.Path("t.dsl"),
                app_name=a,
                app_title=t,
                app_config=c,
                uses=u,
                fragment=frag,
            )
        ],
        n or "t",
    )
    return next(s for s in spec.surfaces if s.name == "task_list")


class TestPeekIR:
    def test_default_is_none_unset(self):
        # A fresh SurfaceSpec is unset (None) — distinct from explicit peek: off.
        s = SurfaceSpec(name="s", mode="list")
        assert s.peek is None

    def test_unset_peek_stripped_from_dump(self):
        # None peek is excluded by exclude_none so unset surfaces don't churn the
        # corpus snapshot; an explicit value serialises.
        s = SurfaceSpec(name="s", mode="list")
        assert s.model_dump(exclude_none=True).get("peek") is None
        explicit = SurfaceSpec(name="s", mode="list", peek=PeekMode.EXPAND)
        assert explicit.model_dump()["peek"] == "expand"


class TestPeekParser:
    def test_unset_when_no_clause(self):
        s = _surface()
        assert s.peek is None  # author wrote nothing

    @pytest.mark.parametrize(
        ("clause", "expected"),
        [
            ("peek: expand", PeekMode.EXPAND),
            ("peek: slide_over", PeekMode.SLIDE_OVER),
            ("peek: off", PeekMode.OFF),
        ],
    )
    def test_explicit_value_sets_mode(self, clause, expected):
        s = _surface(clause)
        assert s.peek is expected  # non-None → authoritative (incl. off)

    def test_unknown_value_is_parse_error(self):
        with pytest.raises(DazzleError):
            _surface("peek: sideways")


class TestPeekResolver:
    def test_explicit_value_wins_including_off(self):
        assert resolve_peek_mode(_surface("peek: expand")) is PeekMode.EXPAND
        assert resolve_peek_mode(_surface("peek: slide_over")) is PeekMode.SLIDE_OVER
        assert resolve_peek_mode(_surface("peek: off")) is PeekMode.OFF

    def test_unset_resolves_off_this_slice(self):
        # Slice 1: unset → off (byte-stable). Slice 4 flips this to expand when
        # the entity has a detail surface.
        assert resolve_peek_mode(_surface()) is PeekMode.OFF


# --- peek: expand render on the converged substrate row-core (#1505 Phase 4) ---


def _peek_row(peek: str = "off", *, drill: bool = True) -> str:
    from dazzle.render.fragment.primitives import RowCapabilities
    from dazzle.render.fragment.renderer._data_row import render_data_row

    caps = RowCapabilities(peek=peek, drill=drill)
    return render_data_row(
        ({"key": "title", "type": "str"},),
        {"id": "abc-123", "title": "x"},
        caps,
        entity_name="Task",
        api_endpoint="/api/tasks",
        detail_url_template="/tasks/{id}",
    )


class TestPeekExpandRender:
    """`peek: expand` renders a chevron + hidden detail-body panel on the
    converged `render_data_row` core (#1505 P4 / #1494 2c)."""

    def test_expand_emits_chevron_to_peek_partial(self):
        html = _peek_row("expand")
        assert "dz-tr-peek-toggle" in html
        assert 'hx-get="/tasks/abc-123?peek=1"' in html
        assert 'aria-expanded="false"' in html
        assert 'id="peek-content-abc-123"' in html
        assert 'hx-target="#peek-content-abc-123"' in html

    def test_expand_emits_hidden_panel_row(self):
        html = _peek_row("expand")
        assert 'id="peek-abc-123"' in html
        assert "dz-tr-peek-panel" in html
        assert "hidden" in html
        assert 'colspan="2"' in html  # 1 visible column + actions cell

    def test_off_has_no_chevron_or_panel(self):
        html = _peek_row("off")
        assert "dz-tr-peek-toggle" not in html
        assert "dz-tr-peek-panel" not in html

    def test_off_is_byte_identical_to_default(self):
        # caps.peek defaults to "off", so an explicit off is byte-identical to
        # not requesting peek — keeps the fleet byte-stable.
        from dazzle.render.fragment.primitives import RowCapabilities
        from dazzle.render.fragment.renderer._data_row import render_data_row

        args = (({"key": "title", "type": "str"},), {"id": "r1", "title": "x"})
        kw = {
            "entity_name": "Task",
            "api_endpoint": "/api/tasks",
            "detail_url_template": "/tasks/{id}",
        }
        explicit_off = render_data_row(*args, RowCapabilities(peek="off", drill=True), **kw)
        default = render_data_row(*args, RowCapabilities(drill=True), **kw)
        assert explicit_off == default

    def test_peek_requires_detail_surface(self):
        # The chevron lives inside the drill block — peek with no detail URL is
        # inert (nothing to peek at).
        html = _peek_row("expand", drill=False)
        assert "dz-tr-peek-toggle" not in html
