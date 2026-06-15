"""#1392 slice 2 — the shipped custom-renderer conformance harness.

Renders each custom surface against a stub context and asserts non-blank /
well-formed / inner-HTML-only, so downstreams stop hand-rolling the check.
"""

from __future__ import annotations

from dataclasses import dataclass

from dazzle.back.runtime.services import RuntimeServices
from dazzle.testing.custom_renderer_conformance import check_custom_renderer_conformance


@dataclass
class _Surface:
    name: str
    render: str | None
    mode: str = "custom"
    title: str | None = None


@dataclass
class _AppSpec:
    surfaces: list[_Surface]


class _GoodRenderer:
    def render(self, surface, ctx):  # type: ignore[no-untyped-def]
        return '<section class="x"><p>empty state</p></section>'


class _BlankRenderer:
    def render(self, surface, ctx):  # type: ignore[no-untyped-def]
        return ""  # the blank-200 failure the guarantee exists to catch


class _FullDocumentRenderer:
    def render(self, surface, ctx):  # type: ignore[no-untyped-def]
        return "<!doctype html><html><body><p>I bypass chrome</p></body></html>"


class _RaisingRenderer:
    def render(self, surface, ctx):  # type: ignore[no-untyped-def]
        # A renderer that assumes ctx has data instead of degrading.
        return f"<p>{ctx['rows'][0]}</p>"


def _services_with(**handlers: object) -> RuntimeServices:
    services = RuntimeServices()
    for name, handler in handlers.items():
        services.renderer_registry.register(name=name, handler=handler)
    return services


def test_passing_custom_renderer_conforms():
    appspec = _AppSpec(surfaces=[_Surface("tag_cloud", render="word_cloud")])
    services = _services_with(word_cloud=_GoodRenderer())
    results = check_custom_renderer_conformance(appspec=appspec, services=services)
    assert len(results) == 1
    assert results[0].ok is True
    assert results[0].surface == "tag_cloud"
    assert results[0].renderer == "word_cloud"


def test_blank_output_fails():
    appspec = _AppSpec(surfaces=[_Surface("blank_surface", render="blanky")])
    services = _services_with(blanky=_BlankRenderer())
    results = check_custom_renderer_conformance(appspec=appspec, services=services)
    assert results[0].ok is False
    assert "blank" in (results[0].reason or "").lower()


def test_full_document_fails_inner_html_only():
    appspec = _AppSpec(surfaces=[_Surface("doc_surface", render="docu")])
    services = _services_with(docu=_FullDocumentRenderer())
    results = check_custom_renderer_conformance(appspec=appspec, services=services)
    assert results[0].ok is False
    assert "inner HTML only" in (results[0].reason or "")


def test_renderer_that_raises_on_stub_ctx_fails():
    appspec = _AppSpec(surfaces=[_Surface("raises", render="raiser")])
    services = _services_with(raiser=_RaisingRenderer())
    results = check_custom_renderer_conformance(appspec=appspec, services=services)
    assert results[0].ok is False
    assert "raised" in (results[0].reason or "").lower()


def test_unregistered_renderer_fails():
    appspec = _AppSpec(surfaces=[_Surface("orphan", render="never_registered")])
    services = _services_with()  # nothing registered for the name
    results = check_custom_renderer_conformance(appspec=appspec, services=services)
    assert results[0].ok is False
    assert "no runtime handler is registered" in (results[0].reason or "")


def test_fragment_and_unset_surfaces_are_skipped():
    appspec = _AppSpec(
        surfaces=[
            _Surface("plain_list", render=None, mode="list"),
            _Surface("fragment_surface", render="fragment", mode="list"),
        ]
    )
    services = _services_with()
    results = check_custom_renderer_conformance(appspec=appspec, services=services)
    assert results == []  # only non-default custom renderers are checked


def test_real_custom_renderer_fixture_conforms(tmp_path):
    """End-to-end against the committed fixtures/custom_renderer app: both
    custom surfaces (word_cloud, feedback_detail) degrade to a visible empty
    state on the stub-ctx (empty-data) path."""
    import glob
    import importlib.util
    from pathlib import Path

    from dazzle.core.linker import build_appspec
    from dazzle.core.parser import parse_modules

    dsls = [Path(p) for p in glob.glob("fixtures/custom_renderer/dsl/*.dsl")]
    appspec = build_appspec(parse_modules(dsls), "custom_renderer.core")

    # fixtures/ is not an importable package; load the renderer modules by path
    # (mirrors how the fixture's register_with_app wires them at app boot).
    def _load(path: str, mod_name: str):  # type: ignore[no-untyped-def]
        spec = importlib.util.spec_from_file_location(mod_name, path)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    word_cloud_mod = _load("fixtures/custom_renderer/app/render/word_cloud.py", "_fx_word_cloud")
    feedback_mod = _load(
        "fixtures/custom_renderer/app/render/feedback_detail.py", "_fx_feedback_detail"
    )

    services = _services_with(
        word_cloud=word_cloud_mod.WordCloudRenderer(),
        feedback_detail=feedback_mod.FeedbackDetailRenderer(),
    )
    results = check_custom_renderer_conformance(appspec=appspec, services=services)
    checked = {r.surface for r in results}
    assert {"tag_cloud", "feedback_detail"} <= checked
    failures = [r for r in results if not r.ok]
    assert not failures, "; ".join(r.reason or "" for r in failures)
