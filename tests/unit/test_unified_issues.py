"""Unit tests for unified issues view."""

import json
import tempfile
from pathlib import Path


class TestUnifiedIssues:
    """Tests for the unified issues handler."""

    def test_extract_issue_key_with_entity_and_field(self) -> None:
        """Test extracting entity.field key from lint message."""
        from dazzle.mcp.server.handlers.dsl import _extract_issue_key

        msg = "Entity 'Order' field 'amount' should have currency specified"
        key = _extract_issue_key(msg)
        assert key == "Order.amount"

    def test_extract_issue_key_with_entity_only(self) -> None:
        """Test extracting entity key when no field is mentioned."""
        from dazzle.mcp.server.handlers.dsl import _extract_issue_key

        msg = "Entity 'Customer' has no primary key defined"
        key = _extract_issue_key(msg)
        assert key == "Customer"

    def test_extract_issue_key_fallback(self) -> None:
        """Test fallback to message when no entity pattern found."""
        from dazzle.mcp.server.handlers.dsl import _extract_issue_key

        msg = "Missing required configuration"
        key = _extract_issue_key(msg)
        assert key == msg

    def test_extract_issue_key_truncates_long_messages(self) -> None:
        """Test that long messages are truncated as keys."""
        from dazzle.mcp.server.handlers.dsl import _extract_issue_key

        msg = "A" * 100  # 100 character message
        key = _extract_issue_key(msg)
        assert len(key) == 80

    def test_unified_issues_returns_valid_json(self) -> None:
        """Test that unified issues returns valid JSON structure."""
        from dazzle.mcp.server.handlers.dsl import get_unified_issues

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create minimal project structure
            (project_root / "dsl").mkdir()
            (project_root / "dazzle.toml").write_text(
                '[project]\nname = "test"\nroot = "test_app"\n\n[modules]\npaths = ["dsl"]'
            )
            (project_root / "dsl" / "main.dsl").write_text(
                'module test_app\n\napp test "Test App"\n\n'
                'entity Order "Order":\n'
                "  id: uuid pk\n"
                "  amount: int\n"
                "  customer_email: str(200)\n"
            )

            result = get_unified_issues(project_root, {})
            data = json.loads(result)

            # Should have valid structure
            assert "total_issues" in data
            assert "issues" in data
            assert "cross_references" in data
            assert isinstance(data["issues"], list)

    def test_unified_issues_detects_compliance_findings(self) -> None:
        """Test that compliance findings are included."""
        from dazzle.mcp.server.handlers.dsl import get_unified_issues

        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            (project_root / "dsl").mkdir()
            (project_root / "dazzle.toml").write_text(
                '[project]\nname = "test"\nroot = "test_app"\n\n[modules]\npaths = ["dsl"]'
            )
            (project_root / "dsl" / "main.dsl").write_text(
                'module test_app\n\napp test "Test App"\n\n'
                'entity Customer "Customer":\n'
                "  id: uuid pk\n"
                "  email: str(200)\n"
                "  phone: str(50)\n"
            )

            result = get_unified_issues(project_root, {})
            data = json.loads(result)

            # Should detect PII fields
            assert data["compliance_findings"] > 0
            assert "GDPR" in data["recommended_frameworks"]

            # Should have issues for email and phone
            issue_keys = [i["key"] for i in data["issues"]]
            assert "Customer.email" in issue_keys
            assert "Customer.phone" in issue_keys
