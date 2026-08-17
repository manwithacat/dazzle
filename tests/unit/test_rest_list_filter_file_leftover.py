"""Leftover REST ?filter[file]=zzz must not invent empty (cycle 2202).

leftover-honest slug VALUES already exist (oral #82). REST
``list_handlers`` still landed leftover FILE VALUES on known
``file`` keys in ``gated_list`` / ``repo.list`` and invented
empty. Valid file path/URL/identifier ride; leftover restores
unfiltered (omit). Oral #83 — not another GET list slug VALUE
(oral #82).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from dazzle.http.runtime.page_routes import (
    entity_file_filter_fields,
    leftover_honest_filter_file,
    leftover_honest_list_filters,
)

_PAGE_ROUTES = (
    Path(__file__).resolve().parents[2] / "src" / "dazzle" / "http" / "runtime" / "page_routes.py"
)
_LIST = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "http"
    / "runtime"
    / "handlers"
    / "list_handlers.py"
)
_LIVE = Path(__file__).resolve().parents[2] / "examples" / "project_tracker" / "dsl" / "app.dsl"

_ALLOWED = frozenset({"id", "title", "status", "file", "attachment"})
_SPEC = SimpleNamespace(
    fields=[
        SimpleNamespace(name="id"),
        SimpleNamespace(name="title"),
        SimpleNamespace(name="status"),
        SimpleNamespace(name="file", type=SimpleNamespace(kind="file")),
        SimpleNamespace(name="attachment", type=SimpleNamespace(kind="file")),
    ]
)
_FILE_ID = "12345678-1234-5678-1234-567812345678"


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({"filter[file]": "zzz"}, {}),
        ({"filter[file]": "ghost"}, {}),
        ({"filter[file]": "not-a-file"}, {}),
        ({"filter[file]": "foo"}, {}),
        ({"filter[file]": "../etc/passwd"}, {}),
        ({"filter[file]": "report.pdf"}, {"file": "report.pdf"}),
        ({"filter[file]": "test_file.txt"}, {"file": "test_file.txt"}),
        (
            {"filter[file]": "uploads/2026/08/17/uuid_report.pdf"},
            {"file": "uploads/2026/08/17/uuid_report.pdf"},
        ),
        (
            {"filter[file]": "https://cdn.example.com/a.pdf"},
            {"file": "https://cdn.example.com/a.pdf"},
        ),
        ({"filter[file]": _FILE_ID}, {"file": _FILE_ID}),
        ({"filter[attachment]": "zzz"}, {}),
        ({"filter[attachment]": "mockup.png"}, {"attachment": "mockup.png"}),
        (
            {"filter[file]": "zzz", "filter[title]": "Invoice"},
            {"title": "Invoice"},
        ),
        (
            {"filter[file]": "report.pdf", "filter[title]": "Invoice"},
            {"file": "report.pdf", "title": "Invoice"},
        ),
        ({"file": "zzz"}, {}),
        ({"file": "report.pdf"}, {"file": "report.pdf"}),
        ({}, {}),
        (None, {}),
    ],
    ids=[
        "bracket-leftover-file",
        "bracket-leftover-ghost",
        "bracket-leftover-phrase",
        "bracket-leftover-bare-token",
        "bracket-leftover-traversal",
        "bracket-valid-filename",
        "bracket-valid-test-file",
        "bracket-valid-storage-key",
        "bracket-valid-https",
        "bracket-valid-uuid",
        "bracket-leftover-attachment",
        "bracket-valid-attachment",
        "bracket-leftover-plus-title",
        "bracket-valid-plus-title",
        "bare-leftover-file",
        "bare-valid-file",
        "empty-params",
        "none-params",
    ],
)
def test_leftover_honest_list_filter_file_values_do_not_invent(
    params: dict[str, str] | None,
    expected: dict[str, str],
) -> None:
    query = params if params is not None else SimpleNamespace()
    assert (
        leftover_honest_list_filters(
            query,
            allowed=_ALLOWED,
            filter_fields=["file", "attachment", "title"],
            entity_spec=_SPEC,
        )
        == expected
    )


def test_entity_file_filter_fields_reads_spec() -> None:
    assert entity_file_filter_fields(_SPEC) == frozenset({"file", "attachment"})
    assert entity_file_filter_fields(None) == frozenset()
    assert entity_file_filter_fields(SimpleNamespace()) == frozenset()
    assert entity_file_filter_fields(SimpleNamespace(fields=[SimpleNamespace(name="title")])) == (
        frozenset()
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("zzz", ""),
        ("ghost", ""),
        ("not-a-file", ""),
        ("foo", ""),
        ("../etc/passwd", ""),
        ("", ""),
        (None, ""),
        ("report.pdf", "report.pdf"),
        ("test_file.txt", "test_file.txt"),
        (
            "uploads/2026/08/17/uuid_report.pdf",
            "uploads/2026/08/17/uuid_report.pdf",
        ),
        ("https://cdn.example.com/a.pdf", "https://cdn.example.com/a.pdf"),
        (_FILE_ID, _FILE_ID),
        (True, ""),
        (False, ""),
    ],
    ids=[
        "junk",
        "ghost",
        "phrase",
        "bare-token",
        "traversal",
        "empty",
        "none",
        "filename",
        "test-file",
        "storage-key",
        "https",
        "uuid",
        "py-true",
        "py-false",
    ],
)
def test_leftover_honest_filter_file_does_not_invent(raw: object, expected: str) -> None:
    assert leftover_honest_filter_file(raw) == expected


def test_helper_source_pins_list_filter_file_leftover() -> None:
    src = _PAGE_ROUTES.read_text(encoding="utf-8")
    assert "def leftover_honest_list_filters" in src
    assert "def entity_file_filter_fields" in src
    assert "filter[file]=zzz" in src
    assert "leftover_honest_filter_file" in src
    assert "leftover_honest_entity_id" in src
    assert "leftover_honest_filter_url" in src


def test_list_handler_source_pins_filter_file_leftover() -> None:
    src = _LIST.read_text(encoding="utf-8")
    assert "leftover_honest_list_filters(" in src
    assert "filter[file]=zzz" in src


def test_live_project_tracker_attachment_file() -> None:
    src = _LIVE.read_text(encoding="utf-8")
    assert 'entity Attachment "Attachment":' in src
    assert "file: file required" in src
