"""Tests for CombinedStaticFiles — multi-directory static file serving."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture()
def project_dir(tmp_path: Path) -> Path:
    """Create a mock project static directory with images."""
    static = tmp_path / "project" / "static"
    images = static / "images"
    images.mkdir(parents=True)
    (images / "hero.webp").write_text("hero-image-data")
    (static / "override.css").write_text("/* project override */")
    return static


@pytest.fixture()
def framework_dir(tmp_path: Path) -> Path:
    """Create a mock framework static directory with js/css/assets."""
    static = tmp_path / "framework" / "static"
    js = static / "js"
    js.mkdir(parents=True)
    (js / "dz.js").write_text("// dazzle runtime")
    css = static / "css"
    css.mkdir(parents=True)
    (css / "dazzle.css").write_text("/* dazzle styles */")
    assets = static / "assets"
    assets.mkdir(parents=True)
    (assets / "dazzle-favicon.svg").write_text("<svg/>")
    # Also create override.css in framework to test shadowing
    (static / "override.css").write_text("/* framework default */")
    return static


class TestCombinedStaticFilesLookup:
    """Test lookup_path resolution order."""

    def test_resolves_project_file_first(self, project_dir: Path, framework_dir: Path) -> None:
        from dazzle_back.runtime.static_files import CombinedStaticFiles

        combined = CombinedStaticFiles(directories=[project_dir, framework_dir])
        full_path, stat = combined.lookup_path("images/hero.webp")

        assert stat is not None
        assert "project" in full_path
        assert full_path == str(project_dir / "images" / "hero.webp")

    def test_falls_back_to_framework(self, project_dir: Path, framework_dir: Path) -> None:
        from dazzle_back.runtime.static_files import CombinedStaticFiles

        combined = CombinedStaticFiles(directories=[project_dir, framework_dir])
        full_path, stat = combined.lookup_path("js/dz.js")

        assert stat is not None
        assert "framework" in full_path

    def test_project_shadows_framework(self, project_dir: Path, framework_dir: Path) -> None:
        from dazzle_back.runtime.static_files import CombinedStaticFiles

        combined = CombinedStaticFiles(directories=[project_dir, framework_dir])
        full_path, stat = combined.lookup_path("override.css")

        assert stat is not None
        assert "project" in full_path
        content = Path(full_path).read_text()
        assert "project override" in content

    def test_nonexistent_file_returns_none_stat(
        self, project_dir: Path, framework_dir: Path
    ) -> None:
        from dazzle_back.runtime.static_files import CombinedStaticFiles

        combined = CombinedStaticFiles(directories=[project_dir, framework_dir])
        _full_path, stat = combined.lookup_path("does-not-exist.txt")

        assert stat is None

    def test_favicon_accessible(self, project_dir: Path, framework_dir: Path) -> None:
        from dazzle_back.runtime.static_files import CombinedStaticFiles

        combined = CombinedStaticFiles(directories=[project_dir, framework_dir])
        full_path, stat = combined.lookup_path("assets/dazzle-favicon.svg")

        assert stat is not None
        assert "dazzle-favicon.svg" in full_path

    def test_skips_nonexistent_extra_dir(self, framework_dir: Path, tmp_path: Path) -> None:
        """Non-existent project dir should be silently skipped."""
        from dazzle_back.runtime.static_files import CombinedStaticFiles

        missing = tmp_path / "does-not-exist"
        combined = CombinedStaticFiles(directories=[missing, framework_dir])
        full_path, stat = combined.lookup_path("js/dz.js")

        assert stat is not None
        assert "framework" in full_path

    def test_single_directory(self, framework_dir: Path) -> None:
        """Works with just one directory (no extras)."""
        from dazzle_back.runtime.static_files import CombinedStaticFiles

        combined = CombinedStaticFiles(directories=[framework_dir])
        full_path, stat = combined.lookup_path("js/dz.js")

        assert stat is not None

    def test_leading_slash_stripped(self, project_dir: Path, framework_dir: Path) -> None:
        from dazzle_back.runtime.static_files import CombinedStaticFiles

        combined = CombinedStaticFiles(directories=[project_dir, framework_dir])
        full_path, stat = combined.lookup_path("/images/hero.webp")

        assert stat is not None
        assert "project" in full_path
