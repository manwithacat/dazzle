"""#1413: a custom renderer declared in dazzle.toml `[renderers] extra` but
never registered at runtime must emit a boot-time warning (it would otherwise
pass validate/lint and 500 with a FragmentError at first request).

Exercises ``DazzleBackendApp._warn_unregistered_renderers`` against the real
``fixtures/custom_renderer`` manifest (which declares ``word_cloud`` /
``feedback_detail`` but never wires their handlers), using a duck-typed stand-in
for ``self`` so no DB/subprocess boot is needed.
"""

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace

from dazzle.back.runtime.server import DazzleBackendApp

_FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "custom_renderer"


def _stub(registered: list[str]) -> SimpleNamespace:
    """Minimal stand-in exposing only the attrs the method reads."""
    registry = SimpleNamespace(registered_names=lambda: list(registered))
    services = SimpleNamespace(renderer_registry=registry)
    return SimpleNamespace(
        _project_root=_FIXTURE,
        _app=SimpleNamespace(state=SimpleNamespace(services=services)),
    )


def test_declared_but_unregistered_renderer_warns(caplog) -> None:
    # Only the framework default "fragment" is registered; the fixture's
    # declared customs (word_cloud, feedback_detail) are orphans.
    stub = _stub(registered=["fragment"])
    with caplog.at_level(logging.WARNING):
        DazzleBackendApp._warn_unregistered_renderers(stub)  # type: ignore[arg-type]
    warnings = " ".join(r.message for r in caplog.records)
    assert "never registered at runtime" in warnings, caplog.text
    assert "word_cloud" in warnings and "feedback_detail" in warnings, caplog.text


def test_no_warning_when_all_declared_renderers_registered(caplog) -> None:
    # When the customs ARE registered, no orphan warning fires.
    stub = _stub(registered=["fragment", "word_cloud", "feedback_detail"])
    with caplog.at_level(logging.WARNING):
        DazzleBackendApp._warn_unregistered_renderers(stub)  # type: ignore[arg-type]
    assert not any("never registered at runtime" in r.message for r in caplog.records), caplog.text
