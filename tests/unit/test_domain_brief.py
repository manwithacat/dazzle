"""Agent-audience domain brief pipeline."""

from __future__ import annotations

import json
from pathlib import Path

from dazzle.domain_brief import (
    extract_from_text,
    load_domain,
    promote_checklist,
    save_domain,
    score_gaps,
)

SPEND = """
# Spend Desk

Single-org spend request app with three job desks.

| Field | Type | Optional | Display |
|-------|------|----------|---------|
| amount | money | no | Amount |

Employee submits a SpendRequest. Manager approves or rejects.
Finance pays approved requests.

Employee sees draft and in-flight lists for their SpendRequest rows.
"""


def test_extract_grounded_spend_no_chrome() -> None:
    d = extract_from_text(SPEND, source_path="inline")
    names = {n.name for n in d.nouns}
    assert "SpendRequest" in names
    chrome = {"Optional", "Field", "Display", "Type", "Amount"}
    assert not (names & chrome)
    assert any(p.id_hint in ("employee", "manager", "finance") for p in d.personas)
    assert d.rejected_chrome or "Optional" not in names


def test_extract_prefers_core_entity_headers() -> None:
    brief = """
# App
## Core Entities
### **Device**
- Name
### **Issue Report**
- Severity – High, Critical
## User Interface
### **Dashboard**
Kanban and Timeline views.
"""
    d = extract_from_text(brief)
    names = {n.name for n in d.nouns}
    assert "Device" in names
    assert "IssueReport" in names
    assert "Dashboard" not in names
    assert "Kanban" not in names
    assert "High" not in names
    assert "Critical" not in names


def test_extract_rejects_mid_sentence_adjectives() -> None:
    """Long SPECs must not promote 'Urgent'/'Several' as domain nouns."""
    brief = """
# Product

Create several urgent Task records. The TaskComment holds discussion.
A Task has a status lifecycle draft to done.
"""
    d = extract_from_text(brief)
    names = {n.name.lower() for n in d.nouns}
    assert "urgent" not in names
    assert "several" not in names
    assert "create" not in names
    # CamelCase multi-hump still accepted
    assert "taskcomment" in names or "TaskComment" in {n.name for n in d.nouns}


def test_extract_definitional_sentences_not_spec_chrome() -> None:
    """Generated SPECIFICATION.md: keep Brand/Asset/Campaign; drop Matrix/Skeptic."""
    brief = """
# Design Studio — System Specification

Design Studio manages brands and design work.

## What it does

**Brands.** A Brand is the organising anchor of the studio's work.
**Design assets.** A Design Asset is a piece of creative work that always belongs
to a Brand. Each asset moves through draft, review, approved, published.
**Campaigns.** A Campaign also belongs to a Brand.
**Feedback.** Design Feedback is always tied to the Design Asset it concerns.

A skeptic does not have to take this on trust. There is no heavy single-page
JavaScript application. The technical foundation is PostgreSQL. An auditable
access matrix is available. A mature relational database stores data.

## Who uses it

- **Admin** — full access
- **Designer** — creates assets
- **Reviewer** — reviews assets
"""
    d = extract_from_text(brief, source_path="SPECIFICATION.md")
    names = {n.name for n in d.nouns}
    assert "Brand" in names
    assert "Asset" in names or "DesignAsset" in names
    assert "Campaign" in names
    assert "Feedback" in names or "DesignFeedback" in names
    junk = {"Skeptic", "Matrix", "JavaScript", "Technical", "Auditable", "Mature", "Studio"}
    assert not (names & junk), names
    # broken generate_questions style should not block via open_qs content
    for q in d.open_questions:
        assert "thes" not in q.text
        assert "assetss" not in q.text


def test_save_load_roundtrip(tmp_path: Path) -> None:
    d = extract_from_text(SPEND)
    paths = save_domain(tmp_path, d)
    assert Path(paths["markdown"]).is_file()
    assert Path(paths["json"]).is_file()
    loaded = load_domain(tmp_path)
    assert loaded is not None
    assert loaded.title
    assert loaded.source_sha256 == d.source_sha256


def test_promote_blocks_until_questions_cleared() -> None:
    d = extract_from_text(SPEND)
    # Force a blocking open question
    d.open_questions = d.open_questions or []
    from dazzle.domain_brief.models import OpenQuestion

    d.open_questions.append(
        OpenQuestion(id="q_block", text="What is the approval threshold?", blocks_promote=True)
    )
    check = promote_checklist(d)
    assert check["ready"] is False
    assert any(g["code"] == "open_question" for g in check["gaps"]["gaps"])


def test_promote_ready_when_minimal_clean() -> None:
    d = extract_from_text(
        "Employee submits a SpendRequest. Manager approves on their desk.",
        source_path="inline",
    )
    # Clear blocking questions for the test
    d.open_questions = [q for q in d.open_questions if not q.blocks_promote]
    for desk in d.desks:
        desk.owner_field_hint = desk.owner_field_hint or "requester"
    for n in d.nouns:
        n.owner_field_hint = n.owner_field_hint or "requester"
    if d.personas and d.nouns and not d.demo_spine:
        from dazzle.domain_brief.models import DemoSpineRow

        d.demo_spine = [
            DemoSpineRow(
                persona=d.personas[0].id_hint,
                story="has rows",
                entity_hint=d.nouns[0].name,
            )
        ]
    report = score_gaps(d)
    # May still warn on chrome_rejected etc.
    errors = [g for g in report.gaps if g.severity == "error"]
    assert not errors, errors
    assert report.ready_to_promote


def test_mcp_tool_registered() -> None:
    from dazzle.mcp.server.tools_consolidated import get_consolidated_tools

    tools = {t.name: t for t in get_consolidated_tools()}
    assert "domain" in tools
    ops = tools["domain"].inputSchema["properties"]["operation"]["enum"]
    assert "extract" in ops and "promote" in ops and "research" in ops


def test_mcp_handler_extract(tmp_path: Path) -> None:
    from dazzle.mcp.server.handlers.domain import domain_extract_handler

    raw = domain_extract_handler(
        tmp_path,
        {"spec_text": SPEND, "project_root": str(tmp_path), "write": True},
    )
    data = json.loads(raw)
    assert data.get("ok") is True
    assert (tmp_path / "AGENT_DOMAIN.md").is_file()
    assert "SpendRequest" in {n["name"] for n in data["domain"]["nouns"]}


def test_research_refuses_ungrounded_noun(tmp_path: Path) -> None:
    from dazzle.domain_brief import extract_from_text, research_and_save, save_domain

    d = extract_from_text(SPEND, source_path="inline")
    save_domain(tmp_path, d)
    (tmp_path / "SPEC.md").write_text(SPEND, encoding="utf-8")
    chrome = research_and_save(
        tmp_path,
        add_noun={"name": "Optional"},
        note="tried chrome",
    )
    assert any("noun_was_chrome" in r for r in (chrome.get("refused") or [])), chrome
    invent = research_and_save(
        tmp_path,
        add_noun={"name": "BookingRefund"},
    )
    assert any("noun_not_in_brief" in r for r in (invent.get("refused") or [])), invent
    assert "research_note" in (chrome.get("applied") or [])


def test_research_answers_question_and_sets_owner(tmp_path: Path) -> None:
    from dazzle.domain_brief import extract_from_text, load_domain, research_and_save, save_domain
    from dazzle.domain_brief.models import OpenQuestion

    d = extract_from_text(SPEND, source_path=str(tmp_path / "SPEC.md"))
    d.open_questions.append(OpenQuestion(id="q_block", text="threshold?", blocks_promote=True))
    save_domain(tmp_path, d)
    (tmp_path / "SPEC.md").write_text(SPEND, encoding="utf-8")
    result = research_and_save(
        tmp_path,
        answer_question_id="q_block",
        answer_text="Managers approve under 5k",
        set_owner_field="requester",
        owner_for="SpendRequest",
    )
    assert result.get("ok") is True
    assert any(a.startswith("answered:") for a in (result.get("applied") or []))
    loaded = load_domain(tmp_path)
    assert loaded is not None
    assert not any(q.id == "q_block" for q in loaded.open_questions)
    assert any(n.owner_field_hint == "requester" for n in loaded.nouns if n.name == "SpendRequest")


def test_bootstrap_instructions_are_domain_first() -> None:
    from dazzle.mcp.server.handlers.bootstrap import _build_instructions

    inst = _build_instructions(False, [], None)
    steps = "\n".join(inst["steps"])
    assert "AGENT_DOMAIN" in steps
    assert "analysis.entities" in steps
    assert "based on analysis" not in steps.lower() or "untrusted" in steps
    rules = "\n".join(inst["dsl_generation_rules"])
    assert "bootstrap_pollution" in rules


def test_cli_help_lists_domain() -> None:
    from typer.testing import CliRunner

    from dazzle.cli import app

    r = CliRunner().invoke(app, ["domain", "--help"])
    assert r.exit_code == 0
    assert "extract" in r.stdout
    assert "research" in r.stdout
