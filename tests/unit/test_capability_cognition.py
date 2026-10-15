"""Capability cognition gating (#1342 Phase 2)."""

import json

import pytest

import dazzle.core.capabilities.registry as reg
from dazzle.core.capabilities import active_capability_ids
from tests.unit._fake_capabilities import fake_capabilities  # noqa: F401  (fixture)

pytestmark = pytest.mark.usefixtures("fake_capabilities")


def test_active_capability_ids_is_non_raising(monkeypatch):
    # alpha available, beta not. Unlike resolve_capabilities, this must NOT raise
    # when a declared capability's extra is missing — it just omits it.
    monkeypatch.setattr(reg, "find_spec", lambda name: object() if name == "authlib" else None)
    active = active_capability_ids(["demo.alpha", "demo.beta", "demo.bogus"])
    assert active == {"demo.alpha"}  # available+declared only
    assert "demo.beta" not in active  # declared but unavailable → omitted
    assert "demo.bogus" not in active  # unknown → omitted


def test_active_capabilities_for_reads_manifest(tmp_path, monkeypatch):
    from dazzle.core.capabilities.cognition import active_capabilities_for

    monkeypatch.setattr(reg, "find_spec", lambda name: object())  # all available
    (tmp_path / "dazzle.toml").write_text(
        '[project]\nname = "t"\nversion = "0.0.1"\n\n[modules]\npaths = ["app"]\n\n'
        '[capabilities]\nenabled = ["demo.alpha"]\n',
        encoding="utf-8",
    )
    assert active_capabilities_for(tmp_path) == {"demo.alpha"}


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
        {"id": "b", "cap": "demo.alpha"},
        {"id": "c", "cap": "demo.beta"},
    ]
    surfaced, gated = partition_by_capability(
        items, active={"demo.alpha"}, capability_of=lambda it: it["cap"]
    )
    assert [i["id"] for i in surfaced] == ["a", "b"]  # ungated + active
    assert gated == [(items[2], "demo.beta")]  # gated + inactive


def test_enable_suggestion_carries_runbook():
    from dazzle.core.capabilities.cognition import enable_suggestion

    s = enable_suggestion("demo.alpha")
    assert s["capability"] == "demo.alpha"
    assert s["enable"] == "dazzle capability enable demo.alpha"
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
        gated_by="demo.alpha",
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
    out2 = eng.suggest_capabilities(appspec, active={"demo.alpha"})
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
    lint.lint_appspec(appspec, active_capabilities={"demo.alpha"})
    assert captured["active"] == {"demo.alpha"}


_BLOB = {
    "patterns": {
        "gated_sso": {
            "name": "Gated SSO",
            "category": "Auth",
            "capability": "demo.alpha",
            "triggers": ["okta", "sso"],
        }
    }
}


def test_propose_patterns_gates_and_suggests(monkeypatch):
    import dazzle.mcp.server.handlers.spec_analyze as sa

    monkeypatch.setattr("dazzle.mcp.semantics_kb.get_dsl_patterns", lambda: _BLOB)

    # Not active → an enable-suggestion, NOT a full proposal.
    out = json.loads(
        sa._propose_patterns({"spec_text": "Staff sign in via Okta SSO."}, active=set())
    )
    assert any(s["capability"] == "demo.alpha" for s in out.get("capability_suggestions", []))
    assert out["pattern_proposals"] == []

    # Active → a normal proposal, no suggestion.
    out2 = json.loads(sa._propose_patterns({"spec_text": "Okta SSO."}, active={"demo.alpha"}))
    assert out2.get("capability_suggestions", []) == []
    assert any(p["pattern_id"] == "gated_sso" for p in out2["pattern_proposals"])


def test_bootstrap_surfaces_capability_suggestions(monkeypatch, tmp_path):
    import dazzle.mcp.server.handlers.bootstrap as bs

    monkeypatch.setattr("dazzle.mcp.semantics_kb.get_dsl_patterns", lambda: _BLOB)

    # No dazzle.toml → nothing declared → a stated Okta requirement becomes a
    # capability suggestion in the briefing, not a full proposal.
    out = json.loads(bs._run_cognition_pass("Staff sign in via Okta SSO.", "test", tmp_path))
    sugg = out["analysis"].get("capability_suggestions", [])
    assert any(s["capability"] == "demo.alpha" for s in sugg)
    assert out["analysis"]["pattern_proposals"] == []

    # Declare it (available) → the suggestion goes away, the proposal appears.
    monkeypatch.setattr(reg, "find_spec", lambda name: object())
    (tmp_path / "dazzle.toml").write_text(
        '[project]\nname="t"\nversion="0.0.1"\n\n[modules]\npaths=["app"]\n\n'
        '[capabilities]\nenabled=["demo.alpha"]\n',
        encoding="utf-8",
    )
    out2 = json.loads(bs._run_cognition_pass("Okta SSO.", "test", tmp_path))
    assert out2["analysis"].get("capability_suggestions", []) == []
    assert any(p["pattern_id"] == "gated_sso" for p in out2["analysis"]["pattern_proposals"])


def test_counter_prior_gate_suppresses_when_inactive(monkeypatch):
    import dazzle.mcp.server.handlers.spec_analyze as sa
    from dazzle.mcp.semantics_kb.counter_priors import CounterPrior

    cp = CounterPrior(
        id="gated_pathology",
        name="Gated pathology",
        layer="inference",
        summary="don't do the gated thing",
        triggers_text=["widget soup"],
        file_path="x",
        body="...",
        capability="demo.beta",
    )
    monkeypatch.setattr(sa, "_load_counter_priors_for_flagging", lambda: [cp])
    monkeypatch.setattr("dazzle.mcp.semantics_kb.get_dsl_patterns", lambda: {"patterns": {}})

    # Not active → the gated antipattern is suppressed (irrelevant to this app).
    out = json.loads(sa._propose_patterns({"spec_text": "lots of widget soup"}, active=set()))
    assert out["antipattern_flags"] == []

    # Active → the antipattern is flagged.
    out2 = json.loads(sa._propose_patterns({"spec_text": "widget soup"}, active={"demo.beta"}))
    assert any(f["guidance_id"] == "gated_pathology" for f in out2["antipattern_flags"])


def test_knowledge_pull_path_is_ungated(monkeypatch):
    # Push/pull contract: a direct `knowledge counter_prior` query returns a
    # capability-gated entry regardless of what's active. Only PROACTIVE surfaces
    # gate; pull queries never do.
    import dazzle.mcp.server.handlers.knowledge as kn
    from dazzle.mcp.semantics_kb.counter_priors import CounterPrior

    cp = CounterPrior(
        id="gated_cp",
        name="Gated",
        layer="inference",
        summary="s",
        triggers_text=["t"],
        file_path="x",
        body="...",
        capability="demo.beta",
    )
    monkeypatch.setattr(kn, "load_all_counter_priors", lambda: [cp])
    out = kn.counter_prior_handler({"id": "gated_cp"})
    assert "gated_cp" in out  # returned even though nothing is active


def test_pattern_capability_round_trips_through_kg(monkeypatch):
    # #1265-class regression: the `capability` gate MUST survive the KG seed
    # round-trip. Before the seed.py fix, _propose_patterns saw capability=None
    # under a seeded KG (full-suite/production) and the gate silently no-op'd —
    # while passing in isolation via the TOML fallback. No shipped pattern is
    # gated since DD-013, so inject one into the TOML read and seed an in-memory KG.
    import dazzle.mcp.semantics_kb as kb
    from dazzle.mcp.knowledge_graph.seed import seed_framework_knowledge
    from dazzle.mcp.knowledge_graph.store import KnowledgeGraph

    real_load = kb._load_toml_file

    def load_with_gated_pattern(path):
        data = real_load(path)
        if path.name == "patterns.toml":
            data = {**data, "patterns": {**data.get("patterns", {}), **_BLOB["patterns"]}}
        return data

    monkeypatch.setattr(kb, "_load_toml_file", load_with_gated_pattern)
    graph = KnowledgeGraph(":memory:")
    seed_framework_knowledge(graph)
    entity = next(
        e for e in graph.list_entities(entity_type="pattern", limit=500) if e.name == "gated_sso"
    )
    assert entity.metadata.get("capability") == "demo.alpha"
