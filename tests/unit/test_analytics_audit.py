"""Tests for the `dazzle analytics audit` CLI (v0.61.0)."""

from __future__ import annotations

import json
from pathlib import Path

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

    def test_email_contact(self) -> None:
        assert _match_pii_hint("email") == "contact"
        assert _match_pii_hint("user_email") == "contact"

    def test_phone_contact(self) -> None:
        assert _match_pii_hint("phone") == "contact"
        assert _match_pii_hint("mobile_phone") == "contact"

    def test_ip_address_location_not_contact(self) -> None:
        """ip_address must match `location` before `address→contact`."""
        assert _match_pii_hint("ip_address") == "location"
        assert _match_pii_hint("client_ip_address") == "location"

    def test_address_still_contact(self) -> None:
        assert _match_pii_hint("address") == "contact"
        assert _match_pii_hint("home_address") == "contact"

    def test_dob_identity(self) -> None:
        assert _match_pii_hint("dob") == "identity"
        assert _match_pii_hint("date_of_birth") == "identity"

    def test_ssn_identity(self) -> None:
        assert _match_pii_hint("ssn") == "identity"

    def test_first_name_identity(self) -> None:
        assert _match_pii_hint("first_name") == "identity"

    def test_financial(self) -> None:
        assert _match_pii_hint("bank_account") == "financial"
        assert _match_pii_hint("iban") == "financial"
        assert _match_pii_hint("salary") == "financial"

    def test_biometric(self) -> None:
        assert _match_pii_hint("fingerprint_hash") == "biometric"

    def test_health(self) -> None:
        assert _match_pii_hint("medical_record") == "health"

    def test_case_insensitive(self) -> None:
        assert _match_pii_hint("EMAIL") == "contact"
        assert _match_pii_hint("DATE_OF_BIRTH") == "identity"

    def test_no_match(self) -> None:
        assert _match_pii_hint("title") is None
        assert _match_pii_hint("status") is None
        assert _match_pii_hint("created_at") is None


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
