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


def test_extract_owner_hint_from_owned_by_prose() -> None:
    """Phrase forms (owned by / assigned to) must bind desks — not only bare field tokens.

    Regression: project_tracker SPEC blocked promote with q_owner despite clear ownership language.
    """
    brief = """
# Project Tracker

Projects owned by a team member, broken into Tasks assigned to them.
Admin and Manager and Member roles share the work.
"""
    d = extract_from_text(brief, source_path="inline")
    assert any(desk.owner_field_hint for desk in d.desks), (
        f"expected owner_field_hint on desks, got {[d.owner_field_hint for d in d.desks]}"
    )
    assert not any(q.id == "q_owner" and q.blocks_promote for q in d.open_questions)


def test_extract_owner_hint_from_self_scope_prose() -> None:
    """HR-style self-scope prose must bind desks via ``person`` — not leave q_owner open.

    Regression: hr_records SPEC says "self only / own employment / direct reports"
    with no owner/assignee token; promote was blocked on q_owner (cycle 1367).
    """
    brief = """
# HR Records

A personnel system for staff. Line Manager sees direct reports.
Employee scope: Read self only — own employment history and own salary history.
Admin and Manager and Finance and Employee roles use the system.
"""
    d = extract_from_text(brief, source_path="inline")
    assert any(desk.owner_field_hint == "person" for desk in d.desks), (
        f"expected person owner_field_hint on desks, got {[d.owner_field_hint for d in d.desks]}"
    )
    assert not any(q.id == "q_owner" and q.blocks_promote for q in d.open_questions)


def test_extract_owner_hint_from_ack_prose() -> None:
    """Ops/SRE briefs bind desks via acknowledgment — not leave q_owner open.

    Regression: ops_dashboard SPEC documents ``acknowledged_by`` + ack_queue /
    "what needs me" with no owner/assignee token; promote was blocked on q_owner
    (cycle 1370).
    """
    brief = """
# Operations Dashboard

Engineers monitor system health and respond to alerts.
Acknowledgement queue (ack_queue) for unacked alerts by severity.
Task inbox for multi-source "what needs me" ops work.
Who acknowledged the alert is recorded on ``acknowledged_by``.
Engineer and User roles use the command center.
"""
    d = extract_from_text(brief, source_path="inline")
    assert any(desk.owner_field_hint == "acknowledged_by" for desk in d.desks), (
        f"expected acknowledged_by owner_field_hint on desks, "
        f"got {[d.owner_field_hint for d in d.desks]}"
    )
    assert not any(q.id == "q_owner" and q.blocks_promote for q in d.open_questions)


def test_extract_owner_hint_from_designer_draft_prose() -> None:
    """Creative-ops briefs bind via created_by when designers draft assets.

    Regression: design_studio SPECIFICATION uses \"designers draft assets\" /
    \"creates and manages design\" without bare ``created_by`` token; re-extract
    dropped desk owner_field_hint and re-opened q_owner (cycle 1372).
    """
    brief = """
# Design Studio

Design Studio is a creative-operations system. A Brand is a product line.
A Design Asset is creative work. Designers draft assets for a brand.
Designer — creates and manages design assets.
Admin and Designer and Reviewer roles use the studio.
"""
    d = extract_from_text(brief, source_path="inline")
    assert any(desk.owner_field_hint == "created_by" for desk in d.desks), (
        f"expected created_by owner_field_hint on desks, "
        f"got {[d.owner_field_hint for d in d.desks]}"
    )
    assert not any(q.id == "q_owner" and q.blocks_promote for q in d.open_questions)


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


def test_broken_cardinality_questions_filtered() -> None:
    """generate_questions sometimes emits function-word plurals / verb-as-noun.

    Regression: domain_join_co SPECIFICATION.md open_qs included
    \"Can a operate have multiple wheres\" / \"multiple theirs\" (cycle 1370).
    Cycle 1372: \"members and 7 tasks\" → multiple 7s; progress → progres;
    indicators and overdue → overdues.
    """
    from dazzle.domain_brief.extract import _is_noise_or_broken_question

    brief = (
        "# Domain Join Co\n\nA company proves its email domain; members join "
        "a workspace. Admin and Member roles use the system.\n"
    )
    broken = [
        "Can a operate have multiple wheres, or just one?",
        "Can a member have multiple theirs, or just one?",
        "Can a operate have multiple thes, or just one?",
        "Can a member have multiple 7s, or just one?",
        "Can a progres have multiple workloads, or just one?",
        "Can a indicator have multiple overdues, or just one?",
        "Can a task have multiple assignmentss, or just one?",
        # Cycle 1375: wrong indefinite article before vowel-onset subjects
        "Can a organization have multiple audits, or just one?",
        "Can a invoice have multiple payments, or just one?",
        "Can a admin have multiple designers, or just one?",
        # Cycle 1377: RBAC/verb fragments as cardinality objects
        "Can a role have multiple quorums, or just one?",
        "Can a task have multiple tracks, or just one?",
        "Can a role have multiple queues, or just one?",
        # Cycle 1378: persona subjects + org/det chrome as objects
        "Can an admin have multiple designers, or just one?",
        "Can an admin have multiple members, or just one?",
        "Can a manager have multiple administrators, or just one?",
        "Can a task have multiple teams, or just one?",
        "Can a customer have multiple teams, or just one?",
        "Can a tenant have multiple theirs, or just one?",
        "Can a brand have multiple thes, or just one?",
    ]
    for q in broken:
        assert _is_noise_or_broken_question(q, brief), q
    # Real cardinality questions must still pass the filter
    ok = "Can a Workspace have multiple Announcements, or just one?"
    assert not _is_noise_or_broken_question(ok, brief), ok
    ok_an = "Can an Organization have multiple Audits, or just one?"
    assert not _is_noise_or_broken_question(ok_an, brief), ok_an


def test_generate_questions_skips_digit_and_prose_cardinality() -> None:
    """Cardinality pairs must be letter-only and entity-grounded when entities given."""
    import json

    from dazzle.mcp.server.handlers.spec_analyze import _generate_questions

    # "members and 7 tasks" must not yield "multiple 7s"
    # "progress and workload" must not yield "progres" / "workloads"
    spec = (
        "Pre-populated with 5 team members and 7 tasks. "
        "Managers track progress and workload. "
        "Warning indicators and overdue filtering. "
        "Oversee team tasks and assignments. "
        "A Task is a unit of work. A User is a person.\n"
    )
    data = json.loads(
        _generate_questions(
            {
                "spec_text": spec,
                "entities": ["Task", "User"],
            }
        )
    )
    texts = [q.get("question", "") for q in data.get("questions", [])]
    card = [t for t in texts if "multiple" in t.lower()]
    joined = " | ".join(card)
    assert "7s" not in joined, card
    assert "progres" not in joined.lower(), card
    assert "overdue" not in joined.lower(), card
    # Entity-grounded real pair from "tasks and assignments"
    assert any("task" in t.lower() and "assignment" in t.lower() for t in card), card


def test_generate_questions_skips_role_quorum_and_track_fragments() -> None:
    """RBAC 'roles and quorums' and verb 'track' must not become cardinality qs.

    Cycle 1377: invoice_ops open_qs had \"Can a role have multiple quorums\";
    simple_task had \"Can a task have multiple tracks\" from track-progress prose.
    """
    import json

    from dazzle.mcp.server.handlers.spec_analyze import _generate_questions

    spec = (
        "Approval roles and quorums gate payments. "
        "Roles and queues route work. "
        "Managers track progress on tasks and track status. "
        "Tasks and assignments bind work. "
        "A Task is a unit of work. A Payment is settlement. "
        "An Assignment links a person to a task.\n"
    )
    data = json.loads(
        _generate_questions(
            {
                "spec_text": spec,
                "entities": ["Task", "Payment", "Assignment"],
            }
        )
    )
    texts = [q.get("question", "") for q in data.get("questions", [])]
    card = [t for t in texts if "multiple" in t.lower()]
    joined = " | ".join(card).lower()
    assert "quorum" not in joined, card
    assert "queue" not in joined, card
    assert "track" not in joined, card
    assert "role" not in joined, card
    assert any("task" in t.lower() and "assignment" in t.lower() for t in card), card


def test_generate_questions_skips_persona_subjects_and_det_chrome() -> None:
    """Persona pairs and determiner/org chrome must not become cardinality qs.

    Cycle 1378: design_studio \"admins and designers\" → admin/designers;
    domain_join admin/members; \"tenants and their\" → multiple theirs;
    \"brands and the visibility\" → multiple thes; task/customer + teams.
    """
    import json

    from dazzle.mcp.server.handlers.spec_analyze import _generate_questions

    spec = (
        "Three kinds of people work in the system — admins and designers "
        "and reviewers land on desks. "
        "Workspace admins and members share announcements. "
        "Managers and administrators oversee the fleet. "
        "Tenants and their people share storage. "
        "Brands and the visibility rules compile. "
        "Customers and teams file tickets. "
        "Tasks and teams coordinate delivery. "
        "Tasks and assignments bind work. "
        "A Task is a unit of work. A Brand owns assets. "
        "An Assignment links a person to a task. A Brand is a label.\n"
    )
    data = json.loads(
        _generate_questions(
            {
                "spec_text": spec,
                "entities": ["Task", "Brand", "Assignment"],
            }
        )
    )
    texts = [q.get("question", "") for q in data.get("questions", [])]
    card = [t for t in texts if "multiple" in t.lower()]
    joined = " | ".join(card).lower()
    assert "admin" not in joined, card
    assert "designer" not in joined, card
    assert "manager" not in joined, card
    assert "theirs" not in joined, card
    assert " thes" not in joined and "multiple thes" not in joined, card
    assert "team" not in joined, card
    assert any("task" in t.lower() and "assignment" in t.lower() for t in card), card


def test_generate_questions_indefinite_article_and_review_signal() -> None:
    """Vowel-onset subjects use *an*; lifecycle 'review' is not bilateral ratings.

    Cycle 1375: fleet open_qs had \"Can a organization\" / \"Can a invoice\" /
    \"Can a admin\", and bilateral-review fired on todo→review→done SPECs.
    """
    import json
    import re

    from dazzle.mcp.server.handlers.spec_analyze import (
        _bilateral_review_signal,
        _generate_questions,
        _indefinite_article,
    )

    assert _indefinite_article("organization") == "an"
    assert _indefinite_article("invoice") == "an"
    assert _indefinite_article("admin") == "an"
    assert _indefinite_article("task") == "a"
    assert _indefinite_article("user") == "a"  # /juː/ consonant sound
    assert _indefinite_article("User") == "a"

    # Lifecycle / permission "review" alone must not ask bilateral ratings
    assert not _bilateral_review_signal(
        "tasks move todo through review to done; permission review is audited"
    )
    # Bare "feedback is scattered" is ops pain, not a Review entity
    assert not _bilateral_review_signal("currently feedback is scattered across slack and email")
    assert _bilateral_review_signal("buyers leave a review after the job")
    assert _bilateral_review_signal("collect star ratings from buyers")
    assert _bilateral_review_signal("design feedback moves assets to approval")

    spec = (
        "Organizations and audits form the tenancy model. "
        "Invoices and payments settle bills. "
        "Admins and designers collaborate on assets. "
        "A Task moves todo through review to done. "
        "An Organization is tenancy. An Invoice is a bill. "
        "An Admin is staff. A Designer is creative. "
        "A Payment is settlement. An Audit is a check.\n"
    )
    data = json.loads(
        _generate_questions(
            {
                "spec_text": spec,
                "entities": [
                    "Organization",
                    "Invoice",
                    "Admin",
                    "Designer",
                    "Payment",
                    "Audit",
                ],
            }
        )
    )
    texts = [q.get("question", "") for q in data.get("questions", [])]
    card = [t for t in texts if "multiple" in t.lower()]
    joined = " | ".join(texts)
    # No wrong article before vowel-onset subjects
    assert not re.search(r"\bCan a (organization|invoice|admin)\b", joined, re.I), texts
    assert any(re.search(r"\bCan an organization\b", t, re.I) for t in card), card
    assert any(re.search(r"\bCan an invoice\b", t, re.I) for t in card), card
    # Cycle 1378: persona stems (admin/designer) are BAD_LEFT — article helper
    # still returns *an* for "admin", but cardinality no longer emits them.
    assert not any(re.search(r"\bCan an admin\b", t, re.I) for t in card), card
    assert "designer" not in " | ".join(card).lower(), card
    # No bilateral-review topic from lifecycle prose
    assert not any("both parties leave reviews" in t.lower() for t in texts), texts
    # Lifecycle "projects and reviews" style must not emit review cardinality
    assert not any(re.search(r"\bmultiple reviews\b", t, re.I) for t in card), card


def test_extract_an_article_and_product_title_not_fused() -> None:
    """'An Invoice is …' → Invoice; 'Acme Billing is …' is product title, not AcmeBilling."""
    brief = """
# Acme Billing — System Specification

Acme Billing is a multi-organization billing system.

**Organizations.** An Organization is the root of the tenancy model.
**Invoices.** An Invoice is a billing record always raised against a Project.
A Project always belongs to an Organization. A User is a person's record.

## Who uses it

- **Auditor** — reviews invoices
- **Admin** — platform administrator
"""
    d = extract_from_text(brief, source_path="SPECIFICATION.md")
    names = {n.name for n in d.nouns}
    assert "Organization" in names
    assert "Invoice" in names
    # "User" is persona-chrome deny; Project may arrive via discover on longer SPECs
    junk = {"AnInvoice", "AnOrganization", "AcmeBilling", "Acme", "Billing"}
    assert not (names & junk), names


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
