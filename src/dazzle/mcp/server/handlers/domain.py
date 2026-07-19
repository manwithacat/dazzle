"""MCP handlers for agent-audience domain brief (ADR-0002 reads + extract write via paths)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dazzle.domain_brief import (
    extract_from_path,
    extract_from_text,
    find_founder_brief,
    load_domain,
    promote_checklist,
    research_and_save,
    save_domain,
    score_gaps,
)
from dazzle.mcp.server.handlers.common import wrap_handler_errors


@wrap_handler_errors
def domain_extract_handler(project_path: Path, args: dict[str, Any]) -> str:
    """Extract AGENT_DOMAIN from founder brief; write md+json by default."""
    root = Path(args["project_root"]) if args.get("project_root") else project_path
    root = root.resolve()
    write = args.get("write", True)
    if args.get("spec_text"):
        domain = extract_from_text(str(args["spec_text"]), source_path="provided_directly")
    else:
        path = Path(args["spec_path"]) if args.get("spec_path") else find_founder_brief(root)
        if path is None or not Path(path).is_file():
            return json.dumps(
                {
                    "error": "No founder brief found",
                    "hint": "Pass spec_text or spec_path, or create SPEC.md",
                },
                indent=2,
            )
        domain = extract_from_path(Path(path))

    paths: dict[str, str] = {}
    if write:
        paths = save_domain(root, domain)
    gaps = score_gaps(domain)
    return json.dumps(
        {
            "ok": True,
            "domain": domain.to_dict(),
            "gaps": gaps.to_dict(),
            "written": paths,
            "rules": [
                "AGENT_DOMAIN is cognition draft — not DSL SSOT",
                "Do not invent chrome entities; rejected_chrome listed",
                "Research into open_questions / research_notes only",
                "Promote only when gaps.ready_to_promote",
            ],
        },
        indent=2,
    )


@wrap_handler_errors
def domain_show_handler(project_path: Path, args: dict[str, Any]) -> str:
    root = Path(args["project_root"]) if args.get("project_root") else project_path
    domain = load_domain(root.resolve())
    if domain is None:
        return json.dumps(
            {"error": "No AGENT_DOMAIN", "hint": "domain(operation='extract') first"},
            indent=2,
        )
    gaps = score_gaps(domain)
    return json.dumps({"domain": domain.to_dict(), "gaps": gaps.to_dict()}, indent=2)


@wrap_handler_errors
def domain_gaps_handler(project_path: Path, args: dict[str, Any]) -> str:
    root = Path(args["project_root"]) if args.get("project_root") else project_path
    domain = load_domain(root.resolve())
    if domain is None:
        return json.dumps({"error": "No AGENT_DOMAIN"}, indent=2)
    return json.dumps(score_gaps(domain).to_dict(), indent=2)


@wrap_handler_errors
def domain_promote_handler(project_path: Path, args: dict[str, Any]) -> str:
    root = Path(args["project_root"]) if args.get("project_root") else project_path
    domain = load_domain(root.resolve())
    if domain is None:
        return json.dumps({"error": "No AGENT_DOMAIN"}, indent=2)
    return json.dumps(promote_checklist(domain), indent=2)


@wrap_handler_errors
def domain_research_handler(project_path: Path, args: dict[str, Any]) -> str:
    """Amend AGENT_DOMAIN via research (answers, notes, grounded adds). Never writes DSL."""
    root = Path(args["project_root"]) if args.get("project_root") else project_path
    root = root.resolve()
    result = research_and_save(
        root,
        write=args.get("write", True),
        note=args.get("note"),
        answer_question_id=args.get("answer_question_id"),
        answer_text=args.get("answer_text"),
        clear_question_id=args.get("clear_question_id"),
        set_owner_field=args.get("set_owner_field"),
        owner_for=args.get("owner_for"),
        add_persona=args.get("add_persona"),
        add_noun=args.get("add_noun"),
        add_spine=args.get("add_spine"),
        mark_hypothesis=args.get("mark_hypothesis"),
    )
    return json.dumps(result, indent=2)
