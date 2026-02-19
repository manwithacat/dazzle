"""Tests for the CSS build system."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestGetPlatformKey:
    def test_returns_tuple(self) -> None:
        from dazzle_ui.build_css import _get_platform_key

        key = _get_platform_key()
        assert isinstance(key, tuple)
        assert len(key) == 2

    def test_lowercase_system(self) -> None:
        from dazzle_ui.build_css import _get_platform_key

        system, _machine = _get_platform_key()
        assert system == system.lower()


class TestCacheDir:
    def test_creates_directory(self, tmp_path: Path) -> None:
        from dazzle_ui.build_css import _cache_dir

        with patch.dict("os.environ", {"DAZZLE_CACHE_DIR": str(tmp_path / "cache")}):
            cache = _cache_dir()
            assert cache.is_dir()
            assert str(cache).endswith("cache")


class TestGetTailwindBinary:
    def test_returns_system_binary_if_on_path(self) -> None:
        from dazzle_ui.build_css import get_tailwind_binary

        with patch("dazzle_ui.build_css.shutil.which", return_value="/usr/local/bin/tailwindcss"):
            result = get_tailwind_binary()
            assert result == Path("/usr/local/bin/tailwindcss")

    def test_returns_none_for_unsupported_platform(self) -> None:
        from dazzle_ui.build_css import get_tailwind_binary

        with (
            patch("dazzle_ui.build_css.shutil.which", return_value=None),
            patch("dazzle_ui.build_css._get_platform_key", return_value=("plan9", "mips")),
        ):
            result = get_tailwind_binary()
            assert result is None

    def test_returns_cached_binary(self, tmp_path: Path) -> None:
        from dazzle_ui.build_css import _TAILWIND_VERSION, get_tailwind_binary

        cached = tmp_path / "tailwindcss"
        cached.write_bytes(b"fake-binary")
        version_file = tmp_path / "tailwindcss.version"
        version_file.write_text(_TAILWIND_VERSION)

        with (
            patch("dazzle_ui.build_css.shutil.which", return_value=None),
            patch("dazzle_ui.build_css._cache_dir", return_value=tmp_path),
            patch("dazzle_ui.build_css._get_platform_key", return_value=("darwin", "arm64")),
        ):
            result = get_tailwind_binary()
            assert result == cached

    def test_downloads_if_not_cached(self, tmp_path: Path) -> None:
        from dazzle_ui.build_css import get_tailwind_binary

        mock_response = MagicMock()
        mock_response.read.return_value = b"binary-data"
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with (
            patch("dazzle_ui.build_css.shutil.which", return_value=None),
            patch("dazzle_ui.build_css._cache_dir", return_value=tmp_path),
            patch("dazzle_ui.build_css._get_platform_key", return_value=("darwin", "arm64")),
            patch("urllib.request.urlopen", return_value=mock_response),
        ):
            result = get_tailwind_binary()
            assert result == tmp_path / "tailwindcss"
            assert result.read_bytes() == b"binary-data"

    def test_handles_download_failure(self, tmp_path: Path) -> None:
        from dazzle_ui.build_css import get_tailwind_binary

        with (
            patch("dazzle_ui.build_css.shutil.which", return_value=None),
            patch("dazzle_ui.build_css._cache_dir", return_value=tmp_path),
            patch("dazzle_ui.build_css._get_platform_key", return_value=("darwin", "arm64")),
            patch("urllib.request.urlopen", side_effect=Exception("network error")),
        ):
            result = get_tailwind_binary()
            assert result is None


class TestCreateInputCss:
    def test_creates_input_file(self, tmp_path: Path) -> None:
        from dazzle_ui.build_css import _create_input_css

        result = _create_input_css(tmp_path)
        assert result.exists()
        content = result.read_text()
        assert "@import" in content
        assert "tailwindcss" in content


class TestTemplateDir:
    def test_exists(self) -> None:
        from dazzle_ui.build_css import _template_dir

        d = _template_dir()
        assert d.is_dir()
        assert (d / "base.html").exists()


class TestStaticDir:
    def test_exists(self) -> None:
        from dazzle_ui.build_css import _static_dir

        d = _static_dir()
        assert d.is_dir()
        assert (d / "css" / "dz.css").exists()


class TestBuildCss:
    def test_returns_none_when_no_binary(self, tmp_path: Path) -> None:
        from dazzle_ui.build_css import build_css

        with patch("dazzle_ui.build_css.get_tailwind_binary", return_value=None):
            result = build_css(output_path=tmp_path / "out.css")
            assert result is None

    def test_calls_tailwind_cli(self, tmp_path: Path) -> None:
        from dazzle_ui.build_css import build_css

        mock_binary = tmp_path / "tw"
        mock_binary.write_text("#!/bin/sh\necho ok")
        mock_binary.chmod(0o755)

        output = tmp_path / "output" / "bundle.css"

        mock_run = MagicMock()
        mock_run.returncode = 0

        with (
            patch("dazzle_ui.build_css.get_tailwind_binary", return_value=mock_binary),
            patch("subprocess.run", return_value=mock_run) as mock_subprocess,
        ):
            # Create the output file as if tailwind wrote it
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text("/* compiled */")

            result = build_css(output_path=output, minify=True)

            assert result == output
            call_args = mock_subprocess.call_args
            cmd = call_args[0][0]
            assert str(mock_binary) in cmd
            assert "--input" in cmd
            assert "--output" in cmd
            assert "--minify" in cmd
            assert "--content" in cmd

    def test_no_minify_flag(self, tmp_path: Path) -> None:
        from dazzle_ui.build_css import build_css

        mock_binary = tmp_path / "tw"
        mock_binary.write_text("#!/bin/sh\necho ok")
        mock_binary.chmod(0o755)

        output = tmp_path / "bundle.css"

        mock_run = MagicMock()
        mock_run.returncode = 0

        with (
            patch("dazzle_ui.build_css.get_tailwind_binary", return_value=mock_binary),
            patch("subprocess.run", return_value=mock_run) as mock_subprocess,
        ):
            output.write_text("/* compiled */")
            result = build_css(output_path=output, minify=False)

            assert result == output
            cmd = mock_subprocess.call_args[0][0]
            assert "--minify" not in cmd

    def test_handles_build_failure(self, tmp_path: Path) -> None:
        from dazzle_ui.build_css import build_css

        mock_binary = tmp_path / "tw"

        mock_run = MagicMock()
        mock_run.returncode = 1
        mock_run.stderr = "Error: something went wrong"

        with (
            patch("dazzle_ui.build_css.get_tailwind_binary", return_value=mock_binary),
            patch("subprocess.run", return_value=mock_run),
        ):
            result = build_css(output_path=tmp_path / "bundle.css")
            assert result is None

    def test_includes_project_templates(self, tmp_path: Path) -> None:
        from dazzle_ui.build_css import build_css

        mock_binary = tmp_path / "tw"
        output = tmp_path / "bundle.css"

        # Create project template dir
        proj = tmp_path / "project"
        proj_templates = proj / "templates"
        proj_templates.mkdir(parents=True)
        (proj_templates / "custom.html").write_text("<div>custom</div>")

        mock_run = MagicMock()
        mock_run.returncode = 0

        with (
            patch("dazzle_ui.build_css.get_tailwind_binary", return_value=mock_binary),
            patch("subprocess.run", return_value=mock_run) as mock_subprocess,
        ):
            output.write_text("/* compiled */")
            build_css(output_path=output, project_root=proj)

            cmd = mock_subprocess.call_args[0][0]
            content_arg_idx = cmd.index("--content") + 1
            content_paths = cmd[content_arg_idx]
            assert "templates" in content_paths


class TestVendorFiles:
    """Verify vendored static files exist."""

    @pytest.fixture
    def vendor_dir(self) -> Path:
        return (
            Path(__file__).parent.parent.parent
            / "src"
            / "dazzle_ui"
            / "runtime"
            / "static"
            / "vendor"
        )

    def test_htmx_exists(self, vendor_dir: Path) -> None:
        assert (vendor_dir / "htmx.min.js").exists()

    def test_htmx_extensions_exist(self, vendor_dir: Path) -> None:
        for ext in [
            "htmx-ext-json-enc.js",
            "idiomorph-ext.min.js",
            "htmx-ext-preload.js",
            "htmx-ext-response-targets.js",
            "htmx-ext-loading-states.js",
            "htmx-ext-sse.js",
        ]:
            assert (vendor_dir / ext).exists(), f"Missing {ext}"

    def test_lucide_exists(self, vendor_dir: Path) -> None:
        assert (vendor_dir / "lucide.min.js").exists()


class TestTemplateReferences:
    """Verify templates reference vendored files, not CDN."""

    def test_base_html_no_unpkg(self) -> None:
        base = Path(__file__).parent.parent.parent / "src" / "dazzle_ui" / "templates" / "base.html"
        content = base.read_text()
        assert "unpkg.com" not in content

    def test_base_html_uses_vendor(self) -> None:
        base = Path(__file__).parent.parent.parent / "src" / "dazzle_ui" / "templates" / "base.html"
        content = base.read_text()
        assert "/static/vendor/htmx.min.js" in content

    def test_site_base_no_unpkg(self) -> None:
        site = (
            Path(__file__).parent.parent.parent
            / "src"
            / "dazzle_ui"
            / "templates"
            / "site"
            / "site_base.html"
        )
        content = site.read_text()
        assert "unpkg.com" not in content

    def test_site_base_uses_vendor(self) -> None:
        site = (
            Path(__file__).parent.parent.parent
            / "src"
            / "dazzle_ui"
            / "templates"
            / "site"
            / "site_base.html"
        )
        content = site.read_text()
        assert "/static/vendor/lucide.min.js" in content

    def test_tailwind_conditional_fallback(self) -> None:
        """CDN is only used as fallback when bundle doesn't exist."""
        base = Path(__file__).parent.parent.parent / "src" / "dazzle_ui" / "templates" / "base.html"
        content = base.read_text()
        assert "_tailwind_bundled" in content
        assert "cdn.tailwindcss.com" in content  # Still present as fallback
        assert "dazzle-bundle.css" in content  # Bundle path is there
