"""Extract AgentDomain from founder prose — offline, chrome-safe."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from dazzle.domain_brief.models import (
    AgentDomain,
    DemoSpineRow,
    DomainDesk,
    DomainNoun,
    DomainPersona,
    OpenQuestion,
)

_STABLE_ALIASES: dict[str, str] = {
    "employee": "employee",
    "member": "member",
    "manager": "manager",
    "admin": "admin",
    "finance": "finance",
    "approver": "approver",
    "requester": "requester",
    "agent": "agent",
    "customer": "customer",
    "tester": "tester",
    "engineer": "engineer",
    "designer": "designer",
    "reviewer": "reviewer",
    "ops": "ops_engineer",
    "ops_engineer": "ops_engineer",
    "hr": "hr_admin",
    "auditor": "auditor",
    "user": "user",
}

_OWNER_HINTS = (
    "requester",
    "submitted_by",
    "assigned_to",
    "created_by",
    "owner",
    "reported_by_id",
)

_ROLE_RE = re.compile(
    r"\b(Employee|Manager|Finance|Approver|Requester|Member|Agent|"
    r"Customer|Tester|Engineer|Designer|Reviewer|Auditor|Admin)\b"
)
_NOISE_Q_RE = re.compile(
    r"\b(booking|refund|hotel|flight|email/push|message each other|notification)\b",
    re.I,
)
_NOISE_BRIEF_RE = re.compile(
    r"\b(booking|refund|hotel|flight|notification|message)\b",
    re.I,
)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _slug(label: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
    return s or "persona"


def _grounded_in_brief(name: str, brief: str) -> bool:
    if not name:
        return False
    return bool(re.search(rf"\b{re.escape(name)}\b", brief, re.I))


def _stable_for(label: str) -> str:
    key = _slug(label)
    if key in _STABLE_ALIASES:
        return _STABLE_ALIASES[key]
    return _STABLE_ALIASES.get(key.rstrip("s"), key)


def _desk_name(persona_id: str) -> str:
    return f"{persona_id}_desk"


def _owner_for_noun(name: str, text: str) -> str | None:
    for h in _OWNER_HINTS:
        if re.search(rf"\b{h}\b", text, re.I):
            return h
    if re.search(r"(request|ticket|task|issue)$", name, re.I):
        return "requester" if re.search(r"request$", name, re.I) else "assigned_to"
    return None


def _run_offline_analyses(
    text: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    from dazzle.mcp.server.handlers.spec_analyze import handle_spec_analyze

    entities_raw = json.loads(
        handle_spec_analyze({"operation": "discover_entities", "spec_text": text})
    )
    personas_raw = json.loads(
        handle_spec_analyze({"operation": "extract_personas", "spec_text": text})
    )
    entity_names = [
        e.get("name", "")
        for e in entities_raw.get("entities", [])
        if isinstance(e, dict) and e.get("name")
    ]
    lifecycles_raw = json.loads(
        handle_spec_analyze(
            {
                "operation": "identify_lifecycles",
                "spec_text": text,
                "entities": entity_names,
            }
        )
    )
    questions_raw = json.loads(
        handle_spec_analyze(
            {
                "operation": "generate_questions",
                "spec_text": text,
                "entities": entity_names,
            }
        )
    )
    return entities_raw, personas_raw, lifecycles_raw, questions_raw


def _life_by_entity(lifecycles_raw: dict[str, Any]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for lc in lifecycles_raw.get("lifecycles", []):
        if not isinstance(lc, dict):
            continue
        ent = str(lc.get("entity") or "")
        states = [str(s) for s in (lc.get("states") or []) if s]
        if ent and states:
            out[ent] = states
    return out


# Adjectives / verbs / UI / status chrome that discover_entities still emits on long SPECs
_NOUN_DENY = frozenset(
    {
        "urgent",
        "several",
        "specific",
        "discrete",
        "right",
        "need",
        "create",
        "test",
        "demo",
        "work",
        "list",
        "level",
        "state",
        "mix",
        "pre",
        "surface",
        "control",
        "scenario",
        "completed",
        "review",
        "transition",
        "implementation",
        "development",
        "organization",
        "intention",
        "declared",
        "various",
        "require",
        "signal",
        "variant",
        "progre",
        "workload",
        "lifecycle",
        "machine",
        "administrator",
        "team",  # too generic alone unless CamelCase compound
        # status / severity / lifecycle adjectives (fieldtest-class SPECs)
        "retired",
        "recalled",
        "prototype",
        "active",
        "draft",
        "released",
        "deprecated",
        "cancelled",
        "canceled",
        "triaged",
        "fixed",
        "verified",
        "closed",
        "open",
        "critical",
        "high",
        "medium",
        "low",
        "casual",
        "enthusiast",
        "indoor",
        "outdoor",
        "vehicle",
        "industrial",
        "full",
        "auto",
        "automated",
        "assigned",
        "connectivity",
        "mechanical",
        "battery",
        "crash",
        "other",
        # UI / workspace chrome mistaken for entities
        "kanban",
        "timeline",
        "dashboard",
        "queue",
        "page",
        "directory",
        "report",
        "board",
        "filter",
        "form",
        "detail",
        "number",
        "date",
        "version",
        "hardware",
        "capture",
        "assign",
        "update",
        "batch",
        "release",
        "session",
        "result",
        "problem",
        "latch",
        "recall",
        "triage",
        "cluster",
        "wearable",
        "engineer",  # persona title alone
        "tester",
        "manager",
        "admin",
        "user",
        "member",
    }
)

# ### **Device** under Core Entities — not every H2/H3 in a long SPEC
_CORE_ENTITY_SECTION_RE = re.compile(r"(?is)##\s*core\s+entities\b(.*?)(?=\n##\s+(?!#))")
_ENTITY_HEADER_RE = re.compile(
    r"^#{3,4}\s+\*{0,2}([A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+)*)\*{0,2}\s*$",
    re.M,
)


def _header_entities(text: str) -> set[str]:
    """Entity titles under ``## Core Entities`` (### **Device**)."""
    out: set[str] = set()
    section = _CORE_ENTITY_SECTION_RE.search(text)
    body = section.group(1) if section else ""
    if not body:
        return out
    for m in _ENTITY_HEADER_RE.finditer(body):
        label = m.group(1).strip()
        compact = re.sub(r"\s+", "", label)
        out.add(compact)
        if " " not in label:
            out.add(label)
    return out


def _strong_noun_signal(
    name: str,
    source: str,
    text: str,
    *,
    header_names: set[str],
) -> bool:
    """Prefer deliberate domain types over mid-sentence capital adjectives."""
    if re.search(r"[a-z][A-Z]", name):  # CamelCase multi-hump
        return True
    if name in header_names or name.replace(" ", "") in header_names:
        return True
    if re.search(rf"\b(entity|record|type|model)\s+{re.escape(name)}\b", text, re.I):
        return True
    hits = len(re.findall(rf"\b{re.escape(name)}\b", text, re.I))
    # article_noun ("The TaskComment…") — accept non-deny compounds
    if source == "article_noun" and hits >= 1:
        return True
    if source == "comma_list" and hits >= 1:
        return True
    # bare Capitalized — need repetition (status adjectives often appear once/twice)
    if source == "capitalized_noun" and hits >= 3:
        return True
    if hits >= 4:
        return True
    return False


def _try_add_header_noun(
    name: str,
    text: str,
    life_by_entity: dict[str, list[str]],
    seen: set[str],
    nouns: list[DomainNoun],
) -> None:
    if " " in name or name.lower() in _NOUN_DENY or len(name) < 3 or name in seen:
        return
    spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", name)
    if not _grounded_in_brief(name, text) and not any(
        _grounded_in_brief(tok, text) for tok in spaced.split()
    ):
        return
    seen.add(name)
    nouns.append(
        DomainNoun(
            name=name,
            status="grounded",
            evidence="entity section header in founder brief",
            lifecycle_hint=life_by_entity.get(name, []),
            owner_field_hint=_owner_for_noun(name, text),
        )
    )


def _try_add_discovered_noun(
    raw: dict[str, Any],
    text: str,
    life_by_entity: dict[str, list[str]],
    headers: set[str],
    seen: set[str],
    nouns: list[DomainNoun],
    rejected: list[str],
) -> None:
    name = str(raw.get("name") or "").strip()
    if not name or name in seen:
        return
    source = str(raw.get("source") or "")
    if raw.get("type") == "user_role":
        return
    if name.lower() in _NOUN_DENY or len(name) < 4:
        rejected.append(name)
        return
    if not _grounded_in_brief(name, text):
        rejected.append(name)
        return
    if not _strong_noun_signal(name, source, text, header_names=headers):
        rejected.append(name)
        return
    seen.add(name)
    nouns.append(
        DomainNoun(
            name=name,
            status="grounded",
            evidence=f"appears in founder brief (source={source or '?'})",
            lifecycle_hint=life_by_entity.get(name, []),
            owner_field_hint=_owner_for_noun(name, text),
        )
    )


def _extract_nouns(
    entities_raw: dict[str, Any],
    text: str,
    life_by_entity: dict[str, list[str]],
) -> tuple[list[DomainNoun], list[str]]:
    rejected: list[str] = []
    nouns: list[DomainNoun] = []
    seen: set[str] = set()
    headers = _header_entities(text)
    for h in sorted(headers):
        _try_add_header_noun(h, text, life_by_entity, seen, nouns)
    for e in entities_raw.get("entities", []):
        if isinstance(e, dict):
            _try_add_discovered_noun(e, text, life_by_entity, headers, seen, nouns, rejected)
    return nouns, rejected


def _build_personas_desks_spine(
    text: str,
    personas_raw: dict[str, Any],
    nouns: list[DomainNoun],
) -> tuple[list[DomainPersona], list[DomainDesk], list[DemoSpineRow]]:
    personas: list[DomainPersona] = []
    desks: list[DomainDesk] = []
    spine: list[DemoSpineRow] = []
    seen: set[str] = set()
    default_owner = next((n.owner_field_hint for n in nouns if n.owner_field_hint), None)

    def add(label: str, *, job: str = "", evidence: str = "") -> None:
        if not label or not _grounded_in_brief(label, text):
            return
        pid = _stable_for(label)
        if pid in seen:
            return
        seen.add(pid)
        desk = _desk_name(pid)
        personas.append(
            DomainPersona(
                id_hint=pid,
                label=label,
                job=job,
                desk=desk,
                stable_id_candidate=pid,
                status="grounded",
                evidence=evidence or "named in founder brief",
            )
        )
        desks.append(
            DomainDesk(
                persona=pid,
                name=desk,
                purpose=f"Job desk for {label}",
                owner_field_hint=default_owner,
                status="hypothesis",
            )
        )
        if nouns:
            spine.append(
                DemoSpineRow(
                    persona=pid,
                    story=f"{label} has seeded {nouns[0].name} rows for their desk",
                    min_rows=1,
                    entity_hint=nouns[0].name,
                )
            )

    for label in _ROLE_RE.findall(text):
        add(label, evidence="role word in founder brief")
    for p in personas_raw.get("personas", []):
        if not isinstance(p, dict):
            continue
        label = str(p.get("name") or "").strip()
        if label:
            add(label, job=str(p.get("description") or ""), evidence="extract_personas + brief")
    return personas, desks, spine


def _collect_questions(
    text: str,
    questions_raw: dict[str, Any],
    personas: list[DomainPersona],
    nouns: list[DomainNoun],
    desks: list[DomainDesk],
) -> list[OpenQuestion]:
    open_qs: list[OpenQuestion] = []
    for i, q in enumerate(questions_raw.get("questions", [])[:6]):
        text_q = (
            str(q.get("question") or q.get("text") or "").strip()
            if isinstance(q, dict)
            else str(q).strip()
        )
        if not text_q:
            continue
        if _NOISE_Q_RE.search(text_q) and not _NOISE_BRIEF_RE.search(text):
            continue
        open_qs.append(OpenQuestion(id=f"q{i + 1}", text=text_q, blocks_promote=False))

    if not personas:
        open_qs.insert(
            0,
            OpenQuestion(
                id="q_personas",
                text="Who are the job personas (roles with desks)?",
                blocks_promote=True,
            ),
        )
    if not nouns:
        open_qs.insert(
            0,
            OpenQuestion(
                id="q_nouns",
                text="What are the core domain nouns named in the brief?",
                blocks_promote=True,
            ),
        )
    if personas and not any(d.owner_field_hint for d in desks):
        open_qs.append(
            OpenQuestion(
                id="q_owner",
                text="Which field binds each desk to current_user?",
                blocks_promote=True,
            )
        )
    return open_qs


def _title_and_summary(text: str, title: str | None) -> tuple[str, str]:
    title_val = title
    if not title_val:
        m = re.search(r"^#\s+(.+)$", text, re.M)
        title_val = m.group(1).strip() if m else text.splitlines()[0][:80]
    parts: list[str] = []
    for line in text.splitlines():
        p = line.strip()
        if not p or p.startswith("#") or p.startswith("|") or set(p) <= set("-:| "):
            continue
        parts.append(p)
        if sum(len(x) for x in parts) > 280:
            break
    return title_val or "Untitled domain", " ".join(parts)[:400]


def extract_from_text(
    founder_text: str,
    *,
    source_path: str | None = None,
    title: str | None = None,
) -> AgentDomain:
    """Build AgentDomain from founder prose (grounded nouns only)."""
    text = founder_text.strip()
    if not text:
        return AgentDomain(title=title or "", summary="")

    entities_raw, personas_raw, lifecycles_raw, questions_raw = _run_offline_analyses(text)
    life = _life_by_entity(lifecycles_raw)
    nouns, rejected = _extract_nouns(entities_raw, text, life)
    personas, desks, spine = _build_personas_desks_spine(text, personas_raw, nouns)
    open_qs = _collect_questions(text, questions_raw, personas, nouns, desks)
    title_val, summary = _title_and_summary(text, title)

    return AgentDomain(
        title=title_val,
        summary=summary,
        source_path=source_path,
        source_sha256=_sha256(text),
        personas=personas,
        nouns=nouns,
        desks=desks,
        demo_spine=spine,
        open_questions=open_qs,
        rejected_chrome=sorted(set(rejected)),
        research_notes=[
            "Prefer knowledge concepts before inventing structure.",
            "Do not promote ungrounded nouns.",
            "Counter-prior bootstrap_pollution: this document is cognition draft, not DSL.",
        ],
    )


def extract_from_path(path: Path) -> AgentDomain:
    return extract_from_text(path.read_text(encoding="utf-8"), source_path=str(path))


def find_founder_brief(project_root: Path) -> Path | None:
    for name in ("SPEC.md", "spec.md", "idea.md", "requirements.md", "README.md"):
        p = project_root / name
        if p.is_file() and len(p.read_text(encoding="utf-8").strip()) > 40:
            return p
    return None
