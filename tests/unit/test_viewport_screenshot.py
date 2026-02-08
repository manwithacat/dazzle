"""Tests for viewport visual regression screenshots."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from dazzle.testing.viewport_screenshot import (
    BASELINES_DIR,
    ScreenshotResult,
    _file_hash,
    _safe_filename,
    capture_screenshot,
    compare_screenshots,
    get_baseline_path,
    run_visual_regression,
    save_as_baseline,
)


def _make_tiny_png(width: int = 2, height: int = 2, color: tuple[int, ...] = (255, 0, 0)) -> bytes:
    """Create a minimal valid PNG image using Pillow."""
    import io

    from PIL import Image

    img = Image.new("RGB", (width, height), color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class TestSafeFilename:
    """Tests for _safe_filename()."""

    def test_root_path(self) -> None:
        assert _safe_filename("/", "mobile") == "root_mobile.png"

    def test_simple_path(self) -> None:
        assert _safe_filename("/dashboard", "desktop") == "dashboard_desktop.png"

    def test_nested_path(self) -> None:
        assert _safe_filename("/admin/users", "tablet") == "admin_users_tablet.png"

    def test_trailing_slash(self) -> None:
        assert _safe_filename("/dashboard/", "mobile") == "dashboard_mobile.png"


class TestGetBaselinePath:
    """Tests for get_baseline_path()."""

    def test_returns_expected_path(self, tmp_path: Path) -> None:
        path = get_baseline_path(tmp_path, "/dashboard", "mobile")
        assert path == tmp_path / BASELINES_DIR / "dashboard_mobile.png"

    def test_root_page_path(self, tmp_path: Path) -> None:
        path = get_baseline_path(tmp_path, "/", "desktop")
        assert path == tmp_path / BASELINES_DIR / "root_desktop.png"


class TestCaptureScreenshot:
    """Tests for capture_screenshot()."""

    def test_captures_and_returns_path(self, tmp_path: Path) -> None:
        mock_page = MagicMock()
        mock_page.screenshot = MagicMock()
        output_dir = tmp_path / "screenshots"
        path = capture_screenshot(mock_page, "/dashboard", "mobile", output_dir)
        assert path == output_dir / "dashboard_mobile.png"
        mock_page.screenshot.assert_called_once()

    def test_creates_output_directory(self, tmp_path: Path) -> None:
        mock_page = MagicMock()
        output_dir = tmp_path / "new_dir" / "screenshots"
        capture_screenshot(mock_page, "/", "desktop", output_dir)
        assert output_dir.exists()


class TestSaveAsBaseline:
    """Tests for save_as_baseline()."""

    def test_copies_file(self, tmp_path: Path) -> None:
        src = tmp_path / "current.png"
        src.write_bytes(b"PNG_DATA")
        baseline = tmp_path / "baselines" / "test.png"
        save_as_baseline(src, baseline)
        assert baseline.exists()
        assert baseline.read_bytes() == b"PNG_DATA"

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        src = tmp_path / "current.png"
        src.write_bytes(b"PNG_DATA")
        baseline = tmp_path / "deep" / "nested" / "dir" / "test.png"
        save_as_baseline(src, baseline)
        assert baseline.exists()


class TestFileHash:
    """Tests for _file_hash()."""

    def test_deterministic(self, tmp_path: Path) -> None:
        f = tmp_path / "test.bin"
        f.write_bytes(b"hello")
        assert _file_hash(f) == _file_hash(f)

    def test_different_content_different_hash(self, tmp_path: Path) -> None:
        a = tmp_path / "a.bin"
        b = tmp_path / "b.bin"
        a.write_bytes(b"hello")
        b.write_bytes(b"world")
        assert _file_hash(a) != _file_hash(b)


class TestCompareScreenshots:
    """Tests for compare_screenshots()."""

    def test_identical_images_pass_with_pillow(self, tmp_path: Path) -> None:
        img_data = _make_tiny_png(4, 4, (128, 128, 128))
        current = tmp_path / "current.png"
        baseline = tmp_path / "baseline.png"
        diff_out = tmp_path / "diff.png"
        current.write_bytes(img_data)
        baseline.write_bytes(img_data)
        passed, diff_pct = compare_screenshots(current, baseline, diff_out)
        assert passed is True
        assert diff_pct == 0.0

    def test_different_images_fail_with_pillow(self, tmp_path: Path) -> None:
        current = tmp_path / "current.png"
        baseline = tmp_path / "baseline.png"
        diff_out = tmp_path / "diff.png"
        current.write_bytes(_make_tiny_png(4, 4, (255, 0, 0)))
        baseline.write_bytes(_make_tiny_png(4, 4, (0, 0, 255)))
        passed, diff_pct = compare_screenshots(current, baseline, diff_out)
        assert passed is False
        assert diff_pct > 0.0
        assert diff_out.exists()

    def test_hash_fallback_identical(self, tmp_path: Path) -> None:
        """Without Pillow, identical files pass via hash comparison."""
        current = tmp_path / "current.png"
        baseline = tmp_path / "baseline.png"
        current.write_bytes(b"IDENTICAL_DATA")
        baseline.write_bytes(b"IDENTICAL_DATA")
        # Directly test the fallback logic (hash comparison)
        assert _file_hash(current) == _file_hash(baseline)

    def test_hash_fallback_different(self, tmp_path: Path) -> None:
        """Without Pillow, different files would fail via hash comparison."""
        current = tmp_path / "current.png"
        baseline = tmp_path / "baseline.png"
        current.write_bytes(b"DATA_A")
        baseline.write_bytes(b"DATA_B")
        from dazzle.testing.viewport_screenshot import _file_hash

        assert _file_hash(current) != _file_hash(baseline)


class TestRunVisualRegression:
    """Tests for run_visual_regression()."""

    def test_new_baseline_created(self, tmp_path: Path) -> None:
        mock_page = MagicMock()
        png_data = _make_tiny_png()

        def fake_screenshot(path: str, full_page: bool = True) -> None:
            Path(path).write_bytes(png_data)

        mock_page.screenshot = fake_screenshot

        result = run_visual_regression(
            mock_page,
            "/dashboard",
            "mobile",
            tmp_path,
        )
        assert isinstance(result, ScreenshotResult)
        assert result.is_new_baseline is True
        assert result.passed is True
        assert result.baseline_path is not None
        assert result.baseline_path.exists()

    def test_update_baselines_flag(self, tmp_path: Path) -> None:
        mock_page = MagicMock()
        png_data = _make_tiny_png(2, 2, (0, 255, 0))

        def fake_screenshot(path: str, full_page: bool = True) -> None:
            Path(path).write_bytes(png_data)

        mock_page.screenshot = fake_screenshot

        # Create existing baseline
        baseline_dir = tmp_path / BASELINES_DIR
        baseline_dir.mkdir(parents=True, exist_ok=True)
        (baseline_dir / "dashboard_mobile.png").write_bytes(_make_tiny_png(2, 2, (255, 0, 0)))

        result = run_visual_regression(
            mock_page,
            "/dashboard",
            "mobile",
            tmp_path,
            update_baselines=True,
        )
        assert result.is_new_baseline is True
        assert result.passed is True

    def test_comparison_against_identical_baseline(self, tmp_path: Path) -> None:
        mock_page = MagicMock()
        png_data = _make_tiny_png(4, 4, (100, 100, 100))

        def fake_screenshot(path: str, full_page: bool = True) -> None:
            Path(path).write_bytes(png_data)

        mock_page.screenshot = fake_screenshot

        # Create matching baseline
        baseline_dir = tmp_path / BASELINES_DIR
        baseline_dir.mkdir(parents=True, exist_ok=True)
        (baseline_dir / "dashboard_desktop.png").write_bytes(png_data)

        result = run_visual_regression(
            mock_page,
            "/dashboard",
            "desktop",
            tmp_path,
        )
        assert result.is_new_baseline is False
        assert result.passed is True
        assert result.pixel_diff_pct == 0.0
