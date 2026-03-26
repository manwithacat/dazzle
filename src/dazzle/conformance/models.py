"""Data models for conformance testing."""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid5

CONFORMANCE_NS = UUID("d4221300-0f07-4a0c-b3e5-000000000000")


class ScopeOutcome(StrEnum):
    ALL = "all"
    FILTERED = "filtered"
    SCOPE_EXCLUDED = "scope_excluded"
    ACCESS_DENIED = "access_denied"
    FORBIDDEN = "forbidden"
    UNAUTHENTICATED = "unauthenticated"
    UNPROTECTED = "unprotected"


@dataclass
class ConformanceCase:
    entity: str
    persona: str
    operation: str
    expected_status: int
    expected_rows: int | None = None
    row_target: str | None = None
    description: str = ""
    scope_type: ScopeOutcome = ScopeOutcome.UNPROTECTED

    @property
    def test_id(self) -> str:
        parts = [self.persona, self.operation, self.entity, self.scope_type.value]
        if self.row_target:
            parts.append(self.row_target)
        return "-".join(parts)


@dataclass
class ConformanceFixtures:
    users: dict[str, dict[str, Any]] = field(default_factory=dict)
    entity_rows: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    junction_rows: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    expected_counts: dict[tuple[str, str], int] = field(default_factory=dict)


def conformance_uuid(entity: str, purpose: str) -> str:
    return str(uuid5(CONFORMANCE_NS, f"{entity}.{purpose}"))
