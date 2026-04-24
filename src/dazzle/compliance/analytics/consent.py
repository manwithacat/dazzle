"""Consent state model and cookie handling (v0.61.0 Phase 2).

Four Dazzle-native consent categories that map to Consent Mode v2 signals:

    analytics       → analytics_storage
    advertising     → ad_storage + ad_user_data + ad_personalization
    personalization → ad_personalization / functionality_storage (context-dependent)
    functional      → functionality_storage + security_storage

The consent cookie (`dz_consent_v2`) stores a user's choices as a URL-encoded
JSON object. The version suffix lets us force re-consent if the policy
materially changes — bump to `_v3` and the old cookie is ignored.

Default state is residency-driven:

    EU / UK / EEA tenants → all categories denied (opt-in required)
    Other tenants         → all categories granted (opt-out available)

This module is pure data / serialisation — no FastAPI or HTTP dependencies.
The middleware layer (consent_middleware.py) handles request/response binding.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Literal

from dazzle.core.ir import ConsentCategory

# Current cookie version. Bump when the policy / category vocabulary
# materially changes; the old cookie will be treated as missing.
CONSENT_COOKIE_NAME = "dz_consent_v2"
CONSENT_COOKIE_VERSION = 2

# 13 months — GDPR guidance for maximum analytics-cookie lifetime.
CONSENT_COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24 * 400

ConsentChoice = Literal["granted", "denied"]

# Jurisdictions that default-deny consent. Covers EEA member states + UK.
# Other jurisdictions default-grant. Tenant-level override always wins.
_DEFAULT_DENY_JURISDICTIONS: frozenset[str] = frozenset(
    {
        "EU",
        "EEA",
        "UK",
        "GB",
        # Individual EEA members (in case tenants config at country level)
        "AT",
        "BE",
        "BG",
        "HR",
        "CY",
        "CZ",
        "DK",
        "EE",
        "FI",
        "FR",
        "DE",
        "GR",
        "HU",
        "IS",
        "IE",
        "IT",
        "LV",
        "LI",
        "LT",
        "LU",
        "MT",
        "NL",
        "NO",
        "PL",
        "PT",
        "RO",
        "SK",
        "SI",
        "ES",
        "SE",
    }
)


@dataclass(frozen=True)
class ConsentState:
    """A user's consent choices across the four Dazzle-native categories.

    `undecided` means the user hasn't interacted with the banner yet — the
    caller should render the banner. If True, all category fields reflect
    the residency-driven defaults, not the user's choices.
    """

    analytics: ConsentChoice
    advertising: ConsentChoice
    personalization: ConsentChoice
    functional: ConsentChoice
    undecided: bool = True
    decided_at: int | None = None  # unix seconds; None when undecided

    def is_granted(self, category: ConsentCategory | str) -> bool:
        """Return True if the given category is currently granted."""
        key = category.value if isinstance(category, ConsentCategory) else category
        if key == "analytics":
            return self.analytics == "granted"
        if key == "advertising":
            return self.advertising == "granted"
        if key == "personalization":
            return self.personalization == "granted"
        if key == "functional":
            return self.functional == "granted"
        raise ValueError(f"Unknown consent category: {key}")

    def to_consent_mode_v2(self) -> dict[str, ConsentChoice]:
        """Map Dazzle categories to Consent Mode v2 signal dict.

        Used when emitting `gtag('consent','default',{...})` or
        `gtag('consent','update',{...})`. Follows Google's published
        category-to-signal mapping.
        """
        ad_linked = "granted" if self.advertising == "granted" else "denied"
        ad_pers = (
            "granted"
            if self.advertising == "granted" and self.personalization == "granted"
            else "denied"
        )
        return {
            "analytics_storage": self.analytics,
            "ad_storage": ad_linked,
            "ad_user_data": ad_linked,
            "ad_personalization": ad_pers,
            "functionality_storage": self.functional,
            "personalization_storage": self.personalization,
            # Security storage is always granted — essential for the service.
            "security_storage": "granted",
        }

    def serialize(self) -> str:
        """Return the cookie value string (JSON; caller URL-encodes for transport)."""
        return json.dumps(
            {
                "v": CONSENT_COOKIE_VERSION,
                "a": self.analytics,
                "d": self.advertising,
                "p": self.personalization,
                "f": self.functional,
                "u": self.undecided,
                "t": self.decided_at,
            },
            separators=(",", ":"),
        )


@dataclass(frozen=True)
class ConsentDefaults:
    """Pre-choice default consent state for a tenant.

    Determined by the tenant's declared data residency: EU/UK → all denied,
    elsewhere → all granted. Tenant-level `consent_default` override applies
    before residency lookup.
    """

    analytics: ConsentChoice
    advertising: ConsentChoice
    personalization: ConsentChoice
    functional: ConsentChoice

    @classmethod
    def for_jurisdiction(
        cls,
        jurisdiction: str | None,
        override: Literal["granted", "denied"] | None = None,
    ) -> ConsentDefaults:
        """Resolve defaults for a tenant's jurisdiction.

        Args:
            jurisdiction: Tenant data residency (EU/UK/US/etc.). None defaults
                to strict (all denied) to bias toward compliance.
            override: Optional tenant-level override that wins over residency.
        """
        if override is not None:
            return cls(
                analytics=override,
                advertising=override,
                personalization=override,
                functional=override,
            )
        juris_upper = (jurisdiction or "EU").upper()
        deny = juris_upper in _DEFAULT_DENY_JURISDICTIONS
        default: ConsentChoice = "denied" if deny else "granted"
        return cls(
            analytics=default,
            advertising=default,
            personalization=default,
            # Functional storage is always granted — essential for the service
            # to work (session cookies, CSRF tokens, auth). Consent Mode v2 also
            # treats functionality_storage as always-on.
            functional="granted",
        )

    def to_undecided_state(self) -> ConsentState:
        """Build a ConsentState representing the default (banner-not-yet-interacted)."""
        return ConsentState(
            analytics=self.analytics,
            advertising=self.advertising,
            personalization=self.personalization,
            functional=self.functional,
            undecided=True,
            decided_at=None,
        )


def parse_consent_cookie(
    raw: str | None,
    defaults: ConsentDefaults,
) -> ConsentState:
    """Parse a cookie value; fall back to `defaults` on missing/malformed.

    A missing, empty, malformed, or wrong-version cookie yields the
    `undecided` default state (banner should render). Partial records are
    treated as malformed — all-or-nothing — so we never half-apply choices.
    """
    if not raw:
        return defaults.to_undecided_state()

    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return defaults.to_undecided_state()

    if not isinstance(data, dict):
        return defaults.to_undecided_state()
    if data.get("v") != CONSENT_COOKIE_VERSION:
        return defaults.to_undecided_state()

    valid_choices: set[str] = {"granted", "denied"}
    for field_key in ("a", "d", "p", "f"):
        if data.get(field_key) not in valid_choices:
            return defaults.to_undecided_state()

    undecided = bool(data.get("u", False))
    ts_raw = data.get("t")
    decided_at = int(ts_raw) if isinstance(ts_raw, int | float) else None

    return ConsentState(
        analytics=data["a"],
        advertising=data["d"],
        personalization=data["p"],
        functional=data["f"],
        undecided=undecided,
        decided_at=decided_at,
    )


def build_decided_state(
    *,
    analytics: bool,
    advertising: bool,
    personalization: bool,
    functional: bool,
    now: int | None = None,
) -> ConsentState:
    """Construct a decided ConsentState from four bool choices."""

    def _choice(flag: bool) -> ConsentChoice:
        return "granted" if flag else "denied"

    return ConsentState(
        analytics=_choice(analytics),
        advertising=_choice(advertising),
        personalization=_choice(personalization),
        # Functional is always granted when the user has made a choice
        # — the alternative would break session/auth/CSRF mechanics.
        functional="granted" if functional else "granted",
        undecided=False,
        decided_at=now if now is not None else int(time.time()),
    )
