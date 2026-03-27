"""Tests for URL configuration and resolution."""

import os
from pathlib import Path
from unittest.mock import patch

from dazzle.core.manifest import (
    ProjectManifest,
    URLsConfig,
    load_manifest,
    resolve_api_url,
    resolve_site_url,
)


class TestURLsConfig:
    def test_defaults(self) -> None:
        config = URLsConfig()
        assert config.site_url == "http://localhost:3000"
        assert config.api_url == "http://localhost:8000"

    def test_custom_values(self) -> None:
        config = URLsConfig(site_url="https://myapp.com", api_url="https://api.myapp.com")
        assert config.site_url == "https://myapp.com"
        assert config.api_url == "https://api.myapp.com"


class TestURLsParsing:
    def test_load_manifest_with_urls(self, tmp_path: Path) -> None:
        toml = tmp_path / "dazzle.toml"
        toml.write_text("""
[project]
name = "test"
version = "0.1.0"

[modules]
paths = ["./dsl"]

[urls]
site_url = "https://myapp.com"
api_url = "https://api.myapp.com"
""")
        manifest = load_manifest(toml)
        assert manifest.urls.site_url == "https://myapp.com"
        assert manifest.urls.api_url == "https://api.myapp.com"

    def test_load_manifest_without_urls_uses_defaults(self, tmp_path: Path) -> None:
        toml = tmp_path / "dazzle.toml"
        toml.write_text("""
[project]
name = "test"
version = "0.1.0"

[modules]
paths = ["./dsl"]
""")
        manifest = load_manifest(toml)
        assert manifest.urls.site_url == "http://localhost:3000"
        assert manifest.urls.api_url == "http://localhost:8000"

    def test_partial_urls_config(self, tmp_path: Path) -> None:
        toml = tmp_path / "dazzle.toml"
        toml.write_text("""
[project]
name = "test"
version = "0.1.0"

[modules]
paths = ["./dsl"]

[urls]
api_url = "https://api.prod.com"
""")
        manifest = load_manifest(toml)
        assert manifest.urls.site_url == "http://localhost:3000"
        assert manifest.urls.api_url == "https://api.prod.com"


class TestResolveSiteUrl:
    def test_default_when_no_manifest_no_env(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            assert resolve_site_url() == "http://localhost:3000"

    def test_env_var_wins(self) -> None:
        with patch.dict(os.environ, {"DAZZLE_SITE_URL": "https://env.example.com"}):
            manifest = ProjectManifest(
                name="test",
                version="0.1.0",
                project_root="",
                module_paths=["./dsl"],
                urls=URLsConfig(site_url="https://toml.example.com"),
            )
            assert resolve_site_url(manifest) == "https://env.example.com"

    def test_manifest_wins_over_default(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            manifest = ProjectManifest(
                name="test",
                version="0.1.0",
                project_root="",
                module_paths=["./dsl"],
                urls=URLsConfig(site_url="https://toml.example.com"),
            )
            assert resolve_site_url(manifest) == "https://toml.example.com"

    def test_trailing_slash_stripped(self) -> None:
        with patch.dict(os.environ, {"DAZZLE_SITE_URL": "https://example.com/"}):
            assert resolve_site_url() == "https://example.com"


class TestResolveApiUrl:
    def test_default_when_no_manifest_no_env(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            assert resolve_api_url() == "http://localhost:8000"

    def test_env_var_wins(self) -> None:
        with patch.dict(os.environ, {"DAZZLE_API_URL": "https://api.env.com"}):
            manifest = ProjectManifest(
                name="test",
                version="0.1.0",
                project_root="",
                module_paths=["./dsl"],
                urls=URLsConfig(api_url="https://api.toml.com"),
            )
            assert resolve_api_url(manifest) == "https://api.env.com"

    def test_manifest_wins_over_default(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            manifest = ProjectManifest(
                name="test",
                version="0.1.0",
                project_root="",
                module_paths=["./dsl"],
                urls=URLsConfig(api_url="https://api.toml.com"),
            )
            assert resolve_api_url(manifest) == "https://api.toml.com"

    def test_trailing_slash_stripped(self) -> None:
        with patch.dict(os.environ, {"DAZZLE_API_URL": "https://api.example.com/"}):
            assert resolve_api_url() == "https://api.example.com"
