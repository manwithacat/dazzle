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
    # Fall back to summary + existing evidence
    bits = [domain.summary or ""]
    bits.extend(n.evidence for n in domain.nouns if n.evidence)
    bits.extend(p.evidence for p in domain.personas if p.evidence)
    return "\n".join(bits)


def _grounded(name: str, brief: str) -> bool:
    if not name or not brief:
        return False
    return bool(re.search(rf"\b{re.escape(name)}\b", brief, re.I))


def apply_research(
    domain: AgentDomain,
    *,
    project_root: Path | None = None,
    note: str | None = None,
    answer_question_id: str | None = None,
    answer_text: str | None = None,
    clear_question_id: str | None = None,
    set_owner_field: str | None = None,
    owner_for: str | None = None,  # noun name or desk name
    add_persona: dict[str, Any] | None = None,
    add_noun: dict[str, Any] | None = None,
    add_spine: dict[str, Any] | None = None,
    mark_hypothesis: str | None = None,  # noun name → status hypothesis
) -> dict[str, Any]:
    """Mutate domain in place; return applied/refused summary."""
    brief = _brief_text(domain, project_root)
    applied: list[str] = []
    refused: list[str] = []

    if note and note.strip():
        domain.research_notes.append(note.strip())
        applied.append("research_note")

    if answer_question_id:
        qid = answer_question_id
        found = False
        for q in domain.open_questions:
            if q.id == qid:
                found = True
                ans = (answer_text or "").strip()
                if ans:
                    domain.research_notes.append(f"Answered {qid}: {ans}")
                q.blocks_promote = False
                applied.append(f"answered:{qid}")
                break
        if not found:
            refused.append(f"unknown_question:{qid}")

    if clear_question_id:
        before = len(domain.open_questions)
        domain.open_questions = [q for q in domain.open_questions if q.id != clear_question_id]
        if len(domain.open_questions) < before:
            applied.append(f"cleared:{clear_question_id}")
        else:
            refused.append(f"unknown_question:{clear_question_id}")

    if set_owner_field and owner_for:
        target = owner_for
        hit = False
        for n in domain.nouns:
            if n.name == target or n.name.lower() == target.lower():
                n.owner_field_hint = set_owner_field
                hit = True
                applied.append(f"owner_noun:{n.name}")
        for d in domain.desks:
            if d.name == target or d.persona == target:
                d.owner_field_hint = set_owner_field
                hit = True
                applied.append(f"owner_desk:{d.name}")
        if not hit:
            refused.append(f"owner_target_missing:{target}")

    if add_persona:
        label = str(add_persona.get("label") or add_persona.get("name") or "").strip()
        if not label:
            refused.append("persona_missing_label")
        elif not _grounded(label, brief) and not add_persona.get("force_hypothesis"):
            refused.append(f"persona_not_in_brief:{label}")
        else:
            pid = str(add_persona.get("id_hint") or label.lower().replace(" ", "_"))
            if any(p.id_hint == pid for p in domain.personas):
                refused.append(f"persona_exists:{pid}")
            else:
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

    if add_noun:
        name = str(add_noun.get("name") or "").strip()
        if not name:
            refused.append("noun_missing_name")
        elif (
            _is_chrome(name)
            or name in domain.rejected_chrome
            or name.lower() in {c.lower() for c in domain.rejected_chrome}
        ):
            refused.append(f"noun_was_chrome:{name}")
        elif not _grounded(name, brief) and not add_noun.get("force_hypothesis"):
            refused.append(f"noun_not_in_brief:{name}")
        elif any(n.name == name for n in domain.nouns):
            refused.append(f"noun_exists:{name}")
        else:
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

    if add_spine:
        persona = str(add_spine.get("persona") or "").strip()
        story = str(add_spine.get("story") or "").strip()
        if not persona or not story:
            refused.append("spine_incomplete")
        else:
            domain.demo_spine.append(
                DemoSpineRow(
                    persona=persona,
                    story=story,
                    min_rows=int(add_spine.get("min_rows") or 1),
                    entity_hint=add_spine.get("entity_hint"),
                )
            )
            applied.append(f"spine:{persona}")

    if mark_hypothesis:
        hit = False
        for n in domain.nouns:
            if n.name == mark_hypothesis or n.name.lower() == mark_hypothesis.lower():
                n.status = "hypothesis"
                hit = True
                applied.append(f"hypothesis:{n.name}")
        if not hit:
            refused.append(f"hypothesis_target_missing:{mark_hypothesis}")

    # Drop empty open-question shells that no longer block
    domain.open_questions = [
        q
        for q in domain.open_questions
        if q.blocks_promote or (answer_question_id and q.id == answer_question_id)
    ]
    # If answered, remove non-blocking answered questions from list (kept in notes)
    if answer_question_id:
        domain.open_questions = [q for q in domain.open_questions if q.id != answer_question_id]

    gaps = score_gaps(domain)
    return {
        "ok": True,
        "applied": applied,
        "refused": refused,
        "gaps": gaps.to_dict(),
        "rules": [
            "Research amends AGENT_DOMAIN only — not DSL",
            "Ungrounded nouns refused unless force_hypothesis (still not chrome)",
            "Promote only when gaps.ready_to_promote",
        ],
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
