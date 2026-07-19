"""Agent-audience domain brief — cognition SSOT before DSL (#agent-domain).

Not runtime. Not investor prose. Agents may research *into* this document;
only grounded claims and explicit hypotheses belong here. DSL remains the
validate/serve SSOT.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

ClaimStatus = Literal["grounded", "hypothesis"]


@dataclass
class DomainNoun:
    name: str
    status: ClaimStatus = "grounded"
    evidence: str = ""
    lifecycle_hint: list[str] = field(default_factory=list)
    owner_field_hint: str | None = None


@dataclass
class DomainPersona:
    id_hint: str
    label: str
    job: str = ""
    desk: str | None = None
    stable_id_candidate: str | None = None
    status: ClaimStatus = "grounded"
    evidence: str = ""


@dataclass
class DomainDesk:
    persona: str
    name: str
    purpose: str = ""
    owner_field_hint: str | None = None
    status: ClaimStatus = "hypothesis"


@dataclass
class DemoSpineRow:
    persona: str
    story: str
    min_rows: int = 1
    entity_hint: str | None = None


@dataclass
class OpenQuestion:
    id: str
    text: str
    blocks_promote: bool = True


@dataclass
class AgentDomain:
    """Mutable agent-facing domain document (not DSL)."""

    version: int = 1
    title: str = ""
    summary: str = ""
    source_path: str | None = None
    source_sha256: str | None = None
    personas: list[DomainPersona] = field(default_factory=list)
    nouns: list[DomainNoun] = field(default_factory=list)
    desks: list[DomainDesk] = field(default_factory=list)
    demo_spine: list[DemoSpineRow] = field(default_factory=list)
    open_questions: list[OpenQuestion] = field(default_factory=list)
    research_notes: list[str] = field(default_factory=list)
    rejected_chrome: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentDomain:
        def _list(key: str, typ: type) -> list[Any]:
            out: list[Any] = []
            for row in data.get(key) or []:
                if not isinstance(row, dict):
                    continue
                # filter unknown keys
                fields = {f.name for f in typ.__dataclass_fields__.values()}  # type: ignore[attr-defined]
                out.append(typ(**{k: v for k, v in row.items() if k in fields}))
            return out

        return cls(
            version=int(data.get("version") or 1),
            title=str(data.get("title") or ""),
            summary=str(data.get("summary") or ""),
            source_path=data.get("source_path"),
            source_sha256=data.get("source_sha256"),
            personas=_list("personas", DomainPersona),
            nouns=_list("nouns", DomainNoun),
            desks=_list("desks", DomainDesk),
            demo_spine=_list("demo_spine", DemoSpineRow),
            open_questions=_list("open_questions", OpenQuestion),
            research_notes=list(data.get("research_notes") or []),
            rejected_chrome=list(data.get("rejected_chrome") or []),
        )
