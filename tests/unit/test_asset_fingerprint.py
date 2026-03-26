"""Tests for content-hash asset fingerprinting (#711)."""

from pathlib import Path

from dazzle_ui.runtime.asset_fingerprint import (
    FINGERPRINT_RE,
    build_asset_manifest,
    static_url_filter,
    strip_fingerprint,
)


class TestBuildAssetManifest:
    def test_hashes_css_files(self, tmp_path: Path) -> None:
        css_dir = tmp_path / "css"
        css_dir.mkdir()
        (css_dir / "app.css").write_text("body { color: red; }")

        manifest = build_asset_manifest(tmp_path)
        assert "css/app.css" in manifest
        # Fingerprinted path has 8-char hex hash before extension
        fp = manifest["css/app.css"]
        assert FINGERPRINT_RE.match(fp)

    def test_hashes_js_files(self, tmp_path: Path) -> None:
        js_dir = tmp_path / "js"
        js_dir.mkdir()
        (js_dir / "main.js").write_text("console.log('hello');")

        manifest = build_asset_manifest(tmp_path)
        assert "js/main.js" in manifest

    def test_ignores_non_asset_files(self, tmp_path: Path) -> None:
        (tmp_path / "readme.txt").write_text("not an asset")
        (tmp_path / "data.json").write_text("{}")

        manifest = build_asset_manifest(tmp_path)
        assert len(manifest) == 0

    def test_hash_changes_with_content(self, tmp_path: Path) -> None:
        css = tmp_path / "style.css"
        css.write_text("v1")
        m1 = build_asset_manifest(tmp_path)

        css.write_text("v2")
        m2 = build_asset_manifest(tmp_path)

        assert m1["style.css"] != m2["style.css"]

    def test_multiple_directories(self, tmp_path: Path) -> None:
        dir1 = tmp_path / "project"
        dir1.mkdir()
        (dir1 / "custom.css").write_text("project styles")

        dir2 = tmp_path / "framework"
        dir2.mkdir()
        (dir2 / "base.css").write_text("framework styles")

        manifest = build_asset_manifest(dir1, dir2)
        assert "custom.css" in manifest
        assert "base.css" in manifest

    def test_skips_nonexistent_dirs(self) -> None:
        manifest = build_asset_manifest(Path("/nonexistent/dir"))
        assert manifest == {}

    def test_includes_svg(self, tmp_path: Path) -> None:
        assets = tmp_path / "assets"
        assets.mkdir()
        (assets / "icon.svg").write_text("<svg></svg>")

        manifest = build_asset_manifest(tmp_path)
        assert "assets/icon.svg" in manifest


class TestStaticUrlFilter:
    def test_rewrites_known_path(self) -> None:
        manifest = {"css/app.css": "css/app.a1b2c3d4.css"}
        result = static_url_filter("css/app.css", manifest)
        assert result == "/static/css/app.a1b2c3d4.css"

    def test_strips_static_prefix(self) -> None:
        manifest = {"css/app.css": "css/app.a1b2c3d4.css"}
        result = static_url_filter("/static/css/app.css", manifest)
        assert result == "/static/css/app.a1b2c3d4.css"

    def test_fallback_for_unknown_path(self) -> None:
        manifest = {}
        result = static_url_filter("css/unknown.css", manifest)
        assert result == "/static/css/unknown.css"

    def test_fallback_preserves_absolute_path(self) -> None:
        manifest = {}
        result = static_url_filter("/static/css/unknown.css", manifest)
        assert result == "/static/css/unknown.css"


class TestStripFingerprint:
    def test_strips_valid_fingerprint(self) -> None:
        assert strip_fingerprint("css/app.a1b2c3d4.css") == "css/app.css"

    def test_strips_nested_path(self) -> None:
        assert strip_fingerprint("vendor/htmx.min.f0e1d2c3.js") == "vendor/htmx.min.js"

    def test_returns_none_for_non_fingerprinted(self) -> None:
        assert strip_fingerprint("css/app.css") is None

    def test_returns_none_for_short_hash(self) -> None:
        assert strip_fingerprint("css/app.abc.css") is None

    def test_returns_none_for_non_hex(self) -> None:
        assert strip_fingerprint("css/app.ghijklmn.css") is None


class TestFingerprintRegex:
    def test_matches_valid_pattern(self) -> None:
        assert FINGERPRINT_RE.match("app.a1b2c3d4.css")

    def test_no_match_without_hash(self) -> None:
        assert not FINGERPRINT_RE.match("app.css")

    def test_no_match_long_hash(self) -> None:
        # Only 8-char hex hashes are valid
        assert not FINGERPRINT_RE.match("app.a1b2c3d4e5.css")
