"""Tests for dazzle tenant CLI commands."""

from unittest.mock import MagicMock, patch

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


class TestTenantSuspend:
    @patch("dazzle.cli.tenant._get_registry")
    @patch("dazzle.cli.tenant._check_tenant_enabled")
    def test_suspend_tenant(self, mock_check: MagicMock, mock_reg: MagicMock) -> None:
        registry = MagicMock()
        registry.update_status.return_value = MagicMock(slug="cyfuture", status="suspended")
        mock_reg.return_value = registry

        result = runner.invoke(tenant_app, ["suspend", "cyfuture"])
        assert result.exit_code == 0
        registry.update_status.assert_called_once_with("cyfuture", "suspended")

    @patch("dazzle.cli.tenant._get_registry")
    @patch("dazzle.cli.tenant._check_tenant_enabled")
    def test_suspend_not_found(self, mock_check: MagicMock, mock_reg: MagicMock) -> None:
        registry = MagicMock()
        registry.update_status.side_effect = ValueError("Tenant 'unknown' not found")
        mock_reg.return_value = registry

        result = runner.invoke(tenant_app, ["suspend", "unknown"])
        assert result.exit_code == 1
        assert "not found" in result.output


class TestTenantActivate:
    @patch("dazzle.cli.tenant._get_registry")
    @patch("dazzle.cli.tenant._check_tenant_enabled")
    def test_activate_tenant(self, mock_check: MagicMock, mock_reg: MagicMock) -> None:
        registry = MagicMock()
        registry.update_status.return_value = MagicMock(slug="cyfuture", status="active")
        mock_reg.return_value = registry

        result = runner.invoke(tenant_app, ["activate", "cyfuture"])
        assert result.exit_code == 0
        registry.update_status.assert_called_once_with("cyfuture", "active")

    @patch("dazzle.cli.tenant._get_registry")
    @patch("dazzle.cli.tenant._check_tenant_enabled")
    def test_activate_not_found(self, mock_check: MagicMock, mock_reg: MagicMock) -> None:
        registry = MagicMock()
        registry.update_status.side_effect = ValueError("Tenant 'unknown' not found")
        mock_reg.return_value = registry

        result = runner.invoke(tenant_app, ["activate", "unknown"])
        assert result.exit_code == 1
        assert "not found" in result.output
