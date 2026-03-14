"""Tests for compliance signal matching heuristics.

Verifies that _match_compliance_pattern correctly identifies PII/financial
fields while avoiding false positives on system and technical fields.
"""

from __future__ import annotations

from dazzle.mcp.event_first_tools import (
    _match_compliance_pattern,
    infer_compliance_requirements,
)


class TestWordBoundaryMatching:
    """Pattern must match a complete underscore-delimited segment."""

    def test_exact_field_matches(self):
        assert _match_compliance_pattern("email", "Contact", "email", 0.95) is not None

    def test_segment_match(self):
        assert _match_compliance_pattern("user_email", "Contact", "email", 0.95) is not None

    def test_substring_rejected(self):
        """'named' should not match pattern 'name'."""
        assert _match_compliance_pattern("named_entity", "Task", "name", 0.7) is None

    def test_prefix_substring_rejected(self):
        """'rename' should not match pattern 'name'."""
        assert _match_compliance_pattern("rename_count", "Task", "name", 0.7) is None

    def test_multi_word_pattern(self):
        assert (
            _match_compliance_pattern("social_security_number", "User", "social_security", 0.99)
            is not None
        )


class TestNeutralizingContext:
    """Fields with qualifying prefixes should be rejected or deprioritized."""

    def test_ip_address_rejected(self):
        """ip_address is technical, not postal."""
        assert _match_compliance_pattern("ip_address", "AuditLog", "address", 0.85) is None

    def test_mac_address_rejected(self):
        assert _match_compliance_pattern("mac_address", "Device", "address", 0.85) is None

    def test_wallet_address_rejected(self):
        assert _match_compliance_pattern("wallet_address", "Account", "address", 0.85) is None

    def test_entity_name_rejected(self):
        """target_entity_name is an identifier, not a person."""
        assert _match_compliance_pattern("target_entity_name", "AuditLog", "name", 0.7) is None

    def test_rule_name_rejected(self):
        assert _match_compliance_pattern("rule_name", "FlaggingRule", "name", 0.7) is None

    def test_service_name_rejected(self):
        assert _match_compliance_pattern("service_name", "Integration", "name", 0.7) is None

    def test_display_name_rejected(self):
        assert _match_compliance_pattern("display_name", "Config", "name", 0.7) is None

    def test_tenant_name_rejected(self):
        assert _match_compliance_pattern("xero_tenant_name", "XeroIntegration", "name", 0.7) is None

    def test_scorecard_not_financial(self):
        """'scorecard' should not match 'card' pattern."""
        assert _match_compliance_pattern("score_card", "Report", "card", 0.9) is None

    def test_postal_address_still_matches(self):
        """A plain 'address' field on a Contact entity is real PII."""
        result = _match_compliance_pattern("address", "Contact", "address", 0.85)
        assert result is not None
        assert result >= 0.8

    def test_person_name_still_matches(self):
        """'name' on a User entity is real PII."""
        result = _match_compliance_pattern("name", "User", "name", 0.7)
        assert result is not None
        assert result >= 0.5

    def test_first_name_still_matches(self):
        """'first_name' should match — no neutralizing prefix."""
        result = _match_compliance_pattern("first_name", "Employee", "name", 0.7)
        assert result is not None


class TestEntityContextAwareness:
    """System entities should get reduced confidence."""

    def test_audit_entity_reduced(self):
        """Fields on AuditLog get significantly reduced confidence."""
        result = _match_compliance_pattern("name", "AuditLog", "name", 0.7)
        # Even if not neutralized, should be very low confidence
        assert result is None or result < 0.4

    def test_log_entity_reduced(self):
        result = _match_compliance_pattern("email", "LogEntry", "email", 0.95)
        assert result is not None
        assert result < 0.5

    def test_normal_entity_full_confidence(self):
        result = _match_compliance_pattern("email", "Contact", "email", 0.95)
        assert result == 0.95

    def test_event_entity_reduced(self):
        result = _match_compliance_pattern("name", "EventPayload", "name", 0.7)
        # System entity + "name" pattern = very low or None
        assert result is None or result < 0.4


class TestUKGovernmentIdentifiers:
    """UK-specific PII patterns: NINO, UTR, sort codes."""

    def test_ni_number_matches(self):
        result = _match_compliance_pattern("ni_number", "Contact", "ni_number", 0.99)
        assert result is not None
        assert result >= 0.95

    def test_nino_matches(self):
        result = _match_compliance_pattern("nino", "Employee", "nino", 0.99)
        assert result is not None
        assert result >= 0.95

    def test_national_insurance_prefix_matches(self):
        """national_insurance_number should match national_insurance pattern."""
        result = _match_compliance_pattern(
            "national_insurance_number", "Contact", "national_insurance", 0.99
        )
        assert result is not None
        assert result >= 0.95

    def test_personal_utr_matches(self):
        """personal_utr should match utr pattern (segment match)."""
        result = _match_compliance_pattern("personal_utr", "SoleTrader", "utr", 0.95)
        assert result is not None
        assert result >= 0.9

    def test_unique_taxpayer_reference_matches(self):
        result = _match_compliance_pattern(
            "unique_taxpayer_reference", "Contact", "unique_taxpayer_reference", 0.95
        )
        assert result is not None
        assert result >= 0.9

    def test_sort_code_matches_financial(self):
        """bank_sort_code should match sort_code pattern."""
        result = _match_compliance_pattern("bank_sort_code", "Employee", "sort_code", 0.9)
        assert result is not None
        assert result >= 0.85

    def test_sort_code_standalone(self):
        result = _match_compliance_pattern("sort_code", "BankAccount", "sort_code", 0.9)
        assert result is not None
        assert result >= 0.85


class TestConfidenceThreshold:
    """Very low confidence signals should be suppressed."""

    def test_below_threshold_returns_none(self):
        """If entity reduction pushes confidence below 0.3, return None."""
        # 0.7 * 0.4 = 0.28, below threshold
        result = _match_compliance_pattern("name", "AuditLog", "name", 0.7)
        assert result is None


class _AppSpecHelper:
    """Shared helpers for building mock AppSpec objects."""

    @staticmethod
    def _make_appspec(entities, policies=None):
        from unittest.mock import MagicMock

        spec = MagicMock()
        spec.domain.entities = entities
        spec.policies = policies
        return spec

    @staticmethod
    def _make_entity(name, field_names):
        from unittest.mock import MagicMock

        entity = MagicMock()
        entity.name = name
        fields = []
        for fn in field_names:
            f = MagicMock()
            f.name = fn
            fields.append(f)
        entity.fields = fields
        entity.access = None
        return entity


class TestInferComplianceUKFields(_AppSpecHelper):
    """End-to-end: infer_compliance_requirements detects UK identifiers."""

    def test_nino_and_utr_detected_as_pii(self):
        entity = self._make_entity("Contact", ["id", "name", "ni_number", "personal_utr", "email"])
        appspec = self._make_appspec([entity])
        result = infer_compliance_requirements(appspec)

        pii_field_names = {f["field"] for f in result["pii_fields"]}
        assert "ni_number" in pii_field_names
        assert "personal_utr" in pii_field_names

    def test_sort_code_detected_as_financial(self):
        entity = self._make_entity("Employee", ["id", "bank_sort_code", "bank_account_number"])
        appspec = self._make_appspec([entity])
        result = infer_compliance_requirements(appspec)

        fin_field_names = {f["field"] for f in result["financial_fields"]}
        assert "bank_sort_code" in fin_field_names
        assert "bank_account_number" in fin_field_names

    def test_gdpr_recommended_for_nino(self):
        entity = self._make_entity("Employee", ["id", "nino"])
        appspec = self._make_appspec([entity])
        result = infer_compliance_requirements(appspec)

        assert "GDPR" in result["recommended_frameworks"]


class TestDslClassifyDirectives(_AppSpecHelper):
    """DSL classify directives should be used with confidence=1.0 and skip pattern matching."""

    @staticmethod
    def _make_policies(classifications):
        from unittest.mock import MagicMock

        policies = MagicMock()
        policies.classifications = classifications
        return policies

    @staticmethod
    def _make_classification(entity, field, classification_value):
        from unittest.mock import MagicMock

        cls = MagicMock()
        cls.entity = entity
        cls.field = field
        cls.classification.value = classification_value
        return cls

    def test_pii_direct_from_classify(self):
        """classify Customer.email as PII_DIRECT → pii_fields with confidence 1.0."""
        entity = self._make_entity("Customer", ["id", "email"])
        cls = self._make_classification("Customer", "email", "pii_direct")
        policies = self._make_policies([cls])
        appspec = self._make_appspec([entity], policies=policies)

        result = infer_compliance_requirements(appspec)
        pii = result["pii_fields"]
        # Should have exactly one entry from classify, none from pattern matching
        email_entries = [e for e in pii if e["field"] == "email"]
        assert len(email_entries) == 1
        assert email_entries[0]["confidence"] == 1.0
        assert email_entries[0]["pattern"] == "classify:pii_direct"

    def test_financial_from_classify(self):
        """classify Order.total as FINANCIAL_TXN → financial_fields."""
        entity = self._make_entity("Order", ["id", "total"])
        cls = self._make_classification("Order", "total", "financial_txn")
        policies = self._make_policies([cls])
        appspec = self._make_appspec([entity], policies=policies)

        result = infer_compliance_requirements(appspec)
        fin = result["financial_fields"]
        total_entries = [e for e in fin if e["field"] == "total"]
        assert len(total_entries) == 1
        assert total_entries[0]["confidence"] == 1.0

    def test_classified_field_skips_pattern_matching(self):
        """A field classified via DSL should not also appear from pattern matching."""
        entity = self._make_entity("Customer", ["id", "email", "phone"])
        cls = self._make_classification("Customer", "email", "pii_direct")
        policies = self._make_policies([cls])
        appspec = self._make_appspec([entity], policies=policies)

        result = infer_compliance_requirements(appspec)
        pii = result["pii_fields"]
        email_entries = [e for e in pii if e["field"] == "email"]
        # Only the classify entry, no pattern-match duplicate
        assert len(email_entries) == 1
        assert email_entries[0]["pattern"] == "classify:pii_direct"
        # phone should still be detected by pattern matching
        phone_entries = [e for e in pii if e["field"] == "phone"]
        assert len(phone_entries) >= 1
        assert phone_entries[0]["confidence"] < 1.0

    def test_no_policies_still_works(self):
        """When appspec.policies is None, pattern matching runs normally."""
        entity = self._make_entity("Customer", ["id", "email"])
        appspec = self._make_appspec([entity], policies=None)

        result = infer_compliance_requirements(appspec)
        pii = result["pii_fields"]
        email_entries = [e for e in pii if e["field"] == "email"]
        assert len(email_entries) >= 1
        assert email_entries[0]["confidence"] < 1.0  # From pattern matching
