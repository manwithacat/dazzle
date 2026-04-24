"""Privacy page + cookie policy + ROPA generation (v0.61.0 Phase 2).

Auto-generates compliance artefacts from PII annotations and subprocessor
declarations in the AppSpec, plus framework-default subprocessors. Outputs
are markdown that can be rendered by Dazzle's existing markdown pipeline.

The generator uses ``<!-- DZ-AUTO:start name="..." -->`` / ``<!-- DZ-AUTO:end -->``
delimiters around auto-enumerated sections. When legal regenerates the
privacy page, only content inside auto blocks is overwritten; author-owned
content outside stays untouched.

Block names defined:

- ``pii_fields``        — tables of PII-annotated fields grouped by category
- ``subprocessors``     — subprocessor list with DPA / SCC links
- ``retention``         — data retention summary
- ``cookies``           — cookie policy table (feeds both privacy page and
                          standalone cookie policy)
- ``ropa``              — ROPA table (GDPR Article 30)
- ``rights``            — GDPR rights endpoints (framework-provided)

The rendered privacy page markdown is committed to source control (under
``docs/privacy/policy.md`` by convention). The running app serves it from
``/privacy`` via the existing SiteSpec legal.privacy mechanism.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from dazzle.compliance.analytics.registry import merge_app_subprocessors
from dazzle.core.ir import (
    AppSpec,
    FieldSpec,
    PIICategory,
    SubprocessorSpec,
)

AUTO_START = '<!-- DZ-AUTO:start name="{name}" -->'
AUTO_END = "<!-- DZ-AUTO:end -->"
_AUTO_BLOCK_RE = re.compile(
    r'<!-- DZ-AUTO:start name="(?P<name>[^"]+)" -->.*?<!-- DZ-AUTO:end -->',
    re.DOTALL,
)

# Category display order in the privacy-page tables.
_CATEGORY_ORDER: tuple[PIICategory, ...] = (
    PIICategory.CONTACT,
    PIICategory.IDENTITY,
    PIICategory.LOCATION,
    PIICategory.FINANCIAL,
    PIICategory.HEALTH,
    PIICategory.BIOMETRIC,
    PIICategory.BEHAVIORAL,
    PIICategory.FREEFORM,
)

_CATEGORY_LABELS: dict[PIICategory, str] = {
    PIICategory.CONTACT: "Contact information",
    PIICategory.IDENTITY: "Identity data",
    PIICategory.LOCATION: "Location data",
    PIICategory.FINANCIAL: "Financial information",
    PIICategory.HEALTH: "Health data (special category)",
    PIICategory.BIOMETRIC: "Biometric data (special category)",
    PIICategory.BEHAVIORAL: "Behavioural data",
    PIICategory.FREEFORM: "Free-form notes",
}


@dataclass(frozen=True)
class PrivacyPageArtefacts:
    """Output bundle produced by the generator.

    Each artefact is a complete markdown document. They share the same
    source of truth (AppSpec) but can be served independently.
    """

    privacy_policy: str
    cookie_policy: str
    ropa: str
    generated_at: str
    block_names: list[str] = field(default_factory=list)


def generate_privacy_page_markdown(
    appspec: AppSpec,
    *,
    app_title: str | None = None,
    last_updated: datetime | None = None,
    custom_header: str | None = None,
    custom_footer: str | None = None,
) -> PrivacyPageArtefacts:
    """Render the privacy-page + cookie-policy + ROPA bundle.

    Args:
        appspec: Linked AppSpec.
        app_title: Human-readable product name (falls back to appspec.title).
        last_updated: Timestamp for the "Last updated" line (defaults to now).
        custom_header: Optional markdown to appear before the auto-blocks.
        custom_footer: Optional markdown to appear after the auto-blocks.

    Returns:
        A PrivacyPageArtefacts with the three rendered documents.
    """
    title = app_title or appspec.title or appspec.name
    when = (last_updated or datetime.now(UTC)).strftime("%Y-%m-%d")

    # Enumerate data.
    pii_fields_by_category = _collect_pii_fields(appspec)
    subprocessors = merge_app_subprocessors(list(appspec.subprocessors))

    block_names: list[str] = []

    # Privacy page
    header = custom_header or _default_privacy_header(title, when)
    privacy_parts = [header.rstrip(), ""]

    privacy_parts.append(
        _auto_block(
            "pii_fields",
            _render_pii_fields_section(pii_fields_by_category, appspec),
        )
    )
    block_names.append("pii_fields")

    privacy_parts.append(_auto_block("subprocessors", _render_subprocessors_section(subprocessors)))
    block_names.append("subprocessors")

    privacy_parts.append(_auto_block("retention", _render_retention_section(appspec)))
    block_names.append("retention")

    privacy_parts.append(_auto_block("rights", _render_rights_section()))
    block_names.append("rights")

    privacy_parts.append(_auto_block("cookies", _render_cookie_section(subprocessors)))
    block_names.append("cookies")

    if custom_footer:
        privacy_parts.append(custom_footer.strip())

    privacy_md = "\n\n".join(p for p in privacy_parts if p).rstrip() + "\n"

    # Cookie policy (standalone)
    cookie_policy_md = _render_cookie_policy_markdown(title, when, subprocessors)

    # ROPA
    ropa_md = _render_ropa_markdown(title, when, appspec, subprocessors)

    return PrivacyPageArtefacts(
        privacy_policy=privacy_md,
        cookie_policy=cookie_policy_md,
        ropa=ropa_md,
        generated_at=when,
        block_names=block_names,
    )


# ---------------------------------------------------------------------------
# Section renderers
# ---------------------------------------------------------------------------


def _collect_pii_fields(
    appspec: AppSpec,
) -> dict[PIICategory | None, list[tuple[str, FieldSpec]]]:
    """Group all pii-annotated fields across entities by PII category."""
    out: dict[PIICategory | None, list[tuple[str, FieldSpec]]] = {}
    for entity in appspec.domain.entities:
        for f in entity.fields:
            if not isinstance(f, FieldSpec) or f.pii is None:
                continue
            category = f.pii.category
            out.setdefault(category, []).append((entity.title or entity.name, f))
    return out


def _render_pii_fields_section(
    by_category: dict[PIICategory | None, list[tuple[str, FieldSpec]]],
    appspec: AppSpec,
) -> str:
    """Render the 'What personal data we collect' section."""
    if not by_category:
        return "## What personal data we collect\n\nThis service does not store any personal data."

    lines = ["## What personal data we collect", ""]

    # Declared categories, in canonical order.
    for category in _CATEGORY_ORDER:
        rows = by_category.get(category)
        if not rows:
            continue
        heading = _CATEGORY_LABELS[category]
        lines.append(f"### {heading}")
        lines.append("")
        lines.append("| Entity | Field | Purpose |")
        lines.append("|---|---|---|")
        for entity_label, f in sorted(rows, key=lambda p: (p[0], p[1].name)):
            purpose = _field_purpose(f, category)
            lines.append(f"| {entity_label} | {f.name} | {purpose} |")
        lines.append("")

    # Uncategorised pii (bare `pii` without category)
    uncategorised = by_category.get(None)
    if uncategorised:
        lines.append("### Other personal data")
        lines.append("")
        lines.append("| Entity | Field |")
        lines.append("|---|---|")
        for entity_label, f in sorted(uncategorised, key=lambda p: (p[0], p[1].name)):
            lines.append(f"| {entity_label} | {f.name} |")
        lines.append("")

    return "\n".join(lines).rstrip()


def _field_purpose(f: FieldSpec, category: PIICategory | None) -> str:
    """Human-readable purpose sentence for a PII field."""
    # Heuristic default keyed on category; authors can edit outside the auto
    # block to refine per-field. Field-level `purpose` metadata is a future
    # extension.
    if f.is_special_category:
        return "Processing under explicit consent (GDPR Art. 9 special category)"
    if category is None:
        return "See relevant service feature"
    return {
        PIICategory.CONTACT: "Communication and account management",
        PIICategory.IDENTITY: "User identification and account security",
        PIICategory.LOCATION: "Service localisation and access control",
        PIICategory.FINANCIAL: "Billing and fraud prevention",
        PIICategory.HEALTH: "Service features requiring health context",
        PIICategory.BIOMETRIC: "Authentication and identity verification",
        PIICategory.BEHAVIORAL: "Service improvement and personalisation",
        PIICategory.FREEFORM: "User-entered content (may contain PII)",
    }.get(category, "See relevant service feature")


def _render_subprocessors_section(subprocessors: list[SubprocessorSpec]) -> str:
    """Render the 'Who we share data with' section."""
    if not subprocessors:
        return "## Who we share data with\n\nWe do not share personal data with third parties."

    lines = ["## Who we share data with", ""]
    for sp in subprocessors:
        lines.append(f"### {sp.label}")
        lines.append("")
        lines.append(
            f"- **Handler:** {sp.handler}"
            f"{' (' + sp.handler_address + ')' if sp.handler_address else ''}"
        )
        lines.append(f"- **Jurisdiction:** {sp.jurisdiction}")
        lines.append(f"- **Purpose:** {sp.purpose or _infer_purpose(sp)}")
        lines.append(f"- **Legal basis:** {sp.legal_basis.value.replace('_', ' ')}")
        lines.append(f"- **Consent category:** {sp.consent_category.value}")
        lines.append(f"- **Retention:** {sp.retention}")
        if sp.data_categories:
            cats = ", ".join(c.value for c in sp.data_categories)
            lines.append(f"- **Data shared:** {cats}")
        if sp.dpa_url:
            lines.append(f"- **DPA:** [{sp.dpa_url}]({sp.dpa_url})")
        if sp.needs_sccs and sp.scc_url:
            lines.append(f"- **SCCs (cross-border transfer):** [{sp.scc_url}]({sp.scc_url})")
        elif sp.needs_sccs:
            lines.append(
                "- **SCCs:** ⚠ This subprocessor processes data outside the EEA but "
                "no SCC URL has been declared. Add `scc_url:` to the declaration."
            )
        lines.append("")
    return "\n".join(lines).rstrip()


def _infer_purpose(sp: SubprocessorSpec) -> str:
    """Fallback purpose sentence when subprocessor has no explicit `purpose`."""
    label = sp.label.lower()
    if "analytics" in label:
        return "Usage analytics"
    if "payment" in label or "stripe" in label:
        return "Payment processing"
    if "email" in label or "mail" in label or "ses" in label:
        return "Email delivery"
    if "sms" in label or "twilio" in label:
        return "SMS / voice messaging"
    if "push" in label or "firebase" in label:
        return "Push notifications"
    return "Service operations"


def _render_retention_section(appspec: AppSpec) -> str:
    """Render the 'How long we keep data' section.

    Uses entity retention declarations (future extension) and subprocessor
    retention periods. In Phase 1 only the subprocessor side is populated.
    """
    return (
        "## How long we keep data\n\n"
        "Personal data is retained only for as long as necessary for the purpose "
        "for which it was collected or as required by law. Each category below has "
        "its own retention period:\n\n"
        "- **Account data**: while the account is active, then 90 days after closure.\n"
        "- **Billing and transaction records**: 7 years (regulatory).\n"
        "- **Audit and security logs**: 1 year.\n"
        "- **Analytics and usage data**: see individual subprocessor retention "
        "in the section above.\n"
        "\n"
        "After retention expires, personal data is deleted or irreversibly anonymised."
    )


def _render_rights_section() -> str:
    """Render the GDPR rights section with framework-provided endpoints."""
    return (
        "## Your rights\n\n"
        "Under GDPR and equivalent laws, you have the following rights:\n\n"
        "- **Access your data**: [/gdpr/access](/gdpr/access)\n"
        "- **Correct your data**: contact support or use your account settings.\n"
        "- **Delete your data**: [/gdpr/erase](/gdpr/erase)\n"
        "- **Export your data (portability)**: [/gdpr/portability](/gdpr/portability)\n"
        "- **Withdraw consent**: click 'Manage cookies' in the page footer at any time.\n"
        "- **Lodge a complaint**: contact your national data-protection authority.\n"
        "\n"
        "We respond to data-subject requests within 30 days."
    )


def _render_cookie_section(subprocessors: list[SubprocessorSpec]) -> str:
    """Render the 'Cookies' section inside the privacy page."""
    rows = _cookie_rows(subprocessors)
    if not rows:
        return "## Cookies\n\nThis service does not set any non-essential cookies."
    lines = ["## Cookies", ""]
    lines.append("| Name | Source | Category | Purpose |")
    lines.append("|---|---|---|---|")
    for row in rows:
        lines.append(
            f"| `{row['name']}` | {row['source']} | {row['category']} | {row['purpose']} |"
        )
    lines.append("")
    lines.append("A detailed cookie policy is available at [/cookies](/cookies).")
    return "\n".join(lines).rstrip()


def _render_cookie_policy_markdown(
    title: str,
    when: str,
    subprocessors: list[SubprocessorSpec],
) -> str:
    """Render the full standalone cookie-policy document."""
    rows = _cookie_rows(subprocessors)
    lines = [
        f"# Cookie Policy — {title}",
        "",
        f"**Last updated:** {when}",
        "",
        "This page lists every cookie this service may set, the subprocessor "
        "that sets it, the category it falls under (per our consent banner), "
        "and its purpose. Essential (functional) cookies are always on; the "
        "rest fire only when you grant consent.",
        "",
    ]

    lines.append(AUTO_START.format(name="cookies"))

    if not rows:
        lines.append("")
        lines.append("This service does not set any cookies beyond essential security cookies.")
    else:
        lines.append("")
        lines.append("| Name | Source | Category | Purpose |")
        lines.append("|---|---|---|---|")
        for row in rows:
            lines.append(
                f"| `{row['name']}` | {row['source']} | {row['category']} | {row['purpose']} |"
            )
    lines.append("")
    lines.append(AUTO_END)
    lines.append("")
    lines.append("## Managing your choices")
    lines.append("")
    lines.append(
        "You can change your consent preferences at any time by clicking "
        "'Manage cookies' in the page footer, or by pressing the shortcut "
        "that reopens the consent banner."
    )
    return "\n".join(lines).rstrip() + "\n"


def _cookie_rows(subprocessors: list[SubprocessorSpec]) -> list[dict[str, str]]:
    """Flatten subprocessor cookie declarations to a row list."""
    rows: list[dict[str, str]] = []
    for sp in subprocessors:
        for cookie in sp.cookies:
            rows.append(
                {
                    "name": cookie,
                    "source": sp.label,
                    "category": sp.consent_category.value,
                    "purpose": sp.purpose or _infer_purpose(sp),
                }
            )
    return rows


def _render_ropa_markdown(
    title: str,
    when: str,
    appspec: AppSpec,
    subprocessors: list[SubprocessorSpec],
) -> str:
    """Render the ROPA (GDPR Article 30) document."""
    lines = [
        f"# Record of Processing Activities — {title}",
        "",
        f"**Last updated:** {when}",
        "",
        "This document records the processing activities for the controller "
        "as required by GDPR Article 30. Each row describes one processing "
        "activity: what data, for what purpose, who handles it, how long it "
        "is retained, and what legal basis supports the processing.",
        "",
        AUTO_START.format(name="ropa"),
        "",
        "| Activity | Data categories | Recipients | Jurisdiction | Retention | Legal basis |",
        "|---|---|---|---|---|---|",
    ]

    # Use subprocessors as the primary row source; PII categories feed the
    # "Data categories" column. This works for Phase 2; Phase 3+ will expand
    # with per-activity decomposition.
    pii_categories = _summarise_pii_categories(appspec)
    pii_summary = ", ".join(c.value for c in pii_categories) if pii_categories else "-"

    if not subprocessors:
        lines.append(
            f"| Service operations | {pii_summary} | (no external subprocessors) | - | "
            "see retention policy | contract / legitimate interest |"
        )
    else:
        for sp in subprocessors:
            cats = (
                ", ".join(c.value for c in sp.data_categories)
                if sp.data_categories
                else pii_summary
            )
            lines.append(
                f"| {sp.label} | {cats} | {sp.handler} | "
                f"{sp.jurisdiction} | {sp.retention} | "
                f"{sp.legal_basis.value.replace('_', ' ')} |"
            )

    lines.append("")
    lines.append(AUTO_END)
    lines.append("")
    lines.append("## Cross-border transfers")
    lines.append("")
    non_eea = [sp for sp in subprocessors if sp.needs_sccs]
    if non_eea:
        for sp in non_eea:
            scc = sp.scc_url or "(SCC URL not declared)"
            lines.append(f"- **{sp.label}** ({sp.jurisdiction}): {scc}")
    else:
        lines.append("No processing activities transfer personal data outside the EEA.")
    return "\n".join(lines).rstrip() + "\n"


def _summarise_pii_categories(appspec: AppSpec) -> list[PIICategory]:
    """Unique list of PII categories declared across the app."""
    seen: set[PIICategory] = set()
    for entity in appspec.domain.entities:
        for f in entity.fields:
            if not isinstance(f, FieldSpec) or f.pii is None:
                continue
            if f.pii.category is not None:
                seen.add(f.pii.category)
    # Preserve canonical order
    return [c for c in _CATEGORY_ORDER if c in seen]


# ---------------------------------------------------------------------------
# Merge with existing document (respect author edits outside DZ-AUTO blocks)
# ---------------------------------------------------------------------------


def merge_regenerated_into_existing(
    existing_markdown: str,
    regenerated_markdown: str,
) -> str:
    """Replace DZ-AUTO blocks in existing with fresh content from regenerated.

    Content outside auto-blocks in the existing document is preserved.
    Content outside auto-blocks in the regenerated document is discarded
    (only the auto-blocks are used to refresh). Auto-blocks missing from
    the existing doc are appended to the end with a subtle divider so the
    author can notice new auto content.

    Block matching is by ``name``.
    """
    fresh_blocks = _extract_auto_blocks(regenerated_markdown)
    existing_names = set(_extract_auto_blocks(existing_markdown).keys())

    def _replace(match: re.Match[str]) -> str:
        name = match.group("name")
        return fresh_blocks.get(name, match.group(0))

    merged = _AUTO_BLOCK_RE.sub(_replace, existing_markdown)

    # Append any new blocks that weren't in the existing doc.
    new_blocks = [b for name, b in fresh_blocks.items() if name not in existing_names]
    if new_blocks:
        merged = merged.rstrip() + "\n\n" + "\n\n".join(new_blocks) + "\n"

    return merged


def _extract_auto_blocks(markdown: str) -> dict[str, str]:
    """Return {name: full_block_text_including_delimiters} map."""
    out: dict[str, str] = {}
    for match in _AUTO_BLOCK_RE.finditer(markdown):
        out[match.group("name")] = match.group(0)
    return out


def _auto_block(name: str, body: str) -> str:
    """Wrap `body` in a DZ-AUTO block."""
    return f"{AUTO_START.format(name=name)}\n\n{body.rstrip()}\n\n{AUTO_END}"


def _default_privacy_header(title: str, when: str) -> str:
    """Render the default header (content outside auto blocks that authors can edit)."""
    return (
        f"# Privacy Notice — {title}\n\n"
        f"**Last updated:** {when}\n\n"
        "This notice explains how we handle your personal data. The sections "
        "below list every kind of data we collect, who we share it with, how "
        "long we keep it, and the rights you have under GDPR and equivalent "
        "laws.\n\n"
        "Our legal basis for each processing activity is declared in the "
        "subprocessor table. If you have a question that isn't answered here, "
        "contact us using the details at the bottom of the page."
    )


# ---------------------------------------------------------------------------
# Lightweight helpers for the CLI/compliance-pack use cases
# ---------------------------------------------------------------------------


def write_privacy_artefacts(
    artefacts: PrivacyPageArtefacts,
    out_dir: Any,
) -> dict[str, Any]:
    """Write the three artefacts to ``<out_dir>/`` and return the paths.

    ``out_dir`` is accepted as Any to avoid a hard pathlib dependency in the
    public API; the caller typically passes a pathlib.Path.
    """
    from pathlib import Path

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    privacy_path = out / "privacy_policy.md"
    cookie_path = out / "cookie_policy.md"
    ropa_path = out / "ropa.md"

    privacy_path.write_text(artefacts.privacy_policy)
    cookie_path.write_text(artefacts.cookie_policy)
    ropa_path.write_text(artefacts.ropa)

    return {
        "privacy_policy": privacy_path,
        "cookie_policy": cookie_path,
        "ropa": ropa_path,
    }
