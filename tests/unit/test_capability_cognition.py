"""Capability cognition gating (#1342 Phase 2)."""

import dazzle.core.capabilities.registry as reg
from dazzle.core.capabilities import active_capability_ids


def test_active_capability_ids_is_non_raising(monkeypatch):
    # OIDC available, SAML not. Unlike resolve_capabilities, this must NOT raise
    # when a declared capability's extra is missing — it just omits it.
    monkeypatch.setattr(reg, "find_spec", lambda name: object() if name == "authlib" else None)
    active = active_capability_ids(["auth.enterprise.oidc", "auth.enterprise.saml", "auth.bogus"])
    assert active == {"auth.enterprise.oidc"}  # available+declared only
    assert "auth.enterprise.saml" not in active  # declared but unavailable → omitted
    assert "auth.bogus" not in active  # unknown → omitted


def test_active_capabilities_for_reads_manifest(tmp_path, monkeypatch):
    from dazzle.core.capabilities.cognition import active_capabilities_for

    monkeypatch.setattr(reg, "find_spec", lambda name: object())  # all available
    (tmp_path / "dazzle.toml").write_text(
        '[project]\nname = "t"\nversion = "0.0.1"\n\n[modules]\npaths = ["app"]\n\n'
        '[capabilities]\nenabled = ["auth.enterprise.oidc"]\n',
        encoding="utf-8",
    )
    assert active_capabilities_for(tmp_path) == {"auth.enterprise.oidc"}


def test_active_capabilities_for_missing_manifest_is_empty(tmp_path):
    from dazzle.core.capabilities.cognition import active_capabilities_for

    assert active_capabilities_for(tmp_path) == set()


def test_active_capabilities_for_malformed_manifest_is_empty(tmp_path):
    # A malformed manifest must NOT crash an advisory cognition read.
    from dazzle.core.capabilities.cognition import active_capabilities_for

    (tmp_path / "dazzle.toml").write_text("this is not valid toml = = =", encoding="utf-8")
    assert active_capabilities_for(tmp_path) == set()


def test_partition_by_capability_splits_surfaced_and_gated():
    from dazzle.core.capabilities.cognition import partition_by_capability

    items = [
        {"id": "a", "cap": None},
        {"id": "b", "cap": "auth.enterprise.oidc"},
        {"id": "c", "cap": "auth.enterprise.saml"},
    ]
    surfaced, gated = partition_by_capability(
        items, active={"auth.enterprise.oidc"}, capability_of=lambda it: it["cap"]
    )
    assert [i["id"] for i in surfaced] == ["a", "b"]  # ungated + active
    assert gated == [(items[2], "auth.enterprise.saml")]  # gated + inactive


def test_enable_suggestion_carries_runbook():
    from dazzle.core.capabilities.cognition import enable_suggestion

    s = enable_suggestion("auth.enterprise.oidc")
    assert s["capability"] == "auth.enterprise.oidc"
    assert s["enable"] == "dazzle capability enable auth.enterprise.oidc"
    assert "dazzle-dsl[sso]" in s["remediation"]


def test_engine_filters_gated_relevance(monkeypatch):
    from types import SimpleNamespace

    import dazzle.core.discovery.engine as eng
    from dazzle.core.discovery.models import Relevance

    gated = Relevance(
        context="c",
        capability="cap",
        category="cat",
        examples=[],
        kg_entity="k",
        gated_by="auth.enterprise.oidc",
    )
    ungated = Relevance(
        context="c2", capability="cap2", category="cat2", examples=[], kg_entity="k2"
    )
    monkeypatch.setattr(eng, "check_widget_relevance", lambda *a: [gated, ungated])
    monkeypatch.setattr(eng, "check_layout_relevance", lambda *a: [])
    monkeypatch.setattr(eng, "check_component_relevance", lambda *a: [])
    monkeypatch.setattr(eng, "check_completeness_relevance", lambda *a: [])
    appspec = SimpleNamespace(domain=SimpleNamespace(entities=[]), surfaces=[], workspaces=[])

    # Not active → the gated item is dropped (gated_by preserved through enrich).
    out = eng.suggest_capabilities(appspec, active=set())
    keys = {r.kg_entity for r in out}
    assert "k2" in keys and "k" not in keys

    # Active → the gated item surfaces.
    out2 = eng.suggest_capabilities(appspec, active={"auth.enterprise.oidc"})
    assert {"k", "k2"} <= {r.kg_entity for r in out2}

    # Default (no active arg) → behaviour unchanged for existing callers: nothing
    # is gated unless a rule sets gated_by AND active excludes it. Here gated_by IS
    # set, so default-empty active drops it — matching the not-active case.
    out3 = eng.suggest_capabilities(appspec)
    assert "k" not in {r.kg_entity for r in out3}


def test_lint_appspec_forwards_active_capabilities(monkeypatch, tmp_path):
    import dazzle.core.lint as lint
    from dazzle.core.linker import build_appspec
    from dazzle.core.parser import parse_modules

    src = 'module t\napp s "S"\n\nentity Task "Task":\n  id: uuid pk\n  title: str(200)\n'
    p = tmp_path / "m.dsl"
    p.write_text(src, encoding="utf-8")
    appspec = build_appspec(parse_modules([p]), root_module_name="t")

    captured = {}
    real = lint.suggest_capabilities

    def spy(a, **kw):
        captured["active"] = kw.get("active")
        return real(a, **kw)

    monkeypatch.setattr(lint, "suggest_capabilities", spy)
    lint.lint_appspec(appspec, active_capabilities={"auth.enterprise.oidc"})
    assert captured["active"] == {"auth.enterprise.oidc"}
