"""Example eval hub — registry + Host parse (no live serve)."""

from __future__ import annotations

import importlib.util
import os
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


@pytest.fixture(scope="module")
def supervisor_mod():
    return _load("supervisor")


class TestSupervisorOurs:
    """Open port ≠ current-tree serve (cycle 2377 stale 13-day listeners)."""

    def test_is_ours_false_when_pidfile_dead(self, supervisor_mod, tmp_path: Path) -> None:
        from pathlib import Path as P

        ExampleApp = _load("registry").ExampleApp
        app = ExampleApp(
            name="simple_task",
            path=P("/tmp/simple_task"),
            title="t",
            has_spec=True,
            has_trial=True,
            has_stories=True,
            port=19107,
        )
        sup = supervisor_mod.Supervisor(root=tmp_path)
        sup.pid_path(app.name).parent.mkdir(parents=True, exist_ok=True)
        sup.pid_path(app.name).write_text("99999999\n", encoding="utf-8")
        assert sup.is_ours(app) is False
        assert sup.is_running(app) is False

    def test_is_ours_false_when_listener_pid_mismatch(
        self, supervisor_mod, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ExampleApp = _load("registry").ExampleApp
        app = ExampleApp(
            name="simple_task",
            path=tmp_path / "simple_task",
            title="t",
            has_spec=True,
            has_trial=True,
            has_stories=True,
            port=19107,
        )
        sup = supervisor_mod.Supervisor(root=tmp_path)
        live_pid = os.getpid()
        sup.pid_path(app.name).parent.mkdir(parents=True, exist_ok=True)
        sup.pid_path(app.name).write_text(f"{live_pid}\n", encoding="utf-8")
        monkeypatch.setattr(sup, "_listener_pid", lambda port: live_pid + 1)
        assert sup.is_ours(app) is False

    def test_reap_stale_only_kills_dazzle_serve(
        self, supervisor_mod, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ExampleApp = _load("registry").ExampleApp
        app = ExampleApp(
            name="hr_records",
            path=tmp_path / "hr_records",
            title="t",
            has_spec=True,
            has_trial=True,
            has_stories=True,
            port=19107,
        )
        sup = supervisor_mod.Supervisor(root=tmp_path)
        killed: list[int] = []
        monkeypatch.setattr(sup, "_listener_pid", lambda port: 4242)
        monkeypatch.setattr(sup, "_cmdline", lambda pid: "nginx -g daemon")
        monkeypatch.setattr(supervisor_mod.os, "kill", lambda pid, sig: killed.append(pid))
        sup._reap_stale(app)
        assert killed == []

        monkeypatch.setattr(
            sup,
            "_cmdline",
            lambda pid: "/venv/bin/dazzle serve --host 127.0.0.1 --port 19107 --test-mode",
        )
        monkeypatch.setattr(sup, "is_port_open", lambda port: False)
        sup._reap_stale(app)
        assert killed == [4242]

    def test_load_survives_hm_registry_shadow(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """HM site/registry.py must not steal hub ExampleApp (cycle 2378)."""
        import importlib

        site = Path(__file__).resolve().parents[2] / "packages" / "hatchi-maxchi" / "site"
        monkeypatch.syspath_prepend(str(site))
        monkeypatch.delitem(sys.modules, "registry", raising=False)
        monkeypatch.delitem(sys.modules, "example_hub_supervisor", raising=False)
        monkeypatch.delitem(sys.modules, "example_hub.supervisor", raising=False)
        monkeypatch.delitem(sys.modules, "example_hub.registry", raising=False)
        hm = importlib.import_module("registry")
        assert not hasattr(hm, "ExampleApp")
        mod = _load("supervisor")
        assert hasattr(mod, "Supervisor")
        assert hasattr(mod, "ExampleApp")
