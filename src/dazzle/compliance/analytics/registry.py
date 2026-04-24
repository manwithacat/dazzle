"""Framework subprocessor registry (v0.61.0).

Ships a default set of subprocessor declarations for the common third-party
services Dazzle users integrate. App-level `subprocessor` DSL declarations
override registry entries by matching `name`; otherwise the registry provides
the metadata consumed by the privacy-page, ROPA, and cookie-policy generators.

Each entry has `is_framework_default=True` so the audit command can tell
registry-provided defaults from app-declared overrides.

To keep this list honest: URLs and addresses are the publicly-documented
values at the time of writing (2026-04-24). The DPA URL is the authoritative
source — if a generated privacy page links to an out-of-date URL, regenerate
after updating the registry rather than editing the generated document.
"""

from __future__ import annotations

from dazzle.core.ir import (
    ConsentCategory,
    DataCategory,
    LegalBasis,
    SubprocessorSpec,
)

FRAMEWORK_SUBPROCESSORS: list[SubprocessorSpec] = [
    SubprocessorSpec(
        name="google_analytics",
        label="Google Analytics 4",
        handler="Google LLC",
        handler_address="1600 Amphitheatre Parkway, Mountain View, CA 94043, USA",
        jurisdiction="US",
        data_categories=[
            DataCategory.PSEUDONYMOUS_ID,
            DataCategory.DEVICE_FINGERPRINT,
            DataCategory.PAGE_URL,
            DataCategory.SESSION_DATA,
            DataCategory.BEHAVIORAL,
        ],
        retention="14 months",
        legal_basis=LegalBasis.LEGITIMATE_INTEREST,
        consent_category=ConsentCategory.ANALYTICS,
        dpa_url="https://business.safety.google/adsprocessorterms/",
        scc_url="https://business.safety.google/sccs/",
        cookies=["_ga", "_ga_*", "_gid", "_gat"],
        purpose="Product and web usage analytics.",
        is_framework_default=True,
    ),
    SubprocessorSpec(
        name="google_tag_manager",
        label="Google Tag Manager",
        handler="Google LLC",
        handler_address="1600 Amphitheatre Parkway, Mountain View, CA 94043, USA",
        jurisdiction="US",
        data_categories=[DataCategory.PSEUDONYMOUS_ID, DataCategory.PAGE_URL],
        retention="session only",
        legal_basis=LegalBasis.LEGITIMATE_INTEREST,
        consent_category=ConsentCategory.ANALYTICS,
        dpa_url="https://business.safety.google/adsprocessorterms/",
        scc_url="https://business.safety.google/sccs/",
        cookies=[],
        purpose="Tag / script orchestration layer that loads analytics and marketing tags.",
        is_framework_default=True,
    ),
    SubprocessorSpec(
        name="plausible",
        label="Plausible Analytics",
        handler="Plausible Insights OÜ",
        handler_address="Västriku tn 2, 50403 Tartu, Estonia",
        jurisdiction="EU",
        data_categories=[
            DataCategory.PAGE_URL,
            DataCategory.SESSION_DATA,
            DataCategory.BEHAVIORAL,
        ],
        retention="aggregated indefinitely; raw session data 24 hours",
        legal_basis=LegalBasis.LEGITIMATE_INTEREST,
        consent_category=ConsentCategory.ANALYTICS,
        dpa_url="https://plausible.io/dpa",
        scc_url=None,  # EU handler, SCCs not required for EU subjects
        cookies=[],  # Plausible is cookieless by design
        purpose="Privacy-friendly web analytics with no cookies and no cross-site tracking.",
        is_framework_default=True,
    ),
    SubprocessorSpec(
        name="stripe",
        label="Stripe Payments",
        handler="Stripe, Inc.",
        handler_address="510 Townsend Street, San Francisco, CA 94103, USA",
        jurisdiction="US",
        data_categories=[DataCategory.FINANCIAL, DataCategory.CONTACT, DataCategory.IDENTITY],
        retention="7 years (regulatory)",
        legal_basis=LegalBasis.CONTRACT,
        consent_category=ConsentCategory.FUNCTIONAL,
        dpa_url="https://stripe.com/legal/dpa",
        scc_url="https://stripe.com/legal/dpa/scc",
        cookies=["__stripe_mid", "__stripe_sid"],
        purpose="Payment processing, fraud prevention, and invoice management.",
        is_framework_default=True,
    ),
    SubprocessorSpec(
        name="twilio",
        label="Twilio",
        handler="Twilio Inc.",
        handler_address="101 Spear Street, 5th Floor, San Francisco, CA 94105, USA",
        jurisdiction="US",
        data_categories=[DataCategory.CONTACT, DataCategory.CONTENT],
        retention="30 days message content; 7 years metadata",
        legal_basis=LegalBasis.CONTRACT,
        consent_category=ConsentCategory.FUNCTIONAL,
        dpa_url="https://www.twilio.com/legal/data-protection-addendum",
        scc_url="https://www.twilio.com/legal/data-protection-addendum",
        cookies=[],
        purpose="Transactional SMS and voice messaging.",
        is_framework_default=True,
    ),
    SubprocessorSpec(
        name="sendgrid",
        label="SendGrid",
        handler="Twilio Inc. (SendGrid)",
        handler_address="1801 California Street, Suite 500, Denver, CO 80202, USA",
        jurisdiction="US",
        data_categories=[DataCategory.CONTACT, DataCategory.CONTENT, DataCategory.BEHAVIORAL],
        retention="30 days message content; 7 years metadata",
        legal_basis=LegalBasis.CONTRACT,
        consent_category=ConsentCategory.FUNCTIONAL,
        dpa_url="https://www.twilio.com/legal/data-protection-addendum",
        scc_url="https://www.twilio.com/legal/data-protection-addendum",
        cookies=[],
        purpose="Transactional and marketing email delivery.",
        is_framework_default=True,
    ),
    SubprocessorSpec(
        name="aws_ses",
        label="Amazon Simple Email Service",
        handler="Amazon Web Services, Inc.",
        handler_address="410 Terry Avenue North, Seattle, WA 98109, USA",
        jurisdiction="US",
        data_categories=[DataCategory.CONTACT, DataCategory.CONTENT],
        retention="minimal; transient message routing only",
        legal_basis=LegalBasis.CONTRACT,
        consent_category=ConsentCategory.FUNCTIONAL,
        dpa_url="https://d1.awsstatic.com/legal/aws-gdpr/AWS_GDPR_DPA.pdf",
        scc_url="https://aws.amazon.com/service-terms/",
        cookies=[],
        purpose="Transactional email delivery.",
        is_framework_default=True,
    ),
    SubprocessorSpec(
        name="firebase_cloud_messaging",
        label="Firebase Cloud Messaging",
        handler="Google LLC",
        handler_address="1600 Amphitheatre Parkway, Mountain View, CA 94043, USA",
        jurisdiction="US",
        data_categories=[DataCategory.PSEUDONYMOUS_ID, DataCategory.CONTENT],
        retention="transient; message stored only until device delivery",
        legal_basis=LegalBasis.CONSENT,
        consent_category=ConsentCategory.FUNCTIONAL,
        dpa_url="https://firebase.google.com/terms/data-processing-terms",
        scc_url="https://business.safety.google/sccs/",
        cookies=[],
        purpose="Push notification delivery to mobile and web clients.",
        is_framework_default=True,
    ),
]


_BY_NAME: dict[str, SubprocessorSpec] = {s.name: s for s in FRAMEWORK_SUBPROCESSORS}


def get_framework_subprocessor(name: str) -> SubprocessorSpec | None:
    """Return a framework-default subprocessor by name, or None if unknown."""
    return _BY_NAME.get(name)


def list_framework_subprocessors() -> list[SubprocessorSpec]:
    """Return a copy of the framework defaults list."""
    return list(FRAMEWORK_SUBPROCESSORS)


def merge_app_subprocessors(
    app_declared: list[SubprocessorSpec],
) -> list[SubprocessorSpec]:
    """Merge app-level declarations with framework defaults.

    App-level entries override framework entries of the same name. Other
    framework defaults are included unchanged. Order: app-declared first
    (declaration order), followed by any framework defaults not overridden.
    """
    app_names = {s.name for s in app_declared}
    merged = list(app_declared)
    for default in FRAMEWORK_SUBPROCESSORS:
        if default.name not in app_names:
            merged.append(default)
    return merged
