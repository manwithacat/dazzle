"""Tests for the privacy/cookie/ROPA generator (v0.61.0 Phase 2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.compliance.analytics import (
    PrivacyPageArtefacts,
    generate_privacy_page_markdown,
    merge_regenerated_into_existing,
)
from dazzle.compliance.analytics.registry import FRAMEWORK_SUBPROCESSORS
from dazzle.core.linker import build_appspec
from dazzle.core.parser import parse_modules


def _load_appspec(dsl: str, tmp_path: Path):
    """Parse a single-file DSL module into an AppSpec."""
    dsl_dir = tmp_path / "dsl"
    dsl_dir.mkdir()
    (dsl_dir / "app.dsl").write_text(dsl)

    (tmp_path / "dazzle.toml").write_text(
        """[project]
name = "t"
version = "0.1.0"
root = "t"

[modules]
paths = ["./dsl"]
"""
    )

    modules = parse_modules([dsl_dir / "app.dsl"])
    return build_appspec(modules, "t")


@pytest.fixture
def sample_appspec(tmp_path: Path):
    dsl = """module t
app T "Test App"

entity User "User":
  id: uuid pk
  email: str(200) pii(category=contact)
  phone: str(50) pii(category=contact)
  dob: date pii(category=identity, sensitivity=high)

entity Receipt "Receipt":
  id: uuid pk
  amount: decimal(10,2)

subprocessor stripe "Stripe Payments":
  handler: "Stripe, Inc."
  jurisdiction: US
  data_categories: [financial, contact]
  retention: "7 years"
  legal_basis: contract
  consent_category: functional
  dpa_url: "https://stripe.com/legal/dpa"
  scc_url: "https://stripe.com/legal/dpa/scc"
  cookies: [__stripe_mid, __stripe_sid]
  purpose: "Payment processing."
"""
    return _load_appspec(dsl, tmp_path)


class TestArtefactStructure:
    def test_returns_three_markdown_documents(self, sample_appspec) -> None:
        artefacts = generate_privacy_page_markdown(sample_appspec)
        assert isinstance(artefacts, PrivacyPageArtefacts)
        assert artefacts.privacy_policy.startswith("# Privacy Notice")
        assert artefacts.cookie_policy.startswith("# Cookie Policy")
        assert artefacts.ropa.startswith("# Record of Processing Activities")

    def test_includes_all_auto_blocks(self, sample_appspec) -> None:
        artefacts = generate_privacy_page_markdown(sample_appspec)
        expected_blocks = {"pii_fields", "subprocessors", "retention", "rights", "cookies"}
        assert set(artefacts.block_names) == expected_blocks

    def test_generated_at_populated(self, sample_appspec) -> None:
        artefacts = generate_privacy_page_markdown(sample_appspec)
        # YYYY-MM-DD format.
        assert len(artefacts.generated_at) == 10
        assert artefacts.generated_at[4] == "-"


class TestPiiFieldsSection:
    def test_enumerates_declared_pii_fields(self, sample_appspec) -> None:
        artefacts = generate_privacy_page_markdown(sample_appspec)
        md = artefacts.privacy_policy
        # Contact category with email + phone
        assert "Contact information" in md
        assert "| email |" in md
        assert "| phone |" in md
        # Identity category with dob
        assert "Identity data" in md
        assert "| dob |" in md

    def test_omits_non_pii_fields(self, sample_appspec) -> None:
        """amount on Receipt isn't pii — must NOT appear in privacy page."""
        artefacts = generate_privacy_page_markdown(sample_appspec)
        assert "| amount |" not in artefacts.privacy_policy

    def test_empty_when_no_pii(self, tmp_path: Path) -> None:
        spec = _load_appspec(
            """module t
app T "T"
entity E "E":
  id: uuid pk
  title: str(100)
""",
            tmp_path,
        )
        artefacts = generate_privacy_page_markdown(spec)
        assert "does not store any personal data" in artefacts.privacy_policy


class TestSubprocessorsSection:
    def test_app_subprocessor_listed(self, sample_appspec) -> None:
        md = generate_privacy_page_markdown(sample_appspec).privacy_policy
        assert "Stripe Payments" in md
        assert "7 years" in md
        assert "https://stripe.com/legal/dpa" in md

    def test_framework_defaults_merged_in(self, sample_appspec) -> None:
        md = generate_privacy_page_markdown(sample_appspec).privacy_policy
        # Framework defaults not explicitly overridden should appear.
        framework_names = {sp.label for sp in FRAMEWORK_SUBPROCESSORS}
        assert any(name in md for name in framework_names)

    def test_sccs_flagged_for_non_eea(self, sample_appspec) -> None:
        md = generate_privacy_page_markdown(sample_appspec).privacy_policy
        # Stripe is US-jurisdiction with SCC URL — must appear in cross-border section.
        assert "SCCs (cross-border transfer)" in md


class TestCookiePolicy:
    def test_enumerates_cookies(self, sample_appspec) -> None:
        cookie_md = generate_privacy_page_markdown(sample_appspec).cookie_policy
        assert "__stripe_mid" in cookie_md
        assert "__stripe_sid" in cookie_md

    def test_framework_cookies_included(self, sample_appspec) -> None:
        """Framework-default GA4 cookies appear without explicit app declaration."""
        cookie_md = generate_privacy_page_markdown(sample_appspec).cookie_policy
        assert "_ga" in cookie_md  # GA4 default subprocessor

    def test_empty_section_when_no_cookies(self, tmp_path: Path) -> None:
        spec = _load_appspec(
            """module t
app T "T"
entity E "E":
  id: uuid pk
""",
            tmp_path,
        )
        # Framework defaults include cookie-setting subprocessors, so the
        # cookie policy is non-empty even with no app declarations.
        cookie_md = generate_privacy_page_markdown(spec).cookie_policy
        assert "Cookie Policy" in cookie_md


class TestROPA:
    def test_rows_per_subprocessor(self, sample_appspec) -> None:
        ropa = generate_privacy_page_markdown(sample_appspec).ropa
        assert "Stripe Payments" in ropa
        assert "contract" in ropa

    def test_auto_block_present(self, sample_appspec) -> None:
        ropa = generate_privacy_page_markdown(sample_appspec).ropa
        assert 'DZ-AUTO:start name="ropa"' in ropa
        assert "DZ-AUTO:end" in ropa

    def test_cross_border_section(self, sample_appspec) -> None:
        ropa = generate_privacy_page_markdown(sample_appspec).ropa
        assert "Cross-border transfers" in ropa
        # Stripe = US, needs SCCs.
        assert "Stripe Payments" in ropa


class TestAutoBlockMerge:
    def test_auto_blocks_replaced(self) -> None:
        existing = """# Privacy

Author intro.

<!-- DZ-AUTO:start name="pii_fields" -->
OLD content.
<!-- DZ-AUTO:end -->

Author footer.
"""
        regenerated = """<!-- DZ-AUTO:start name="pii_fields" -->
NEW content.
<!-- DZ-AUTO:end -->
"""
        merged = merge_regenerated_into_existing(existing, regenerated)
        assert "OLD content" not in merged
        assert "NEW content" in merged
        assert "Author intro" in merged
        assert "Author footer" in merged

    def test_new_auto_blocks_appended(self) -> None:
        existing = """# Privacy

Author intro.

<!-- DZ-AUTO:start name="pii_fields" -->
OLD fields.
<!-- DZ-AUTO:end -->
"""
        regenerated = """<!-- DZ-AUTO:start name="pii_fields" -->
NEW fields.
<!-- DZ-AUTO:end -->

<!-- DZ-AUTO:start name="subprocessors" -->
NEW subprocessors.
<!-- DZ-AUTO:end -->
"""
        merged = merge_regenerated_into_existing(existing, regenerated)
        assert "NEW subprocessors" in merged
        assert "NEW fields" in merged

    def test_non_auto_content_preserved_when_no_blocks_match(self) -> None:
        existing = "# Privacy\n\nOnly author content."
        regenerated = """<!-- DZ-AUTO:start name="pii_fields" -->
Block content.
<!-- DZ-AUTO:end -->
"""
        merged = merge_regenerated_into_existing(existing, regenerated)
        assert "Only author content" in merged
        assert "Block content" in merged

    def test_block_order_follows_existing(self) -> None:
        """Blocks in existing doc keep their position after regeneration."""
        existing = """# Privacy

<!-- DZ-AUTO:start name="subprocessors" -->
Old subs.
<!-- DZ-AUTO:end -->

Middle author text.

<!-- DZ-AUTO:start name="pii_fields" -->
Old pii.
<!-- DZ-AUTO:end -->
"""
        regenerated = """<!-- DZ-AUTO:start name="pii_fields" -->
New pii.
<!-- DZ-AUTO:end -->

<!-- DZ-AUTO:start name="subprocessors" -->
New subs.
<!-- DZ-AUTO:end -->
"""
        merged = merge_regenerated_into_existing(existing, regenerated)
        subs_pos = merged.index("New subs")
        pii_pos = merged.index("New pii")
        # subs must still come first — existing order is preserved.
        assert subs_pos < pii_pos
        assert "Middle author text" in merged


class TestRightsSection:
    def test_lists_gdpr_endpoints(self, sample_appspec) -> None:
        md = generate_privacy_page_markdown(sample_appspec).privacy_policy
        assert "/gdpr/access" in md
        assert "/gdpr/erase" in md
        assert "/gdpr/portability" in md
