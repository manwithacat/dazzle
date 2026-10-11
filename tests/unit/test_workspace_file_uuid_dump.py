"""Workspace file cells must not dump storage UUIDs (oral #170)."""

from __future__ import annotations

from dazzle.http.runtime.workspace_csv import _csv_cell
from dazzle.render.file_cell import clerk_file_cell_display
from dazzle.render.fragment.region import WorkspaceRegionAdapter
from dazzle.render.fragment.renderer import FragmentRenderer

_STORAGE = "a1000000-0000-4000-8000-000000000099"


class _FakeTimeline:
    name = "recent_uploads"
    title = "Recent uploads"
    display = "timeline"
    empty_message = "No recent uploads"


def test_clerk_file_cell_uses_filename_not_uuid() -> None:
    item = {"id": "a1", "filename": "brief.pdf", "file": _STORAGE}
    assert clerk_file_cell_display(item, "file", _STORAGE) == "brief.pdf"
    assert clerk_file_cell_display(item, "file", "zzz") == "zzz"
    assert clerk_file_cell_display({"id": "a1", "file": _STORAGE}, "file", _STORAGE) == "Download"
    assert clerk_file_cell_display({"file": ""}, "file", "") == ""
    assert (
        clerk_file_cell_display(
            {"filename": "spec.pdf", "file": "/uploads/spec.pdf"},
            "file",
            "/uploads/spec.pdf",
        )
        == "spec.pdf"
    )


def test_timeline_html_renders_filename_not_storage_uuid() -> None:
    html = FragmentRenderer().render(
        WorkspaceRegionAdapter().build(  # type: ignore[arg-type]
            _FakeTimeline(),
            {
                "items": [
                    {
                        "id": "a1",
                        "filename": "brief.pdf",
                        "file": _STORAGE,
                        "size_bytes": 1200,
                        "created_at": "2026-08-01T12:00:00+00:00",
                    },
                    {
                        "id": "a99",
                        "filename": "notes.md",
                        "file": "zzz",
                        "created_at": "2026-08-02T12:00:00+00:00",
                    },
                ],
                "columns": [
                    {"key": "filename", "label": "Filename", "type": "text"},
                    {
                        "key": "file",
                        "label": "File",
                        "type": "file",
                        "entity_name": "Attachment",
                    },
                    {"key": "size_bytes", "label": "Size", "type": "bytes"},
                    {"key": "created_at", "label": "Created", "type": "datetime"},
                ],
                "display_key": "filename",
                "empty_message": "No recent uploads",
            },
        )
    )
    assert "brief.pdf" in html
    assert "dz-detail-file-link" in html
    assert "/_dazzle/documents/Attachment/a1/file/file" in html
    assert _STORAGE not in html
    assert "zzz" in html
    assert "No recent uploads" not in html


def test_empty_items_do_not_invent_file_download() -> None:
    html = FragmentRenderer().render(
        WorkspaceRegionAdapter().build(  # type: ignore[arg-type]
            _FakeTimeline(),
            {
                "items": [],
                "columns": [
                    {"key": "file", "label": "File", "type": "file", "entity_name": "Attachment"},
                ],
                "display_key": "filename",
                "empty_message": "No recent uploads",
            },
        )
    )
    assert "zzz" not in html
    assert "Download" not in html
    assert "brief.pdf" not in html
    assert "No recent uploads" in html


def test_csv_file_cell_uses_filename_not_uuid() -> None:
    col = {"key": "file", "label": "File", "type": "file", "entity_name": "Attachment"}
    assert _csv_cell({"filename": "brief.pdf", "file": _STORAGE}, col) == "brief.pdf"
    assert _csv_cell({"file": "zzz"}, col) == "zzz"
    assert _csv_cell({"file": _STORAGE}, col) == "Download"
    assert _csv_cell({"file": ""}, col) == ""
