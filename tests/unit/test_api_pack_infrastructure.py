"""Tests for API pack infrastructure manifest."""

from dazzle.api_kb import load_pack
from dazzle.api_kb.loader import (
    InfrastructureSpec,
    SandboxSpec,
)


class TestInfrastructureSchema:
    """Tests for infrastructure dataclasses."""

    def test_sandbox_spec_defaults(self) -> None:
        ss = SandboxSpec()
        assert ss.available is False
        assert ss.env_prefix == ""

    def test_infrastructure_spec_defaults(self) -> None:
        infra = InfrastructureSpec()
        assert infra.hosting == "cloud_only"
        assert infra.sandbox is None


class TestStripeInfrastructure:
    """Tests for Stripe pack infrastructure metadata."""

    def test_stripe_has_infrastructure(self) -> None:
        pack = load_pack("stripe_payments")
        assert pack is not None
        assert pack.infrastructure is not None

    def test_stripe_cloud_only(self) -> None:
        pack = load_pack("stripe_payments")
        assert pack.infrastructure.hosting == "cloud_only"

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
