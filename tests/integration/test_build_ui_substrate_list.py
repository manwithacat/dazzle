"""ADR-0049 Task 6 regression: `dazzle build-ui` (static preview) renders list
surfaces via the substrate.

The E2E (PostgreSQL) tier caught that `build-ui` was a list-render caller the
delete-review's inventory missed: `static_preview.generate_preview_files` calls
`render_page` per surface, which now raises loudly for a list (D4). The fix
injects a substrate list-body renderer from the cli `BuildService`. This unit
test pins it so the regression is caught without the Postgres tier.
"""

from __future__ import annotations

from pathlib import Path

from dazzle.core.appspec_loader import load_project_appspec

_SIMPLE = Path(__file__).resolve().parent.parent.parent / "examples" / "simple_task"


def test_build_service_generates_substrate_list_previews(tmp_path: Path) -> None:
    from dazzle.cli.services.build_service import BuildService

    appspec = load_project_appspec(_SIMPLE)
    svc = BuildService(_SIMPLE / "dazzle.toml")
    files = svc.generate_preview_files(appspec, str(tmp_path))

    list_files = [Path(f) for f in files if f.endswith("-list.html")]
    assert list_files, "expected at least one *-list.html preview"
    for f in list_files:
        html = f.read_text(encoding="utf-8")
        # the substrate list, not the deleted legacy table chrome
        assert "dz-region--kind-list" in html, f"{f.name} is not substrate-rendered"
        assert 'class="dz-table-body"' in html  # the hydrating skeleton tbody
        # full standalone page chrome (build-ui writes openable files)
        assert "<!DOCTYPE html>" in html or "<html" in html


def test_static_preview_list_raises_without_renderer() -> None:
    """Without the injected renderer, a list preview raises loudly (D4) rather
    than rendering a blank page — the guard that surfaced the build-ui gap."""
    import pytest

    from dazzle.page.runtime.static_preview import generate_preview_files

    appspec = load_project_appspec(_SIMPLE)
    with pytest.raises(RuntimeError, match="typed substrate"):
        # no list_body_renderer → render_page raises on the first list surface
        generate_preview_files(appspec, "/tmp/should-not-be-written-dz")
