"""Tests for API pack infrastructure manifest."""

from __future__ import annotations

from dazzle.api_kb import load_pack
from dazzle.api_kb.loader import (
    DockerSpec,
    InfrastructureSpec,
    SandboxSpec,
)


class TestInfrastructureSchema:
    """Tests for infrastructure dataclasses."""

    def test_docker_spec_defaults(self) -> None:
        ds = DockerSpec(image="nginx:latest")
        assert ds.image == "nginx:latest"
        assert ds.port == 8080
        assert ds.requires == []
        assert ds.environment == {}

    def test_sandbox_spec_defaults(self) -> None:
        ss = SandboxSpec()
        assert ss.available is False
        assert ss.env_prefix == ""

    def test_infrastructure_spec_defaults(self) -> None:
        infra = InfrastructureSpec()
        assert infra.hosting == "cloud_only"
        assert infra.docker is None
        assert infra.sandbox is None


class TestDocusealInfrastructure:
    """Tests for DocuSeal pack infrastructure metadata."""

    def test_docuseal_has_infrastructure(self) -> None:
        pack = load_pack("docuseal_signatures")
        assert pack is not None
        assert pack.infrastructure is not None

    def test_docuseal_hosting_both(self) -> None:
        pack = load_pack("docuseal_signatures")
        assert pack.infrastructure.hosting == "both"

    def test_docuseal_docker_image(self) -> None:
        pack = load_pack("docuseal_signatures")
        docker = pack.infrastructure.docker
        assert docker is not None
        assert docker.image == "docuseal/docuseal:latest"
        assert docker.port == 3000

    def test_docuseal_requires_postgres(self) -> None:
        pack = load_pack("docuseal_signatures")
        assert "postgres" in pack.infrastructure.docker.requires

    def test_docuseal_local_env_overrides(self) -> None:
        pack = load_pack("docuseal_signatures")
        overrides = pack.infrastructure.local_env_overrides
        assert "DOCUSEAL_BASE_URL" in overrides

    def test_docuseal_no_sandbox(self) -> None:
        pack = load_pack("docuseal_signatures")
        assert pack.infrastructure.sandbox is not None
        assert pack.infrastructure.sandbox.available is False


class TestStripeInfrastructure:
    """Tests for Stripe pack infrastructure metadata."""

    def test_stripe_has_infrastructure(self) -> None:
        pack = load_pack("stripe_payments")
        assert pack is not None
        assert pack.infrastructure is not None

    def test_stripe_cloud_only(self) -> None:
        pack = load_pack("stripe_payments")
        assert pack.infrastructure.hosting == "cloud_only"

    def test_stripe_no_docker(self) -> None:
        pack = load_pack("stripe_payments")
        assert pack.infrastructure.docker is None

    def test_stripe_sandbox_available(self) -> None:
        pack = load_pack("stripe_payments")
        assert pack.infrastructure.sandbox is not None
        assert pack.infrastructure.sandbox.available is True
        assert pack.infrastructure.sandbox.env_prefix == "sk_test_"


class TestPacksWithoutInfrastructure:
    """Tests for packs that don't have infrastructure section."""

    def test_companies_house_no_infrastructure(self) -> None:
        pack = load_pack("companies_house_lookup")
        assert pack is not None
        assert pack.infrastructure is None


class TestMcpGetIncludesInfrastructure:
    """Tests that the MCP get handler includes infrastructure data."""

    def test_get_handler_returns_infrastructure(self) -> None:
        import json

        from dazzle.mcp.server.handlers.api_packs import get_api_pack_handler

        result = json.loads(get_api_pack_handler({"pack_name": "docuseal_signatures"}))
        assert "infrastructure" in result
        infra = result["infrastructure"]
        assert infra is not None
        assert infra["hosting"] == "both"
        assert infra["docker"]["image"] == "docuseal/docuseal:latest"

    def test_get_handler_infrastructure_null_when_absent(self) -> None:
        import json

        from dazzle.mcp.server.handlers.api_packs import get_api_pack_handler

        result = json.loads(get_api_pack_handler({"pack_name": "companies_house_lookup"}))
        assert "infrastructure" in result
        assert result["infrastructure"] is None
