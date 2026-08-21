"""Related file_list must title the filename, not the uploader (oral #139)."""

from __future__ import annotations

from pathlib import Path

from dazzle.core.project import load_project
from dazzle.page.converters.template_compiler import compile_appspec_to_templates
from dazzle.render.cell_chrome import format_byte_size, related_file_name_and_meta
from dazzle.render.fragment.format_cell import format_cell
from dazzle.render.fragment.primitives.data import RelatedGroup, RelatedTab
from dazzle.render.fragment.renderer import FragmentRenderer
from dazzle.render.fragment.renderer._data_row import _render_cell_display


def test_format_byte_size_humanizes_and_leftover_stays_put() -> None:
    assert format_byte_size(18432) == "18 KB"
    assert format_byte_size(12) == "12 B"
    assert format_byte_size(1_500_000) == "1.5 MB"
    assert format_byte_size("zzz") == "zzz"
    assert format_cell(18432, "bytes") == "18 KB"
    assert format_cell("zzz", "bytes") == "zzz"


def test_related_file_name_prefers_filename_not_uploader() -> None:
    name, metas = related_file_name_and_meta(
        (
            "Alex Field",
            "brief.md",
            "a1000000-0000-4000-8000-000000000001",
            "18432",
            "1 Aug 2026",
        ),
        ("Uploaded By", "Filename", "File", "Size Bytes", "Created At"),
    )
    assert name == "brief.md"
    assert metas == ["18 KB"]
    assert "Alex Field" not in name
    assert "a1000000" not in name


def test_related_file_leftover_filename_stays_put() -> None:
    name, metas = related_file_name_and_meta(
        ("Alex Field", "zzz", "a1000000-0000-4000-8000-000000000001", "ghost"),
        ("Uploaded By", "Filename", "File", "Size Bytes"),
    )
    assert name == "zzz"
    assert metas == ["ghost"]
    assert format_byte_size("ghost") == "ghost"


def test_related_file_list_html_titles_filename() -> None:
    html = FragmentRenderer().render(
        RelatedGroup(
            group_id="files",
            label="Files",
            display="file_list",
            tabs=(
                RelatedTab(
                    tab_id="files",
                    label="Files",
                    headers=("Uploaded By", "Filename", "File", "Size Bytes"),
                    rows=(
                        (
                            "Alex Field",
                            "brief.md",
                            "a1000000-0000-4000-8000-000000000001",
                            "18432",
                        ),
                    ),
                    row_drill=("/app/attachment/a-1",),
                ),
            ),
        )
    )
    assert 'class="dz-related-file-name">brief.md<' in html
    assert "18 KB" in html
    assert 'class="dz-related-file-name">Alex Field<' not in html
    assert "a1000000-0000-4000-8000-000000000001" not in html


def test_related_file_list_leftover_html_stays_put() -> None:
    html = FragmentRenderer().render(
        RelatedGroup(
            group_id="files",
            label="Files",
            display="file_list",
            tabs=(
                RelatedTab(
                    tab_id="files",
                    label="Files",
                    headers=("Uploaded By", "Filename", "Size Bytes"),
                    rows=(("Alex Field", "zzz", "ghost"),),
                ),
            ),
        )
    )
    assert 'class="dz-related-file-name">zzz<' in html
    assert "ghost" in html
    assert "18 KB" not in html


def test_project_tracker_seed_file_row_titles_filename() -> None:
    name, metas = related_file_name_and_meta(
        (
            "Jamie Chen",
            "ia-dropoff-funnel-map-v3.pdf",
            "/files/demo/ia-dropoff-funnel-map-v3.pdf",
            "482331",
            "11 Jul 2026",
        ),
        ("Uploaded By", "Filename", "File", "Size Bytes", "Created At"),
    )
    assert name == "ia-dropoff-funnel-map-v3.pdf"
    assert metas == ["482 KB"]
    assert "/files/demo/" not in name


def test_project_tracker_file_list_columns_type_size_bytes() -> None:
    spec = load_project(Path("examples/project_tracker"))
    ctxs = compile_appspec_to_templates(spec)
    detail = ctxs["/task/{id}"].detail
    assert detail is not None
    group = next(g for g in detail.related_groups if g.group_id == "group-task_files")
    assert group.display == "file_list"
    tab = group.tabs[0]
    keys = [c.key for c in tab.columns]
    assert "filename" in keys
    size = next(c for c in tab.columns if c.key == "size_bytes")
    assert size.type == "bytes"


def test_list_row_bytes_cell_humanizes() -> None:
    html = _render_cell_display({"key": "size_bytes", "type": "bytes"}, 18432)
    assert html == "18 KB"
    leftover = _render_cell_display({"key": "size_bytes", "type": "bytes"}, "zzz")
    assert leftover == "zzz"
