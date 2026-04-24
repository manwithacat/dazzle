"""PII annotation IR types (v0.61.0).

Fields carry an optional `PIIAnnotation` that declares data-protection
category and sensitivity. Annotations feed three pipelines:

1. Compile-time — privacy page, ROPA, cookie policy generators.
2. Runtime — PII stripping before analytics events leave the framework.
3. Audit — special-category fields receive mandatory audit-on-read.

The annotation is orthogonal to RBAC (`permit:` / `scope:` unchanged).
The existing `sensitive` modifier remains as a coarser boolean flag;
`pii()` supersedes it with category + sensitivity detail.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class PIICategory(StrEnum):
    """Closed-vocabulary categories for personal data classification.

    Parser rejects any value outside this enum.
    """

    CONTACT = "contact"  # email, phone, address
    IDENTITY = "identity"  # name, DOB, government IDs, tax numbers
    LOCATION = "location"  # precise geolocation, IP address
    BIOMETRIC = "biometric"  # fingerprints, face templates
    FINANCIAL = "financial"  # bank account, card number, income
    HEALTH = "health"  # medical conditions, prescriptions (GDPR Art. 9)
    FREEFORM = "freeform"  # unstructured text that may contain PII
    BEHAVIORAL = "behavioral"  # browsing history, preferences


class PIISensitivity(StrEnum):
    """Sensitivity tier driving handling defaults.

    - STANDARD: ordinary personal data.
    - HIGH: higher-risk (DOB, full name, geolocation).
    - SPECIAL_CATEGORY: GDPR Article 9 / 10 (health, biometric, criminal,
      political, religious). Triggers mandatory audit-on-read, restricted
      export, and explicit-consent gating in Phase 2+.
    """

    STANDARD = "standard"
    HIGH = "high"
    SPECIAL_CATEGORY = "special_category"


class PIIAnnotation(BaseModel):
    """Structured PII classification for a single field.

    Examples:
        email: str pii                                 → category=None, sensitivity=STANDARD
        email: str pii(category=contact)               → category=CONTACT, sensitivity=STANDARD
        dob: date pii(category=identity, sensitivity=high)
        ssn: str pii(category=identity, sensitivity=special_category)
    """

    category: PIICategory | None = None
    sensitivity: PIISensitivity = PIISensitivity.STANDARD

    model_config = ConfigDict(frozen=True)

    @property
    def is_special_category(self) -> bool:
        """True for GDPR Art. 9/10 data requiring extra protection."""
        return self.sensitivity is PIISensitivity.SPECIAL_CATEGORY
