"""Example eval hub — registry + Host parse (no live serve)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_HUB = Path(__file__).resolve().parents[2] / "scripts" / "example_hub"


def _load(name: str):
    path = _HUB / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"example_hub_{name}", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    # package-local imports need path
    sys.path.insert(0, str(_HUB))
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def registry():
    return _load("registry")


class TestParseHost:
    def test_hub_hosts(self, registry) -> None:
        assert registry.parse_host("dazzle.local") is None
        assert registry.parse_host("dazzle.local:9080") is None
        assert registry.parse_host("www.dazzle.local") is None
        assert registry.parse_host("hub.dazzle.local:9080") is None
        assert registry.parse_host("localhost:9080") is None
        assert registry.parse_host("127.0.0.1:9080") is None

    def test_app_subdomain(self, registry) -> None:
        assert registry.parse_host("simple_task.dazzle.local") == "simple_task"
        assert registry.parse_host("Simple_Task.dazzle.local:9080") == "simple_task"
        assert registry.parse_host("contact_manager.dazzle.local") == "contact_manager"

    def test_unknown_slug(self, registry) -> None:
        assert registry.parse_host("not-a-valid.dazzle.local") == "?unknown:not-a-valid"
        assert registry.parse_host("foo.bar.dazzle.local") == "?unknown:foo.bar"


class TestDiscover:
    def test_finds_showcase(self, registry) -> None:
        apps = registry.discover_apps(showcase_only=True)
        names = {a.name for a in apps}
        assert "simple_task" in names
        assert "contact_manager" in names
        assert all(a.port >= 9100 for a in apps)
        # stable ports by index
        by_name = {a.name: a.port for a in apps}
        apps2 = registry.discover_apps(showcase_only=True)
        assert {a.name: a.port for a in apps2} == by_name

    def test_host_property(self, registry) -> None:
        apps = registry.discover_apps(showcase_only=True)
        st = next(a for a in apps if a.name == "simple_task")
        assert st.host == "simple_task.dazzle.local"
