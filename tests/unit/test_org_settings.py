"""Unit tests for OrganizationRecord.settings field (#1424 phase 1)."""

from dazzle.http.runtime.auth.models import OrganizationRecord


def test_organization_record_has_settings_default_empty():
    org = OrganizationRecord(id="t1", slug="acme", name="Acme")
    assert org.settings == {}


def test_organization_record_settings_roundtrip():
    org = OrganizationRecord(
        id="t1",
        slug="acme",
        name="Acme",
        settings={"domain_join_policy": "auto_join"},
    )
    assert org.settings["domain_join_policy"] == "auto_join"
