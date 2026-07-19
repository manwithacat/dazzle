"""Research into AGENT_DOMAIN — never invent chrome nouns.

Agents may answer open questions, append research notes, set owner hints,
and mark hypotheses. New domain nouns are refused unless the name already
appears in the founder brief (or an explicit grounded evidence string).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from dazzle.domain_brief.gaps import score_gaps
from dazzle.domain_brief.models import (
    AgentDomain,
    DemoSpineRow,
    DomainDesk,
    DomainNoun,
    DomainPersona,
)
from dazzle.domain_brief.store import load_domain, save_domain

# Markdown / form chrome that must never become domain nouns (even if present in brief text)
_CHROME_VOCAB = frozenset(
    {
        "optional",
        "field",
        "display",
        "type",
        "amount",  # column header alone is chrome without domain type context
        "required",
        "description",
        "value",
        "name",
        "status",
        "true",
        "false",
        "yes",
        "no",
        "null",
        "string",
        "integer",
        "boolean",
        "money",
        "uuid",
        "datetime",
        "date",
    }
)

_RULES = (
    "Research amends AGENT_DOMAIN only — not DSL",
    "Ungrounded nouns refused unless force_hypothesis (still not chrome)",
    "Promote only when gaps.ready_to_promote",
)


def _is_chrome(name: str) -> bool:
    return name.strip().lower() in _CHROME_VOCAB


def _brief_text(domain: AgentDomain, project_root: Path | None) -> str:
    """Best-effort founder prose for grounding checks."""
    if domain.source_path and domain.source_path not in ("inline", "provided_directly"):
        p = Path(domain.source_path)
        if p.is_file():
            return p.read_text(encoding="utf-8")
    if project_root is not None:
        for name in ("SPEC.md", "spec.md", "idea.md", "requirements.md"):
            p = project_root / name
            if p.is_file():
                return p.read_text(encoding="utf-8")
    bits = [domain.summary or ""]
    bits.extend(n.evidence for n in domain.nouns if n.evidence)
    bits.extend(p.evidence for p in domain.personas if p.evidence)
    return "\n".join(bits)


def _grounded(name: str, brief: str) -> bool:
    if not name or not brief:
        return False
    return bool(re.search(rf"\b{re.escape(name)}\b", brief, re.I))


def _name_match(a: str, b: str) -> bool:
    return a == b or a.lower() == b.lower()


def _apply_note(domain: AgentDomain, note: str | None, applied: list[str]) -> None:
    if note and note.strip():
        domain.research_notes.append(note.strip())
        applied.append("research_note")


def _apply_answer(
    domain: AgentDomain,
    qid: str | None,
    answer_text: str | None,
    applied: list[str],
    refused: list[str],
) -> None:
    if not qid:
        return
    for q in domain.open_questions:
        if q.id != qid:
            continue
        ans = (answer_text or "").strip()
        if ans:
            domain.research_notes.append(f"Answered {qid}: {ans}")
        q.blocks_promote = False
        applied.append(f"answered:{qid}")
        return
    refused.append(f"unknown_question:{qid}")


def _apply_clear(
    domain: AgentDomain,
    clear_question_id: str | None,
    applied: list[str],
    refused: list[str],
) -> None:
    if not clear_question_id:
        return
    before = len(domain.open_questions)
    domain.open_questions = [q for q in domain.open_questions if q.id != clear_question_id]
    if len(domain.open_questions) < before:
        applied.append(f"cleared:{clear_question_id}")
    else:
        refused.append(f"unknown_question:{clear_question_id}")


def _apply_owner(
    domain: AgentDomain,
    set_owner_field: str | None,
    owner_for: str | None,
    applied: list[str],
    refused: list[str],
) -> None:
    if not set_owner_field or not owner_for:
        return
    hit = False
    for n in domain.nouns:
        if _name_match(n.name, owner_for):
            n.owner_field_hint = set_owner_field
            hit = True
            applied.append(f"owner_noun:{n.name}")
    for d in domain.desks:
        if d.name == owner_for or d.persona == owner_for:
            d.owner_field_hint = set_owner_field
            hit = True
            applied.append(f"owner_desk:{d.name}")
    if not hit:
        refused.append(f"owner_target_missing:{owner_for}")


def _persona_refusal(
    domain: AgentDomain,
    label: str,
    pid: str,
    brief: str,
    force_hypothesis: bool,
) -> str | None:
    if not label:
        return "persona_missing_label"
    if not _grounded(label, brief) and not force_hypothesis:
        return f"persona_not_in_brief:{label}"
    if any(p.id_hint == pid for p in domain.personas):
        return f"persona_exists:{pid}"
    return None


def _apply_persona(
    domain: AgentDomain,
    add_persona: dict[str, Any] | None,
    brief: str,
    applied: list[str],
    refused: list[str],
) -> None:
    if not add_persona:
        return
    label = str(add_persona.get("label") or add_persona.get("name") or "").strip()
    pid = str(add_persona.get("id_hint") or (label.lower().replace(" ", "_") if label else ""))
    err = _persona_refusal(domain, label, pid, brief, bool(add_persona.get("force_hypothesis")))
    if err:
        refused.append(err)
        return
    desk = str(add_persona.get("desk") or f"{pid}_desk")
    status = "hypothesis" if add_persona.get("force_hypothesis") else "grounded"
    domain.personas.append(
        DomainPersona(
            id_hint=pid,
            label=label,
            job=str(add_persona.get("job") or ""),
            desk=desk,
            stable_id_candidate=str(add_persona.get("stable_id") or pid),
            status=status,  # type: ignore[arg-type]
            evidence=str(add_persona.get("evidence") or "research op"),
        )
    )
    domain.desks.append(
        DomainDesk(
            persona=pid,
            name=desk,
            purpose=str(add_persona.get("purpose") or f"Job desk for {label}"),
            owner_field_hint=add_persona.get("owner_field_hint"),
            status="hypothesis",
        )
    )
    applied.append(f"persona:{pid}")


def _noun_is_chrome(name: str, domain: AgentDomain) -> bool:
    if _is_chrome(name):
        return True
    if name in domain.rejected_chrome:
        return True
    return name.lower() in {c.lower() for c in domain.rejected_chrome}


def _apply_noun(
    domain: AgentDomain,
    add_noun: dict[str, Any] | None,
    brief: str,
    applied: list[str],
    refused: list[str],
) -> None:
    if not add_noun:
        return
    name = str(add_noun.get("name") or "").strip()
    if not name:
        refused.append("noun_missing_name")
        return
    if _noun_is_chrome(name, domain):
        refused.append(f"noun_was_chrome:{name}")
        return
    if not _grounded(name, brief) and not add_noun.get("force_hypothesis"):
        refused.append(f"noun_not_in_brief:{name}")
        return
    if any(n.name == name for n in domain.nouns):
        refused.append(f"noun_exists:{name}")
        return
    status = "hypothesis" if add_noun.get("force_hypothesis") else "grounded"
    domain.nouns.append(
        DomainNoun(
            name=name,
            status=status,  # type: ignore[arg-type]
            evidence=str(add_noun.get("evidence") or "research op"),
            lifecycle_hint=list(add_noun.get("lifecycle_hint") or []),
            owner_field_hint=add_noun.get("owner_field_hint"),
        )
    )
    applied.append(f"noun:{name}")


def _apply_spine(
    domain: AgentDomain,
    add_spine: dict[str, Any] | None,
    applied: list[str],
    refused: list[str],
) -> None:
    if not add_spine:
        return
    persona = str(add_spine.get("persona") or "").strip()
    story = str(add_spine.get("story") or "").strip()
    if not persona or not story:
        refused.append("spine_incomplete")
        return
    domain.demo_spine.append(
        DemoSpineRow(
            persona=persona,
            story=story,
            min_rows=int(add_spine.get("min_rows") or 1),
            entity_hint=add_spine.get("entity_hint"),
        )
    )
    applied.append(f"spine:{persona}")


def _apply_hypothesis(
    domain: AgentDomain,
    mark_hypothesis: str | None,
    applied: list[str],
    refused: list[str],
) -> None:
    if not mark_hypothesis:
        return
    for n in domain.nouns:
        if _name_match(n.name, mark_hypothesis):
            n.status = "hypothesis"
            applied.append(f"hypothesis:{n.name}")
            return
    refused.append(f"hypothesis_target_missing:{mark_hypothesis}")


def _prune_answered_questions(domain: AgentDomain, answer_question_id: str | None) -> None:
    domain.open_questions = [
        q
        for q in domain.open_questions
        if q.blocks_promote or (answer_question_id and q.id == answer_question_id)
    ]
    if answer_question_id:
        domain.open_questions = [q for q in domain.open_questions if q.id != answer_question_id]


def apply_research(
    domain: AgentDomain,
    *,
    project_root: Path | None = None,
    note: str | None = None,
    answer_question_id: str | None = None,
    answer_text: str | None = None,
    clear_question_id: str | None = None,
    set_owner_field: str | None = None,
    owner_for: str | None = None,
    add_persona: dict[str, Any] | None = None,
    add_noun: dict[str, Any] | None = None,
    add_spine: dict[str, Any] | None = None,
    mark_hypothesis: str | None = None,
) -> dict[str, Any]:
    """Mutate domain in place; return applied/refused summary."""
    brief = _brief_text(domain, project_root)
    applied: list[str] = []
    refused: list[str] = []

    _apply_note(domain, note, applied)
    _apply_answer(domain, answer_question_id, answer_text, applied, refused)
    _apply_clear(domain, clear_question_id, applied, refused)
    _apply_owner(domain, set_owner_field, owner_for, applied, refused)
    _apply_persona(domain, add_persona, brief, applied, refused)
    _apply_noun(domain, add_noun, brief, applied, refused)
    _apply_spine(domain, add_spine, applied, refused)
    _apply_hypothesis(domain, mark_hypothesis, applied, refused)
    _prune_answered_questions(domain, answer_question_id)

    gaps = score_gaps(domain)
    return {
        "ok": True,
        "applied": applied,
        "refused": refused,
        "gaps": gaps.to_dict(),
        "rules": list(_RULES),
    }


def research_and_save(
    project_root: Path,
    **kwargs: Any,
) -> dict[str, Any]:
    """Load domain, apply research, optionally save."""
    root = project_root.resolve()
    domain = load_domain(root)
    if domain is None:
        return {
            "ok": False,
            "error": "No AGENT_DOMAIN",
            "hint": "domain(operation='extract') first",
        }
    write = kwargs.pop("write", True)
    result = apply_research(domain, project_root=root, **kwargs)
    paths: dict[str, str] = {}
    if write and result.get("applied"):
        paths = save_domain(root, domain)
    result["written"] = paths
    result["domain"] = domain.to_dict()
    return result
