"""Tests for dazzle tenant CLI commands."""

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from dazzle.cli.tenant import tenant_app

runner = CliRunner()


class TestTenantCreate:
    @patch("dazzle.cli.tenant._get_provisioner")
    @patch("dazzle.cli.tenant._get_registry")
    @patch("dazzle.cli.tenant._check_tenant_enabled")
    def test_create_success(
        self, mock_check: MagicMock, mock_reg: MagicMock, mock_prov: MagicMock
    ) -> None:
        registry = MagicMock()
        registry.create.return_value = MagicMock(
            slug="cyfuture",
            display_name="CyFuture UK",
            schema_name="tenant_cyfuture",
            status="active",
        )
        mock_reg.return_value = registry
        provisioner = MagicMock()
        mock_prov.return_value = provisioner

        result = runner.invoke(tenant_app, ["create", "cyfuture", "--display-name", "CyFuture UK"])
        assert result.exit_code == 0
        assert "cyfuture" in result.output
        registry.ensure_table.assert_called_once()
        registry.create.assert_called_once_with("cyfuture", "CyFuture UK")
        provisioner.provision.assert_called_once_with("tenant_cyfuture")

    @patch("dazzle.cli.tenant._get_provisioner")
    @patch("dazzle.cli.tenant._get_registry")
    @patch("dazzle.cli.tenant._check_tenant_enabled")
    def test_create_registry_failure(
        self, mock_check: MagicMock, mock_reg: MagicMock, mock_prov: MagicMock
    ) -> None:
        registry = MagicMock()
        registry.create.side_effect = Exception("duplicate slug")
        mock_reg.return_value = registry
        mock_prov.return_value = MagicMock()

        result = runner.invoke(tenant_app, ["create", "cyfuture", "--display-name", "CyFuture UK"])
        assert result.exit_code == 1
        assert "Failed to create tenant" in result.output

    @patch("dazzle.cli.tenant._get_provisioner")
    @patch("dazzle.cli.tenant._get_registry")
    @patch("dazzle.cli.tenant._check_tenant_enabled")
    def test_create_provisioner_failure(
        self, mock_check: MagicMock, mock_reg: MagicMock, mock_prov: MagicMock
    ) -> None:
        registry = MagicMock()
        registry.create.return_value = MagicMock(
            slug="cyfuture",
            display_name="CyFuture UK",
            schema_name="tenant_cyfuture",
            status="active",
        )
        mock_reg.return_value = registry
        provisioner = MagicMock()
        provisioner.provision.side_effect = Exception("DB error")
        mock_prov.return_value = provisioner

        result = runner.invoke(tenant_app, ["create", "cyfuture", "--display-name", "CyFuture UK"])
        assert result.exit_code == 1
        assert "Schema provisioning failed" in result.output


class TestTenantList:
    @patch("dazzle.cli.tenant._get_registry")
    @patch("dazzle.cli.tenant._check_tenant_enabled")
    def test_list_tenants(self, mock_check: MagicMock, mock_reg: MagicMock) -> None:
        registry = MagicMock()
        registry.list.return_value = [
            MagicMock(
                slug="cyfuture",
                display_name="CyFuture UK",
                schema_name="tenant_cyfuture",
                status="active",
            ),
        ]
        mock_reg.return_value = registry

        result = runner.invoke(tenant_app, ["list"])
        assert result.exit_code == 0
        assert "cyfuture" in result.output

    @patch("dazzle.cli.tenant._get_registry")
    @patch("dazzle.cli.tenant._check_tenant_enabled")
    def test_list_empty(self, mock_check: MagicMock, mock_reg: MagicMock) -> None:
        registry = MagicMock()
        registry.list.return_value = []
        mock_reg.return_value = registry

        result = runner.invoke(tenant_app, ["list"])
        assert result.exit_code == 0
        assert "No tenants found" in result.output


class TestTenantStatus:
    @patch("dazzle.cli.tenant._get_registry")
    @patch("dazzle.cli.tenant._check_tenant_enabled")
    def test_status_found(self, mock_check: MagicMock, mock_reg: MagicMock) -> None:
        registry = MagicMock()
        registry.get.return_value = MagicMock(
            slug="cyfuture",
            display_name="CyFuture UK",
            schema_name="tenant_cyfuture",
            status="active",
            created_at="2026-01-01T00:00:00",
            updated_at="2026-01-02T00:00:00",
        )
        mock_reg.return_value = registry

        result = runner.invoke(tenant_app, ["status", "cyfuture"])
        assert result.exit_code == 0
        assert "cyfuture" in result.output
        assert "tenant_cyfuture" in result.output

    @patch("dazzle.cli.tenant._get_registry")
    @patch("dazzle.cli.tenant._check_tenant_enabled")
    def test_status_not_found(self, mock_check: MagicMock, mock_reg: MagicMock) -> None:
        registry = MagicMock()
        registry.get.return_value = None
        mock_reg.return_value = registry

        result = runner.invoke(tenant_app, ["status", "unknown"])
        assert result.exit_code == 1
        assert "not found" in result.output


class TestTenantStatusTransition:
    """Both `tenant suspend` and `tenant activate` go through the same
    update_status call — happy path forwards the new status, missing tenant
    raises ValueError surfaced as 'not found'."""

    @pytest.mark.parametrize(
        "action,status",
        [("suspend", "suspended"), ("activate", "active")],
        ids=["test_suspend_tenant", "test_activate_tenant"],
    )
    @patch("dazzle.cli.tenant._get_registry")
    @patch("dazzle.cli.tenant._check_tenant_enabled")
    def test_status_transition_happy(
        self,
        mock_check: MagicMock,
        mock_reg: MagicMock,
        action: str,
        status: str,
    ) -> None:
        registry = MagicMock()
        registry.update_status.return_value = MagicMock(slug="cyfuture", status=status)
        mock_reg.return_value = registry

        result = runner.invoke(tenant_app, [action, "cyfuture"])
        assert result.exit_code == 0
        registry.update_status.assert_called_once_with("cyfuture", status)

    @pytest.mark.parametrize(
        "action",
        ["suspend", "activate"],
        ids=["test_suspend_not_found", "test_activate_not_found"],
    )
    @patch("dazzle.cli.tenant._get_registry")
    @patch("dazzle.cli.tenant._check_tenant_enabled")
    def test_status_transition_missing(
        self, mock_check: MagicMock, mock_reg: MagicMock, action: str
    ) -> None:
        registry = MagicMock()
        registry.update_status.side_effect = ValueError("Tenant 'unknown' not found")
        mock_reg.return_value = registry

        result = runner.invoke(tenant_app, [action, "unknown"])
        assert result.exit_code == 1
        assert "not found" in result.output


class TestTenantAliasCli:
    @patch("dazzle.cli.tenant_alias._connect")
    @patch("dazzle.cli.tenant_alias._alias_context")
    def test_claim_prints_txt_challenge(self, mock_ctx: MagicMock, mock_connect: MagicMock) -> None:
        from uuid import uuid4

        from dazzle.http.runtime.tenant.aliases import AliasRow, txt_name, txt_value

        mock_ctx.return_value = (None, "postgresql://localhost/db", "example.com", ())
        conn = MagicMock()
        mock_connect.return_value.__enter__.return_value = conn
        row = AliasRow(
            id=uuid4(),
            tenant_id="t1",
            hostname="app.customer.com",
            state="pending_txt",
            txt_token="tok",
            cname_target="customers.example.com",
        )
        with patch("dazzle.cli.tenant_alias.claim", return_value=row):
            result = runner.invoke(
                tenant_app,
                [
                    "alias",
                    "claim",
                    "t1",
                    "app.customer.com",
                    "--cname-target",
                    "customers.example.com",
                ],
            )
        assert result.exit_code == 0, result.output
        assert "app.customer.com" in result.output
        assert txt_name("app.customer.com") in result.output
        assert txt_value("tok") in result.output
        assert "verify-domain" not in result.output

    @patch("dazzle.cli.tenant_alias._connect")
    @patch("dazzle.cli.tenant_alias._alias_context")
    def test_show_verification(self, mock_ctx: MagicMock, mock_connect: MagicMock) -> None:
        from uuid import uuid4

        from dazzle.http.runtime.tenant.aliases import AliasRow

        mock_ctx.return_value = (None, "postgresql://localhost/db", "example.com", ())
        conn = MagicMock()
        mock_connect.return_value.__enter__.return_value = conn
        row = AliasRow(
            id=uuid4(),
            tenant_id="t1",
            hostname="app.customer.com",
            state="pending_txt",
            txt_token="tok",
            cname_target="customers.example.com",
        )
        with patch("dazzle.cli.tenant_alias.AliasStore") as store_cls:
            store_cls.return_value.get_by_hostname.return_value = row
            result = runner.invoke(tenant_app, ["alias", "show-verification", "app.customer.com"])
        assert result.exit_code == 0, result.output
        assert "dazzle-verify=tok" in result.output
        assert "_dazzle-challenge.app.customer.com" in result.output
