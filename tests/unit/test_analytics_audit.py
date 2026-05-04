"""Tests for the `dazzle analytics audit` CLI (v0.61.0)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dazzle.cli.analytics import _match_pii_hint, analytics_app


def _write_project(root: Path, app_dsl: str) -> None:
    (root / "dazzle.toml").write_text(
        """[project]
name = "t"
version = "0.1.0"
root = "t"

[modules]
paths = ["./dsl"]
"""
    )
    dsl_dir = root / "dsl"
    dsl_dir.mkdir(exist_ok=True)
    (dsl_dir / "app.dsl").write_text(app_dsl)


class TestPIINameHint:
    """Heuristic name-matcher unit tests — isolated from IR and CLI."""

    @pytest.mark.parametrize(
        "field_name, expected_category",
        [
            ("email", "contact"),
            ("user_email", "contact"),
            ("phone", "contact"),
            ("mobile_phone", "contact"),
            # ip_address must match `location` before `address→contact`
            ("ip_address", "location"),
            ("client_ip_address", "location"),
            ("address", "contact"),
            ("home_address", "contact"),
            ("dob", "identity"),
            ("date_of_birth", "identity"),
            ("ssn", "identity"),
            ("first_name", "identity"),
            ("bank_account", "financial"),
            ("iban", "financial"),
            ("salary", "financial"),
            ("fingerprint_hash", "biometric"),
            ("medical_record", "health"),
            # case-insensitive
            ("EMAIL", "contact"),
            ("DATE_OF_BIRTH", "identity"),
            # no match
            ("title", None),
            ("status", None),
            ("created_at", None),
        ],
        ids=[
            "email_contact",
            "user_email_contact",
            "phone_contact",
            "mobile_phone_contact",
            "ip_address_location",
            "client_ip_address_location",
            "address_contact",
            "home_address_contact",
            "dob_identity",
            "date_of_birth_identity",
            "ssn_identity",
            "first_name_identity",
            "bank_account_financial",
            "iban_financial",
            "salary_financial",
            "fingerprint_hash_biometric",
            "medical_record_health",
            "EMAIL_case_insensitive",
            "DATE_OF_BIRTH_case_insensitive",
            "title_no_match",
            "status_no_match",
            "created_at_no_match",
        ],
    )
    def test_pii_name_hint(self, field_name: str, expected_category: str | None) -> None:
        assert _match_pii_hint(field_name) == expected_category


class TestAuditCommand:
    def test_flags_unannotated_pii_fields(self, tmp_path: Path) -> None:
        _write_project(
            tmp_path,
            """module t
app T "T"
entity User "User":
  id: uuid pk
  email: str(200)
  phone: str(50) pii(category=contact)
  dob: date
""",
        )

        runner = CliRunner()
        result = runner.invoke(
            analytics_app,
            ["--project-dir", str(tmp_path), "--format", "json"],
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)

        flagged = {(f["entity"], f["field"]) for f in data["pii_name_hints"]}
        # email and dob unannotated → flagged
        assert ("User", "email") in flagged
        assert ("User", "dob") in flagged
        # phone is annotated → NOT flagged
        assert ("User", "phone") not in flagged

    def test_ignores_annotated_fields(self, tmp_path: Path) -> None:
        _write_project(
            tmp_path,
            """module t
app T "T"
entity U "U":
  id: uuid pk
  email: str(200) pii(category=contact)
  phone: str(50) pii(category=contact)
""",
        )

        runner = CliRunner()
        result = runner.invoke(
            analytics_app,
            ["--project-dir", str(tmp_path), "--format", "json"],
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["pii_name_hints"] == []

    def test_reports_framework_subprocessors_by_default(self, tmp_path: Path) -> None:
        _write_project(
            tmp_path,
            """module t
app T "T"
entity E "E":
  id: uuid pk
""",
        )

        runner = CliRunner()
        result = runner.invoke(
            analytics_app,
            ["--project-dir", str(tmp_path), "--format", "json"],
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        names = {sp["name"] for sp in data["subprocessors"]}
        # All framework defaults appear in the audit even without any app
        # declarations — tests the surface to keep authors aware.
        assert {"google_analytics", "plausible", "stripe"} <= names

    def test_detects_collision(self, tmp_path: Path) -> None:
        """App subprocessor that overrides framework with conflicting consent cat."""
        _write_project(
            tmp_path,
            """module t
app T "T"
entity E "E":
  id: uuid pk

subprocessor google_analytics "GA Custom":
  handler: "ACME"
  jurisdiction: US
  retention: "1 year"
  legal_basis: consent
  consent_category: functional
""",
        )

        runner = CliRunner()
        result = runner.invoke(
            analytics_app,
            ["--project-dir", str(tmp_path), "--format", "json"],
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        ga = next(sp for sp in data["subprocessors"] if sp["name"] == "google_analytics")
        assert ga["is_framework_default"] is False
        collision = ga["collision_with_framework_default"]
        assert collision is not None
        assert collision["framework_consent_category"] == "analytics"
        assert collision["app_consent_category"] == "functional"

    def test_table_output_succeeds(self, tmp_path: Path) -> None:
        _write_project(
            tmp_path,
            """module t
app T "T"
entity E "E":
  id: uuid pk
  email: str(200)
""",
        )

        runner = CliRunner()
        result = runner.invoke(
            analytics_app,
            ["--project-dir", str(tmp_path)],
        )
        assert result.exit_code == 0, result.output
        assert "PII annotation audit" in result.output
        assert "Subprocessors" in result.output
        assert "E.email" in result.output

    def test_audit_does_not_fail_build(self, tmp_path: Path) -> None:
        """Even with many findings, exit code must be 0 — warn-only."""
        _write_project(
            tmp_path,
            """module t
app T "T"
entity U "U":
  id: uuid pk
  email: str(200)
  phone: str(50)
  dob: date
  ssn: str(20)
  first_name: str(100)
  last_name: str(100)
""",
        )

        runner = CliRunner()
        result = runner.invoke(
            analytics_app,
            ["--project-dir", str(tmp_path)],
        )
        assert result.exit_code == 0, result.output
