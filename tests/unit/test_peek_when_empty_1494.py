"""#1494 (UX-maturity 2c/3d) — `peek:` + `when_empty:` declarative-over-htmx-4.

Covers the `peek:` DSL surface (IR field with `None` as the true-unset signal,
parser keyword), the `resolve_peek_mode` default-flip (unset + detail surface →
`expand`, the 2c level-4 move), the `expand` render on the converged row-core,
the `when_empty:` region self-demote, and the Slice-2 click-to-edit toggle in the
peek panel (`TestPeekClickToEdit`).
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

    def test_unset_flips_to_expand_when_entity_has_detail(self):
        # The default-flip (#1494, 2c → level 4): an unset surface whose entity
        # has a detail surface resolves to `expand` (action-proximate detail by
        # default). The entity arg is the detail-surface signal.
        assert resolve_peek_mode(_surface(), entity=object()) is PeekMode.EXPAND

    def test_unset_resolves_off_without_detail(self):
        # No detail target (entity is None) → off: there is no detail body to
        # expand into, so the row degrades to plain drill.
        assert resolve_peek_mode(_surface(), entity=None) is PeekMode.OFF
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

    def test_explicit_value_authoritative(self):
        assert resolve_when_empty(self._r(when_empty=WhenEmpty.COLLAPSE)) == WhenEmpty.COLLAPSE
        assert resolve_when_empty(self._r(when_empty=WhenEmpty.SUPPRESS)) == WhenEmpty.SUPPRESS
        assert resolve_when_empty(self._r(when_empty=WhenEmpty.MESSAGE)) == WhenEmpty.MESSAGE

    def test_author_empty_message_keeps_message(self):
        # An author who wrote an empty_message opted into a visible empty-state.
        r = self._r(display="bar_chart", aggregates={"n": 1}, empty_message="No data")
        assert resolve_when_empty(r) == WhenEmpty.MESSAGE

    def test_supporting_widget_collapses_by_default(self):
        # The default-flip: empty supporting widgets self-collapse to header-only
        # (card stays in the grid). Charts/metrics + any aggregate region.
        assert resolve_when_empty(self._r(display="bar_chart")) == WhenEmpty.COLLAPSE
        assert resolve_when_empty(self._r(display="metrics")) == WhenEmpty.COLLAPSE
        assert (
            resolve_when_empty(self._r(display="list", aggregates={"n": 1})) == WhenEmpty.COLLAPSE
        )

    def test_primary_content_keeps_message(self):
        # Primary content (list/kanban/…) keeps a "nothing here yet" message.
        assert resolve_when_empty(self._r(display="list")) == WhenEmpty.MESSAGE
        assert resolve_when_empty(self._r(display="kanban")) == WhenEmpty.MESSAGE

    def test_suppress_is_never_the_default(self):
        # Full card removal is explicit opt-in only — never a default-flip outcome.
        for display in ("bar_chart", "metrics", "list", "kanban"):
            assert resolve_when_empty(self._r(display=display)) != WhenEmpty.SUPPRESS


class TestWhenEmptyRenderSeam:
    """`_build_region_response` turns the resolved mode into native htmx removal
    when the fetch produced no rows."""

    def _resp(self, ir_region, items, hx_target="region-recent-recent", is_added_card=False):
        from dazzle.http.runtime.workspace_region_handler import _build_region_response

        ctx = SimpleNamespace(ir_region=ir_region, ctx_region=SimpleNamespace(display="list"))
        fetched = SimpleNamespace(items=items, total=len(items))
        return _build_region_response(
            ctx, fetched, "<table>body</table>", hx_target, is_added_card=is_added_card
        )

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

    def test_empty_supporting_widget_collapses_by_default(self):
        # Unset chart/metric → default-flip → collapse (HX-Reswap: delete body).
        resp = self._resp(self._region(display="bar_chart"), items=[])
        assert resp.headers.get("HX-Reswap") == "delete"

    def test_added_card_exempt_from_auto_collapse(self):
        # A picker-added card (?added=1) skips the auto default-flip — it shows
        # its empty-state, never an immediate self-demote.
        resp = self._resp(self._region(display="bar_chart"), items=[], is_added_card=True)
        assert "HX-Reswap" not in resp.headers
        assert "<table>body</table>" in bytes(resp.body).decode()

    def test_added_card_still_honours_explicit_when_empty(self):
        # An explicit author `when_empty:` wins even for an added card.
        resp = self._resp(
            self._region(display="bar_chart", when_empty=WhenEmpty.COLLAPSE),
            items=[],
            is_added_card=True,
        )
        assert resp.headers.get("HX-Reswap") == "delete"


# --- Slice 2: click-to-edit toggle in the peek panel (#1494) ------------------


class TestPeekClickToEdit:
    """The peek panel toggles view⇄edit in place: the Edit affordance hx-gets a
    content-only edit form into the panel cell (`#peek-content-{id}`); an inline
    Cancel re-fetches the read-only view back. Non-peek detail/edit render is
    unchanged (nav Link / page form with `<h1>`)."""

    def _adapter(self):
        from dazzle.http.runtime.renderers.fragment_adapter import FragmentSurfaceAdapter

        return FragmentSurfaceAdapter()

    def _render(self, fragment) -> str:
        from dazzle.render.fragment import FragmentRenderer

        return FragmentRenderer().render(fragment)

    def _edit_form(self, *, peek: bool):
        import types

        from dazzle.core.ir.surfaces import SurfaceMode

        surf = types.SimpleNamespace(
            name="task_edit", title="Edit Task", entity_ref="Task", mode=None
        )
        ctx = {
            "fields": [{"name": "title", "label": "Title", "type": "text", "value": "x"}],
            "action": "/api/tasks/abc",
            "method": "PUT",
        }
        if peek:
            ctx |= {"peek": True, "item_id": "abc", "cancel_url": "/app/tasks/abc"}
        return self._render(self._adapter()._build_form(surf, ctx, mode=SurfaceMode.EDIT))

    def test_peek_edit_form_is_content_only(self):
        # No page-level <h1> — the form swaps into the inline panel, not a page.
        assert "<h1" not in self._edit_form(peek=True)

    def test_non_peek_edit_form_keeps_page_heading(self):
        assert "<h1" in self._edit_form(peek=False)

    def test_peek_edit_form_has_inline_cancel_back_to_view(self):
        html = self._edit_form(peek=True)
        assert "Cancel" in html
        # Cancel re-fetches the content-only view into the same panel cell.
        assert 'hx-get="/app/tasks/abc?peek=1"' in html
        assert 'hx-target="#peek-content-abc"' in html

    def _edit_action(self, *, peek: bool):
        ctx = {"edit_url": "/app/tasks/abc/edit", "entity_name": "Task"}
        if peek:
            ctx |= {"peek": True, "item_id": "abc"}
        actions = self._adapter()._build_detail_actions(ctx)
        return self._render(actions[0])

    def test_peek_edit_toggle_is_hx_get_into_panel(self):
        html = self._edit_action(peek=True)
        # A button (not a nav link) that loads the edit form into the panel cell.
        assert 'hx-get="/app/tasks/abc/edit?peek=1"' in html
        assert 'hx-target="#peek-content-abc"' in html
        assert "<button" in html

    def test_non_peek_edit_action_is_nav_link(self):
        html = self._edit_action(peek=False)
        assert 'href="/app/tasks/abc/edit"' in html
        assert "hx-get" not in html


class TestPeekSaveAndStay:
    """#1494 (2c, Slice 2 increment 2): a peek-panel EDIT form commits in place —
    posts `?peek=1` (API suppresses HX-Redirect), discards the JSON body
    (`hx-swap="none"`), and re-fetches the read-only view back into the panel
    cell on success. Non-peek forms keep the page-settling `hx-target="body"`."""

    def _adapter(self):
        from dazzle.http.runtime.renderers.fragment_adapter import FragmentSurfaceAdapter

        return FragmentSurfaceAdapter()

    def _render(self, fragment) -> str:
        from dazzle.render.fragment import FragmentRenderer

        return FragmentRenderer().render(fragment)

    def _form(self, *, peek: bool, mode):
        import types

        surf = types.SimpleNamespace(
            name="task_edit", title="Edit Task", entity_ref="Task", mode=None
        )
        ctx = {
            "fields": [{"name": "title", "label": "Title", "type": "text", "value": "x"}],
            "action": "/api/tasks/abc",
            "method": "PUT",
        }
        if peek:
            ctx |= {"peek": True, "item_id": "abc", "cancel_url": "/app/tasks/abc"}
        return self._render(self._adapter()._build_form(surf, ctx, mode=mode))

    def test_peek_edit_form_posts_with_peek_flag(self):
        from dazzle.core.ir.surfaces import SurfaceMode

        html = self._form(peek=True, mode=SurfaceMode.EDIT)
        # Action carries ?peek=1 so update_item suppresses HX-Redirect.
        assert 'hx-put="/api/tasks/abc?peek=1"' in html

    def test_peek_edit_form_swaps_none_and_refetches_view(self):
        from dazzle.core.ir.surfaces import SurfaceMode

        html = self._form(peek=True, mode=SurfaceMode.EDIT)
        assert 'hx-swap="none"' in html
        assert 'hx-target="#peek-content-abc"' in html
        # On success, re-fetch the read-only view back into the panel cell.
        assert "hx-on:htmx:after:request=" in html
        assert "event.detail.successful" in html
        assert "/app/tasks/abc?peek=1" in html
        assert 'data-dz-peek-save="1"' in html

    def test_non_peek_edit_form_settles_to_page(self):
        from dazzle.core.ir.surfaces import SurfaceMode

        html = self._form(peek=False, mode=SurfaceMode.EDIT)
        assert 'hx-target="body"' in html
        assert 'hx-swap="innerHTML"' in html
        assert "?peek=1" not in html
        assert "hx-on:htmx:after:request" not in html

    def test_peek_create_form_does_not_save_in_panel(self):
        # CREATE has no item to return to — keep the page-settling submit even in
        # a (crafted) peek context, so the inline wiring stays EDIT-only.
        from dazzle.core.ir.surfaces import SurfaceMode

        html = self._form(peek=True, mode=SurfaceMode.CREATE)
        assert "hx-on:htmx:after:request" not in html
        assert 'hx-swap="none"' not in html


# --- peek: slide_over render (#1494 2c, Slice 2) -----------------------------


def _slide_row(peek: str = "slide_over", *, table_id: str = "tasks") -> str:
    from dazzle.render.fragment.primitives import RowCapabilities
    from dazzle.render.fragment.renderer._data_row import render_data_row

    return render_data_row(
        ({"key": "title", "type": "str"},),
        {"id": "abc-123", "title": "x"},
        RowCapabilities(peek=peek, drill=True),
        entity_name="Task",
        api_endpoint="/api/tasks",
        detail_url_template="/tasks/{id}",
        table_id=table_id,
    )


class TestPeekSlideOverRowChevron:
    """A `peek: slide_over` row chevron loads the detail body into the list's one
    shared slide-over panel and reveals it — no per-row panel (that's `expand`)."""

    def test_chevron_targets_shared_slideover_content(self):
        html = _slide_row(table_id="tasks")
        assert "dz-tr-peek-toggle" in html
        assert 'hx-get="/tasks/abc-123?peek=1"' in html
        # Targets the list-level shared content cell, not a per-row panel.
        assert 'hx-target="#slideover-content-tasks"' in html

    def test_chevron_reveals_the_container(self):
        html = _slide_row(table_id="tasks")
        # The reveal is the HM dialog opener contract (dz-dialog.js
        # showModal on the named <dialog>) — no inline hx-on JS.
        assert 'data-dz-dialog-open="slideover-tasks"' in html
        assert "removeAttribute" not in html
        assert "hx-on:click" not in html

    def test_slide_over_emits_no_per_row_panel(self):
        html = _slide_row()
        assert "dz-tr-peek-panel" not in html
        assert "peek-content-abc-123" not in html

    def test_slide_over_off_byte_identical_to_expand_off(self):
        # off rows stay byte-stable regardless of the new branch.
        assert _slide_row("off") == _slide_row("off")
        assert "dz-tr-peek-toggle" not in _slide_row("off")

    def test_build_data_table_threads_peek_and_table_id_to_chevron(self):
        # The /api row-hydrate seam: the per-surface-resolved `peek_mode` + the
        # surface's `table_id` flow table_dict → DataTable → row chevron, so the
        # chevron's reveal/target ids match the container `_build_list` emits for
        # that same table_id (the SEV-2 alignment — chevron keyed per-surface).
        from dazzle.http.runtime.handlers.list_handlers import build_data_table
        from dazzle.render.fragment.renderer._data_row import render_data_table_rows

        dt = build_data_table(
            {
                "columns": [{"key": "title", "type": "str"}],
                "entity_name": "Task",
                "detail_url_template": "/tasks/{id}",
                "peek_mode": "slide_over",
                "table_id": "my_tasks",
            },
            [{"id": "r1", "title": "x"}],
        )
        html = render_data_table_rows(dt)
        assert 'hx-target="#slideover-content-my_tasks"' in html
        assert "slideover-my_tasks" in html  # reveal targets the per-surface panel
        assert "dz-tr-peek-panel" not in html  # no per-row panel for slide_over


class TestSlideOverPrimitive:
    """The `SlideOver` container renders the HM drawer contract — a native
    `<dialog class="dz-drawer">` with the panel + content ids the row
    chevron addresses. Focus trap, inert background, Esc and backdrop
    dismissal are the platform's own (Tier F2 convergence; the bespoke
    `.dz-slideover-*` family + inline hx-on toggles were retired)."""

    def _render(self, **kw) -> str:
        from dazzle.render.fragment import FragmentRenderer, SlideOver

        return FragmentRenderer().render(SlideOver(**kw))

    def test_renders_native_dialog_with_matching_ids(self):
        html = self._render(table_id="tasks", title="Task detail")
        assert 'id="slideover-tasks"' in html
        assert "<dialog" in html
        assert "dz-drawer" in html
        assert 'closedby="any"' in html
        # dialogs take their accessible name only from author attributes
        assert 'aria-labelledby="slideover-tasks-title"' in html
        assert 'id="slideover-tasks-title"' in html
        assert 'id="slideover-content-tasks"' in html
        assert "dz-drawer__body" in html

    def test_close_is_the_native_dialog_form(self):
        html = self._render(table_id="tasks")
        # One <form method="dialog"> close button; no backdrop div, no
        # inline JS — dismissal is native (Esc / backdrop / the form).
        assert '<form method="dialog"' in html
        assert "dz-drawer__close" in html
        assert "dz-slideover" not in html
        assert "hx-on:click" not in html

    def test_width_drives_data_attr(self):
        assert 'data-dz-width="lg"' in self._render(table_id="t", width="lg")

    def test_requires_table_id(self):
        import pytest

        from dazzle.render.fragment import SlideOver

        with pytest.raises(ValueError):
            SlideOver(table_id="")


class TestSlideOverListContainer:
    """`_build_list` emits the shared `SlideOver` exactly when the list's
    resolved peek mode is `slide_over` (always an explicit author value)."""

    def _list_html(self, peek_mode: str) -> str:
        import types

        from dazzle.http.runtime.renderers.fragment_adapter import FragmentSurfaceAdapter
        from dazzle.render.fragment import FragmentRenderer

        surf = types.SimpleNamespace(name="task_list", title="Tasks", entity_ref="Task", mode=None)
        ctx = {
            "columns": [{"key": "title", "label": "Title", "type": "text"}],
            "endpoint": "/api/tasks",
            "entity_title": "Task",
            "detail_url_template": "/tasks/{id}",
            # region_name is what `_build_dispatch_ctx` sets to surface.name; it
            # drives table_id (= region_name or entity_name), so the container id
            # matches the row chevron's `#slideover-{table_id}` target.
            "region_name": "task_list",
            "peek_mode": peek_mode,
        }
        return FragmentRenderer().render(FragmentSurfaceAdapter()._build_list(surf, ctx))

    def test_slide_over_emits_container(self):
        html = self._list_html("slide_over")
        assert 'class="dz-drawer"' in html  # HM drawer contract (Tier F2)
        assert 'id="slideover-task_list"' in html  # table_id = region_name

    def test_expand_emits_no_container(self):
        assert "dz-slideover-panel" not in self._list_html("expand")

    def test_off_emits_no_container(self):
        assert "dz-slideover-panel" not in self._list_html("off")


class TestSlideOverDispatchCtx:
    """`_build_dispatch_ctx` threads the explicit `peek:` value so the list
    adapter can emit the container with the initial chrome."""

    def test_explicit_slide_over_threads(self):
        import types

        from dazzle.core.ir.surfaces import PeekMode
        from dazzle.http.runtime.page_routes import _build_dispatch_ctx

        table = types.SimpleNamespace(columns=[], rows=[], api_endpoint="/api/tasks")
        render_ctx = types.SimpleNamespace(table=table, form=None)
        surface = types.SimpleNamespace(name="task_list", peek=PeekMode.SLIDE_OVER)
        ctx = _build_dispatch_ctx(render_ctx, surface)
        assert ctx["peek_mode"] == "slide_over"

    def test_unset_threads_off(self):
        import types

        from dazzle.http.runtime.page_routes import _build_dispatch_ctx

        table = types.SimpleNamespace(columns=[], rows=[], api_endpoint="/api/tasks")
        render_ctx = types.SimpleNamespace(table=table, form=None)
        surface = types.SimpleNamespace(name="task_list", peek=None)
        ctx = _build_dispatch_ctx(render_ctx, surface)
        assert ctx["peek_mode"] == "off"
