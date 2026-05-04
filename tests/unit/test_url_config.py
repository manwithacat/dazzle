"""Tests for URL configuration and resolution."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

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


def _manifest(*, site_url: str | None = None, api_url: str | None = None) -> ProjectManifest:
    kwargs: dict = {}
    if site_url is not None:
        kwargs["site_url"] = site_url
    if api_url is not None:
        kwargs["api_url"] = api_url
    return ProjectManifest(
        name="test",
        version="0.1.0",
        project_root="",
        module_paths=["./dsl"],
        urls=URLsConfig(**kwargs) if kwargs else URLsConfig(),
    )


@pytest.mark.parametrize(
    ("env", "manifest", "expected"),
    [
        ({}, None, "http://localhost:3000"),
        (
            {"DAZZLE_SITE_URL": "https://env.example.com"},
            _manifest(site_url="https://toml.example.com"),
            "https://env.example.com",
        ),
        ({}, _manifest(site_url="https://toml.example.com"), "https://toml.example.com"),
        ({"DAZZLE_SITE_URL": "https://example.com/"}, None, "https://example.com"),
    ],
    ids=[
        "test_default_when_no_manifest_no_env",
        "test_env_var_wins",
        "test_manifest_wins_over_default",
        "test_trailing_slash_stripped",
    ],
)
def test_resolve_site_url(
    env: dict[str, str], manifest: ProjectManifest | None, expected: str
) -> None:
    with patch.dict(os.environ, env, clear=True):
        assert resolve_site_url(manifest) == expected


@pytest.mark.parametrize(
    ("env", "manifest", "expected"),
    [
        ({}, None, "http://localhost:8000"),
        (
            {"DAZZLE_API_URL": "https://api.env.com"},
            _manifest(api_url="https://api.toml.com"),
            "https://api.env.com",
        ),
        ({}, _manifest(api_url="https://api.toml.com"), "https://api.toml.com"),
        ({"DAZZLE_API_URL": "https://api.example.com/"}, None, "https://api.example.com"),
    ],
    ids=[
        "test_default_when_no_manifest_no_env",
        "test_env_var_wins",
        "test_manifest_wins_over_default",
        "test_trailing_slash_stripped",
    ],
)
def test_resolve_api_url(
    env: dict[str, str], manifest: ProjectManifest | None, expected: str
) -> None:
    with patch.dict(os.environ, env, clear=True):
        assert resolve_api_url(manifest) == expected
