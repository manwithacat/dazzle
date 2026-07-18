"""Agent demo cognition priors — concepts, counter-priors, always-on pack."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SIMPLE = REPO / "examples" / "simple_task"


def test_agent_demo_toml_and_aliases() -> None:
    import tomllib
    from pathlib import Path

    from dazzle.mcp.semantics_kb import ALIASES, TOML_FILES

    assert "agent_demo.toml" in TOML_FILES
    path = Path(__file__).resolve().parents[2] / "src/dazzle/mcp/semantics_kb/agent_demo.toml"
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    concepts = data["concepts"]
    for name in (
        "demo_identity",
        "stable_personas",
        "workspace_region_filters",
        "empty_desk_false_green",
        "first_principles_demo",
    ):
        assert name in concepts, name
        assert concepts[name].get("definition")
    assert data["meta"]["concept_count"] == len(concepts)
    assert ALIASES.get("demo_ops") == "first_principles_demo"
    assert ALIASES.get("false_green") == "empty_desk_false_green"


def test_counter_priors_agent_era_parse() -> None:
    from dazzle.mcp.semantics_kb.counter_priors import load_all_counter_priors

    ids = {e.id for e in load_all_counter_priors()}
    for need in (
        "empty_desk_false_green",
        "free_persona_id_not_stable",
        "workspace_filter_or_silent_empty",
        "reseed_stable_users",
    ):
        assert need in ids


def test_demo_ops_exposes_knowledge_index() -> None:
    from dazzle.demo_data.test_mode_load import demo_ops_playbook

    pb = demo_ops_playbook()
    assert "demo_identity" in pb["knowledge_concepts"]
    assert "empty_desk_false_green" in pb["counter_priors"]
    assert pb["workflow"] == "first_principles_demo"


def test_agent_context_knowledge_priors() -> None:
    from dazzle.agent_loop import build_context

    if not (SIMPLE / "dazzle.toml").is_file():
        pytest.skip("simple_task missing")
    ctx = build_context(SIMPLE)
    assert "knowledge_priors" in ctx
    assert "demo_identity" in ctx["knowledge_priors"]["concepts"]
    assert ctx["knowledge_priors"]["workflow"] == "first_principles_demo"


def test_first_principles_workflow_guide() -> None:
    from dazzle.mcp.cli_help import get_workflow_guide

    guide = get_workflow_guide("first_principles_demo")
    assert guide.get("found") is True
    assert len(guide.get("steps") or []) >= 6
    assert "bootstrap_pollution" in (guide.get("counter_priors") or [])


def test_version_cognition_triple() -> None:
    from dazzle.core.version_cognition import framework_version_cognition

    cog = framework_version_cognition(SIMPLE if SIMPLE.is_dir() else None)
    assert "installed" in cog
    assert cog["installed"] not in ("",)
    assert "compatible" in cog
    assert "hint" in cog


def test_1629_g4_g5_g7_priors_catalogued() -> None:
    from dazzle.mcp.semantics_kb.counter_priors import load_all_counter_priors

    ids = {e.id for e in load_all_counter_priors()}
    for need in (
        "bootstrap_pollution",
        "metric_current_user_lie",
        "version_pin_distrust",
    ):
        assert need in ids
    from dazzle.demo_data.test_mode_load import demo_ops_playbook

    pb = demo_ops_playbook()
    assert "bootstrap_pollution" in pb["counter_priors"]
    assert "version_cognition" in pb["knowledge_concepts"]
