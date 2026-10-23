"""#1843 — usage-driven UI adaptation is opt-in via `[ui] adaptive_ui`.

Each call site that lets the recorded usage signal change a page is gated on
the named adaptation: off (the default) means the signal is not even read and
the page renders as declared. The manifest parsing rows live with the other
`[ui]` keys in `test_manifest_sections.py`.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from dazzle.core import ir
from dazzle.http.converters.entity_converter import convert_entity
from dazzle.http.runtime import page_routes
from dazzle.http.runtime.server import _usage_columns_full

pytestmark = pytest.mark.unit

_ALL = frozenset({"combobox", "autofocus", "actions", "columns"})


def _form_fields() -> list[dict[str, Any]]:
    return [
        {"name": "title", "kind": "text", "label": "Title"},
        {
            "name": "kind",
            "kind": "select",
            "label": "Type",
            "options": [(f"k{i}", f"K{i}") for i in range(9)],
        },
    ]


@pytest.mark.parametrize(
    ("adaptive", "reads", "widget", "focused"),
    [
        pytest.param(frozenset(), False, None, None, id="off-by-default-no-read"),
        pytest.param(frozenset({"actions", "columns"}), False, None, None, id="form-names-off"),
        pytest.param(frozenset({"combobox"}), True, "combobox", None, id="combobox-only"),
        # The hot select stays a plain select, so it is the autofocus target.
        pytest.param(frozenset({"autofocus"}), True, None, "kind", id="autofocus-only"),
        pytest.param(_ALL, True, "combobox", "title", id="all"),
    ],
)
def test_form_annotation_follows_adaptive_ui(
    monkeypatch: pytest.MonkeyPatch,
    adaptive: frozenset[str],
    reads: bool,
    widget: str | None,
    focused: str | None,
) -> None:
    calls: list[str] = []

    def _usage(request: Any, *, surface: str, kind: str) -> dict[str, int]:
        calls.append(surface)
        return {"kind": 40, "title": 12}

    monkeypatch.setattr(page_routes, "read_usage_counts_for_request", _usage)
    prc = SimpleNamespace(deps=SimpleNamespace(adaptive_ui=adaptive), request=object())
    ctx = {"fields": _form_fields()}
    page_routes._annotate_form_usage(
        prc,  # type: ignore[arg-type]
        SimpleNamespace(form=object()),
        SimpleNamespace(entity_ref="Deadline"),
        ctx,
    )
    assert calls == (["Deadline"] if reads else [])
    assert ctx["fields"][1].get("widget") == widget
    assert [f["name"] for f in ctx["fields"] if f.get("autofocus")] == (
        [focused] if focused else []
    )


@pytest.mark.parametrize(
    ("adaptive", "expected"),
    [
        pytest.param(frozenset(), {}, id="off-declared-order"),
        pytest.param(frozenset({"actions"}), {"/app/x": 30}, id="actions-on"),
    ],
)
def test_workspace_action_usage_follows_adaptive_ui(
    monkeypatch: pytest.MonkeyPatch, adaptive: frozenset[str], expected: dict[str, int]
) -> None:
    monkeypatch.setattr(
        page_routes, "_read_workspace_action_usage", lambda request, name: {"/app/x": 30}
    )
    deps = SimpleNamespace(adaptive_ui=adaptive)
    assert page_routes._workspace_action_usage(deps, object(), "ops") == expected  # type: ignore[arg-type]


def _entity() -> Any:
    return convert_entity(
        ir.EntitySpec(
            name="Task",
            label="Task",
            fields=[
                ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID), pk=True),
                ir.FieldSpec(
                    name="title", type=ir.FieldType(kind=ir.FieldTypeKind.STR, max_length=200)
                ),
            ],
        )
    )


@pytest.mark.parametrize(
    ("adaptive", "list_surface", "full"),
    [
        pytest.param(frozenset(), None, False, id="off-declared-columns"),
        pytest.param(frozenset({"columns"}), None, True, id="columns-on"),
        pytest.param(frozenset({"columns"}), object(), False, id="author-projection-wins"),
    ],
)
def test_list_columns_follow_adaptive_ui(
    adaptive: frozenset[str], list_surface: Any, full: bool
) -> None:
    cols = _usage_columns_full(_entity(), list_surface, adaptive)
    assert (cols is not None) is full
