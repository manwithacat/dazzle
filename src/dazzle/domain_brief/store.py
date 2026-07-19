"""Load/save AGENT_DOMAIN.md + agent_domain.json twins."""

from __future__ import annotations

import json
import re
from pathlib import Path

from dazzle.domain_brief.models import AgentDomain

JSON_NAME = "agent_domain.json"
MD_NAME = "AGENT_DOMAIN.md"
_FENCE_RE = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)


def default_paths(project_root: Path) -> tuple[Path, Path]:
    root = project_root.resolve()
    return root / MD_NAME, root / JSON_NAME


def save_domain(project_root: Path, domain: AgentDomain) -> dict[str, str]:
    md_path, json_path = default_paths(project_root)
    json_path.write_text(json.dumps(domain.to_dict(), indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(domain), encoding="utf-8")
    return {"markdown": str(md_path), "json": str(json_path)}


def load_domain(project_root: Path) -> AgentDomain | None:
    md_path, json_path = default_paths(project_root)
    if json_path.is_file():
        return AgentDomain.from_dict(json.loads(json_path.read_text(encoding="utf-8")))
    if md_path.is_file():
        m = _FENCE_RE.search(md_path.read_text(encoding="utf-8"))
        if m:
            return AgentDomain.from_dict(json.loads(m.group(1)))
    return None


def _section_personas(domain: AgentDomain) -> list[str]:
    if not domain.personas:
        return ["_None yet._"]
    return [
        f"- **{p.label}** (`{p.id_hint}`, stable≈`{p.stable_id_candidate or p.id_hint}`, "
        f"{p.status}) — desk `{p.desk or '—'}` — {p.job or p.evidence or '—'}"
        for p in domain.personas
    ]


def _section_nouns(domain: AgentDomain) -> list[str]:
    if not domain.nouns:
        return ["_None grounded yet._"]
    lines = []
    for n in domain.nouns:
        life = " → ".join(n.lifecycle_hint) if n.lifecycle_hint else "—"
        lines.append(
            f"- **{n.name}** ({n.status}) owner≈`{n.owner_field_hint or '—'}` "
            f"lifecycle: {life} — {n.evidence or ''}"
        )
    return lines


def _section_desks(domain: AgentDomain) -> list[str]:
    if not domain.desks:
        return ["_Infer from personas or author explicitly._"]
    return [
        f"- **{d.name}** for `{d.persona}` ({d.status}) "
        f"owner≈`{d.owner_field_hint or '—'}` — {d.purpose}"
        for d in domain.desks
    ]


def _section_spine(domain: AgentDomain) -> list[str]:
    if not domain.demo_spine:
        return ["_Who owns which rows for each persona desk?_"]
    return [
        f"- `{s.persona}`: {s.story} (min_rows={s.min_rows}, entity≈{s.entity_hint or '—'})"
        for s in domain.demo_spine
    ]


def _section_questions(domain: AgentDomain) -> list[str]:
    if not domain.open_questions:
        return ["_None blocking._"]
    return [
        f"- `{q.id}`{' **blocks promote**' if q.blocks_promote else ''}: {q.text}"
        for q in domain.open_questions
    ]


def render_markdown(domain: AgentDomain) -> str:
    """Human + agent readable domain brief with embedded JSON twin."""
    chunks: list[str] = [
        f"# Agent domain: {domain.title or '(untitled)'}",
        "",
        "> **Audience: AI agents.** Not runtime SSOT (DSL). Not investor prose.",
        "> Promote only when `dazzle domain promote` is green. No chrome entities.",
        "",
        "## Summary",
        "",
        domain.summary or "_(empty)_",
        "",
        f"**Source:** `{domain.source_path or 'inline'}`  ",
        f"**Fingerprint:** `{domain.source_sha256 or '—'}`",
        "",
        "## Personas (jobs)",
        "",
        *_section_personas(domain),
        "",
        "## Nouns (domain types)",
        "",
        *_section_nouns(domain),
    ]
    if domain.rejected_chrome:
        chunks.extend(
            [
                "",
                "## Rejected chrome (not domain)",
                "",
                ", ".join(f"`{c}`" for c in domain.rejected_chrome),
            ]
        )
    chunks.extend(
        [
            "",
            "## Desks",
            "",
            *_section_desks(domain),
            "",
            "## Demo spine (seed stories)",
            "",
            *_section_spine(domain),
            "",
            "## Open questions",
            "",
            *_section_questions(domain),
        ]
    )
    if domain.research_notes:
        chunks.extend(["", "## Research notes", ""])
        chunks.extend(f"- {n}" for n in domain.research_notes)
    chunks.extend(
        [
            "",
            "## Machine twin",
            "",
            "```json",
            json.dumps(domain.to_dict(), indent=2),
            "```",
            "",
            "<!-- dazzle-agent-domain: v1 -->",
            "",
        ]
    )
    return "\n".join(chunks)
