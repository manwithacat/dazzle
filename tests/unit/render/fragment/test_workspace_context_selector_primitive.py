"""Phase 4B.5.b.3 (v0.66.124): byte-equivalence + structural tests for
the typed `WorkspaceContextSelector` primitive.

The context selector is the optional `<div class="dz-workspace-context">`
+ inline IIFE that filters workspace regions by an entity FK. The
adapter resolves the `label or entity.replace('_', ' ')` fallback
upstream; the typed primitive receives the resolved label string."""

from __future__ import annotations

import pytest

from dazzle.render.fragment import FragmentRenderer, WorkspaceContextSelector
from dazzle_back.runtime.renderers.dual_path import diff_summary
from dazzle_ui.runtime.template_renderer import create_jinja_env


class _LegacyWorkspace:
    def __init__(self, name, options_url, label, entity):
        self.name = name
        self.context_options_url = options_url
        self.context_selector_label = label
        self.context_selector_entity = entity


def _legacy_render(ws: _LegacyWorkspace) -> str:
    src = open(  # noqa: SIM115
        "src/dazzle_ui/templates/workspace/_content.html"
    ).read()
    start = src.index("{% if workspace.context_options_url %}")
    end = src.index("{% endif %}", start) + len("{% endif %}")
    block = src[start:end]
    env = create_jinja_env()
    return env.from_string(block).render(workspace=ws)


def _typed_render(workspace_name: str, options_url: str, label: str) -> str:
    return FragmentRenderer().render(
        WorkspaceContextSelector(
            workspace_name=workspace_name, options_url=options_url, label=label
        )
    )


def test_context_selector_with_explicit_label_byte_equivalence() -> None:
    """`context_selector_label` set → label rendered verbatim."""
    ws = _LegacyWorkspace("dashboard", "/api/contexts", "Tenant", "tenant")
    legacy = _legacy_render(ws)
    typed = _typed_render("dashboard", "/api/contexts", "Tenant")
    assert diff_summary(legacy, typed) is None


def test_context_selector_label_fallback_byte_equivalence() -> None:
    """No explicit label → adapter falls back to `entity.replace('_', ' ')`.
    Typed primitive receives the resolved string; assert byte-equivalence
    with the legacy fallback path."""
    ws = _LegacyWorkspace("ops", "/api/c2", None, "tenant_org")
    legacy = _legacy_render(ws)
    typed = _typed_render("ops", "/api/c2", "tenant org")
    assert diff_summary(legacy, typed) is None


def test_context_selector_emits_select_with_default_all_option() -> None:
    """The select carries `id="dz-context-selector"` (the JS keys off
    this) and a default `<option value="">All</option>` option."""
    html = _typed_render("d", "/api/c", "Tenant")
    assert 'id="dz-context-selector"' in html
    assert '<option value="">All</option>' in html


def test_context_selector_label_uses_for_attribute() -> None:
    """The `<label>` element's `for=` matches the select id — the a11y
    contract for screen readers."""
    html = _typed_render("d", "/api/c", "Tenant")
    assert 'for="dz-context-selector"' in html
    assert ">Tenant:</label>" in html


def test_context_selector_inline_script_uses_dz_prefs() -> None:
    """The IIFE keys saved selections to `workspace.{name}.context`
    via dzPrefs — restores the user's last context across nav."""
    html = _typed_render("dashboard", "/api/c", "X")
    assert "window.dzPrefs" in html
    assert "workspace." in html
    assert ".context" in html


def test_context_selector_inline_script_updates_region_hx_get_urls() -> None:
    """On change, the IIFE walks every `[id^="region-"][hx-get]` and
    sets `context_id={selected}` on the URL — the cross-region filter
    contract."""
    html = _typed_render("d", "/api/c", "X")
    assert '[id^="region-"][hx-get]' in html
    assert "context_id" in html


def test_context_selector_inline_script_guards_against_undefined_htmx() -> None:
    """#980 round 2 — manual htmx triggers are skipped when
    `typeof htmx === 'undefined'` so the page works even if the
    selector dispatches its initial change before the deferred
    htmx.min.js has loaded."""
    html = _typed_render("d", "/api/c", "X")
    assert "typeof htmx === 'undefined'" in html


def test_context_selector_validates_required_fields() -> None:
    """Empty workspace_name / options_url both raise."""
    with pytest.raises(ValueError, match="workspace_name"):
        WorkspaceContextSelector(workspace_name="", options_url="/x", label="L")
    with pytest.raises(ValueError, match="options_url"):
        WorkspaceContextSelector(workspace_name="d", options_url="", label="L")


def test_context_selector_workspace_name_is_json_encoded_in_script() -> None:
    """`tojson` produces a JSON-encoded string with quotes — the typed
    primitive matches by using `json.dumps()`. A workspace name like
    `my_workspace` becomes `"my_workspace"` in the script body."""
    html = _typed_render("my_workspace", "/api/c", "X")
    assert 'var wsName = "my_workspace"' in html


def test_context_selector_options_url_is_json_encoded_in_script() -> None:
    """Same `tojson`-encoding applies to the fetch URL — special chars
    in the URL round-trip cleanly."""
    html = _typed_render("d", "/api/contexts?app=ops", "X")
    assert 'fetch("/api/contexts?app=ops")' in html
