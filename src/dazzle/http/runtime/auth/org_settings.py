"""Typed per-tenant auth settings (verified-domain join, #1424).

Stored as the ``organizations.settings`` JSON blob; this is the typed view.
Unknown / malformed **stored** values coerce to the safe default
(fail-closed **read** posture). Write paths must not invent a policy
from leftover form tokens — use :func:`leftover_honest_join_policy`.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from dazzle.render.fragment.renderer._render_interactive import (
    leftover_honest_catalog_id,
    leftover_honest_catalog_option_values,
)

JoinPolicy = Literal["off", "auto_join", "admin_approval"]
_POLICIES: frozenset[str] = frozenset({"off", "auto_join", "admin_approval"})


def leftover_honest_join_policy(raw: Any) -> JoinPolicy | None:
    """Valid declared join-policy tokens ride. Leftover junk restores None.

    Leftover ``domain_join_policy=zzz`` used to invent ``admin_approval``
    via :meth:`OrgSettings.from_dict` and persist it. Valid tokens
    (``off`` / ``auto_join`` / ``admin_approval``) ride. Rest is
    stay-put (None). Distinct from leftover persona roles (oral #89)
    and leftover catalog picker (oral #69). Live domain_join_co
    join-policy form. Cycle 2212.
    """
    honest = leftover_honest_catalog_id(
        str(raw if raw is not None else ""),
        leftover_honest_catalog_option_values(_POLICIES),
        "",
        allow_empty_rest=True,
    )
    if honest in _POLICIES:
        return honest  # type: ignore[return-value]
    return None


class OrgSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    domain_join_policy: JoinPolicy = "admin_approval"
    restrict_membership_to_verified_domains: bool = False

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "OrgSettings":
        # Fail-closed **read** of stored JSON. Write paths stay put
        # via leftover_honest_join_policy — do not coerce leftover
        # form tokens into admin_approval.
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
