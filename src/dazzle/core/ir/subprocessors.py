"""Subprocessor declarations for GDPR / SOC 2 / ISO 27001 (v0.61.0).

A subprocessor is any third-party that handles personal data on the app's
behalf — analytics providers, payment processors, email/SMS gateways, file
storage, etc. Each declared subprocessor feeds four compile-time outputs:

1. Privacy-page subprocessor table (GDPR Art. 13/14 transparency).
2. ROPA document row (GDPR Art. 30 Record of Processing Activities).
3. Cookie-policy entries (per-provider cookie enumeration).
4. DPA-hub page (SOC 2 CC6.6 evidence — signed DPAs with subprocessors).

Framework-provided subprocessors (GA4, GTM, Stripe, Twilio, SendGrid, AWS
SES, Firebase) ship in a default registry. App-level declarations override
or extend it.

See docs/superpowers/specs/2026-04-24-analytics-privacy-design.md §2.3.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LegalBasis(StrEnum):
    """GDPR Article 6 lawful basis for processing."""

    CONSENT = "consent"
    CONTRACT = "contract"
    LEGAL_OBLIGATION = "legal_obligation"
    VITAL_INTERESTS = "vital_interests"
    PUBLIC_TASK = "public_task"
    LEGITIMATE_INTEREST = "legitimate_interest"


class ConsentCategory(StrEnum):
    """Dazzle-native consent categories (v0.61.0).

    Each subprocessor must bind to exactly one consent category so the
    consent banner can gate its cookies and script loads.

    Mapping to Consent Mode v2 signals (documented in the spec):
        analytics       → analytics_storage
        advertising     → ad_storage + ad_user_data + ad_personalization
        personalization → ad_personalization / functionality_storage
        functional      → functionality_storage + security_storage
    """

    ANALYTICS = "analytics"
    ADVERTISING = "advertising"
    PERSONALIZATION = "personalization"
    FUNCTIONAL = "functional"


class DataCategory(StrEnum):
    """Closed vocabulary describing categories of data a subprocessor handles.

    Distinct from the PII `category` vocabulary — a subprocessor may receive
    pseudonymous IDs, device fingerprints, or aggregate usage data that is
    not itself an entity field. Overlap is intentional where categories
    match.
    """

    CONTACT = "contact"
    IDENTITY = "identity"
    LOCATION = "location"
    BEHAVIORAL = "behavioral"
    FINANCIAL = "financial"
    HEALTH = "health"
    DEVICE_FINGERPRINT = "device_fingerprint"
    PSEUDONYMOUS_ID = "pseudonymous_id"
    PAGE_URL = "page_url"
    SESSION_DATA = "session_data"
    CONTENT = "content"


class SubprocessorSpec(BaseModel):
    """Declaration of a third-party data processor.

    Attributes:
        name: DSL identifier (e.g. `google_analytics`, `stripe`). Must match
            `[a-z][a-z0-9_]*`.
        label: Human-readable name (e.g. "Google Analytics 4").
        handler: Legal entity processing the data (e.g. "Google LLC").
        handler_address: Optional postal address for the handler entity.
        jurisdiction: ISO 3166-1 alpha-2 country code or multi-region code
            (EU, EEA, UK, US, APAC). Free-form string; validator ensures
            uppercase.
        data_categories: What kinds of data flow to this subprocessor.
        retention: Retention period as a free-form string (e.g. "14 months",
            "7 years", "session only"). Parsed by downstream generators.
        legal_basis: GDPR Art. 6 basis.
        consent_category: Which consent category gates this subprocessor.
        dpa_url: URL to the signed Data Processing Agreement.
        scc_url: Optional URL to Standard Contractual Clauses (EU→non-EU
            transfers). Required when jurisdiction is outside EEA and data
            flows from EU subjects.
        cookies: Cookie names (or glob patterns like `_ga_*`) set by this
            subprocessor. Feeds the cookie policy.
        purpose: Short human description of why this subprocessor is used.
        is_framework_default: True for registry-shipped subprocessors; False
            for app-level declarations. Distinguishes audit output.
    """

    name: str
    label: str
    handler: str
    handler_address: str | None = None
    jurisdiction: str
    data_categories: list[DataCategory] = Field(default_factory=list)
    retention: str
    legal_basis: LegalBasis
    consent_category: ConsentCategory
    dpa_url: str | None = None
    scc_url: str | None = None
    cookies: list[str] = Field(default_factory=list)
    purpose: str = ""
    is_framework_default: bool = False

    model_config = ConfigDict(frozen=True)

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        if not v or not v[0].isalpha() or not all(c.isalnum() or c == "_" for c in v):
            raise ValueError(
                f"Subprocessor name must start with a letter and contain only "
                f"alphanumeric characters or underscore, got {v!r}"
            )
        return v

    @field_validator("jurisdiction")
    @classmethod
    def _normalise_jurisdiction(cls, v: str) -> str:
        return v.strip().upper()

    @property
    def needs_sccs(self) -> bool:
        """True when data transfers cross the EEA and SCC link is therefore required."""
        non_eea = {"US", "APAC", "CN", "IN", "JP", "SG", "AU", "BR", "CA", "RU"}
        return self.jurisdiction in non_eea
