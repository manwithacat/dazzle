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


# ─────────────────────────────────────────────────────────────────────────────
# Slice 3 (#1494, 3d): `when_empty:` — empty-region self-demote
# ─────────────────────────────────────────────────────────────────────────────

from types import SimpleNamespace  # noqa: E402

from dazzle.core.ir import WhenEmpty  # noqa: E402
from dazzle.page.runtime.when_empty_resolver import resolve_when_empty  # noqa: E402

_WS_DSL = """\
module t
app a "A"
entity Task "Task":
  id: uuid pk
  title: str(100)
workspace ops "Ops":
  recent:
    source: Task
    display: list
{when_empty_line}  all_tasks:
    source: Task
"""


def _ws_region(when_empty_line: str = ""):
    dsl = _WS_DSL.format(when_empty_line=(f"    {when_empty_line}\n" if when_empty_line else ""))
    n, a, t, c, u, frag = parse_dsl(dsl, pathlib.Path("t.dsl"))
    return frag.workspaces[0].regions[0]


class TestWhenEmptyParse:
    def test_unset_is_none(self):
        assert _ws_region().when_empty is None

    def test_explicit_suppress(self):
        assert _ws_region("when_empty: suppress").when_empty == WhenEmpty.SUPPRESS

    def test_explicit_collapse(self):
        assert _ws_region("when_empty: collapse").when_empty == WhenEmpty.COLLAPSE

    def test_explicit_message(self):
        assert _ws_region("when_empty: message").when_empty == WhenEmpty.MESSAGE

    def test_invalid_value_rejected(self):
        with pytest.raises(DazzleError):
            _ws_region("when_empty: vanish")


class TestWhenEmptyResolver:
    """The default-flip: explicit wins; unset adapts to the region's role."""

    def _r(self, **kw):
        base = {"when_empty": None, "display": "list", "aggregates": {}, "empty_message": None}
        base.update(kw)
        return SimpleNamespace(**base)

    def test_explicit_collapse_authoritative(self):
        assert resolve_when_empty(self._r(when_empty=WhenEmpty.COLLAPSE)) == WhenEmpty.COLLAPSE

    def test_explicit_suppress_authoritative(self):
        assert resolve_when_empty(self._r(when_empty=WhenEmpty.SUPPRESS)) == WhenEmpty.SUPPRESS

    def test_unset_defaults_to_message_byte_stable(self):
        # The auto self-demote default-flip is deferred (it breaks the fleet's
        # viewport/interaction gates) — unset always resolves to `message` so
        # existing dashboards are byte-stable. Self-demote is opt-in only.
        assert resolve_when_empty(self._r(display="bar_chart")) == WhenEmpty.MESSAGE
        assert resolve_when_empty(self._r(display="list", aggregates={"n": 1})) == WhenEmpty.MESSAGE
        assert resolve_when_empty(self._r(display="list")) == WhenEmpty.MESSAGE
        assert resolve_when_empty(self._r(display="kanban")) == WhenEmpty.MESSAGE


class TestWhenEmptyRenderSeam:
    """`_build_region_response` turns the resolved mode into native htmx removal
    when the fetch produced no rows."""

    def _resp(self, ir_region, items, hx_target="region-recent-recent"):
        from dazzle.http.runtime.workspace_region_handler import _build_region_response

        ctx = SimpleNamespace(ir_region=ir_region, ctx_region=SimpleNamespace(display="list"))
        fetched = SimpleNamespace(items=items, total=len(items))
        return _build_region_response(ctx, fetched, "<table>body</table>", hx_target)

    def _region(self, **kw):
        base = {
            "when_empty": None,
            "display": "list",
            "aggregates": {},
            "empty_message": None,
            "refresh_interval": None,
        }
        base.update(kw)
        return SimpleNamespace(**base)

    def test_empty_suppress_oob_deletes_wrapper(self):
        resp = self._resp(self._region(when_empty=WhenEmpty.SUPPRESS), items=[])
        body = bytes(resp.body).decode()
        assert 'id="card-recent-recent"' in body
        assert 'hx-swap-oob="delete"' in body
        assert "<table>" not in body  # the empty body is dropped

    def test_empty_collapse_reswap_delete(self):
        resp = self._resp(self._region(when_empty=WhenEmpty.COLLAPSE), items=[])
        assert resp.headers.get("HX-Reswap") == "delete"
        assert bytes(resp.body).decode() == ""

    def test_empty_message_renders_normal_body(self):
        # Primary list, unset → message → the normal typed body (no removal).
        resp = self._resp(self._region(), items=[])
        assert "HX-Reswap" not in resp.headers
        assert "<table>body</table>" in bytes(resp.body).decode()

    def test_nonempty_suppress_renders_normally(self):
        # Suppress only fires on an empty fetch; with rows the body renders.
        resp = self._resp(self._region(when_empty=WhenEmpty.SUPPRESS), items=[{"id": "1"}])
        assert "<table>body</table>" in bytes(resp.body).decode()
        assert "hx-swap-oob" not in bytes(resp.body).decode()
