"""Typed per-tenant auth settings (verified-domain join, #1424).

Stored as the ``organizations.settings`` JSON blob; this is the typed view.
Unknown / malformed values coerce to the safe default (fail-closed posture).
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

JoinPolicy = Literal["off", "auto_join", "admin_approval"]
_POLICIES: frozenset[str] = frozenset({"off", "auto_join", "admin_approval"})


class OrgSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    domain_join_policy: JoinPolicy = "admin_approval"
    restrict_membership_to_verified_domains: bool = False

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "OrgSettings":
        raw = d.get("domain_join_policy")
        policy: JoinPolicy = raw if raw in _POLICIES else "admin_approval"
        return cls(
            domain_join_policy=policy,
            restrict_membership_to_verified_domains=bool(
                d.get("restrict_membership_to_verified_domains", False)
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain_join_policy": self.domain_join_policy,
            "restrict_membership_to_verified_domains": self.restrict_membership_to_verified_domains,
        }
