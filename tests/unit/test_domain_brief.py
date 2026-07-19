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
    assert "extract" in ops and "promote" in ops


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


def test_cli_help_lists_domain() -> None:
    from typer.testing import CliRunner

    from dazzle.cli import app

    r = CliRunner().invoke(app, ["domain", "--help"])
    assert r.exit_code == 0
    assert "extract" in r.stdout
