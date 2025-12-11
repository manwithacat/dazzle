"""
Unit tests for DAZZLE API Knowledgebase (api_kb).

Tests the pack loader, search functionality, and DSL generation.
"""

import pytest

from dazzle.api_kb import (
    ApiPack,
    EnvVarSpec,
    list_packs,
    load_pack,
    search_packs,
)
from dazzle.api_kb.loader import generate_env_example


class TestPackLoading:
    """Tests for loading API packs."""

    def test_load_stripe_payments_pack(self):
        """Test loading the Stripe payments pack."""
        pack = load_pack("stripe_payments")

        assert pack is not None
        assert pack.name == "stripe_payments"
        assert pack.provider == "Stripe"
        assert pack.category == "payments"

    def test_load_hmrc_mtd_vat_pack(self):
        """Test loading the HMRC MTD VAT pack."""
        pack = load_pack("hmrc_mtd_vat")

        assert pack is not None
        assert pack.name == "hmrc_mtd_vat"
        assert pack.provider == "HMRC"
        assert pack.category == "tax"

    def test_load_companies_house_pack(self):
        """Test loading the Companies House lookup pack."""
        pack = load_pack("companies_house_lookup")

        assert pack is not None
        assert pack.name == "companies_house_lookup"
        assert pack.provider == "Companies House"
        assert pack.category == "business_data"

    def test_load_xero_accounting_pack(self):
        """Test loading the Xero accounting pack."""
        pack = load_pack("xero_accounting")

        assert pack is not None
        assert pack.name == "xero_accounting"
        assert pack.provider == "Xero"
        assert pack.category == "accounting"

    def test_load_nonexistent_pack(self):
        """Test loading a pack that doesn't exist."""
        pack = load_pack("nonexistent_pack")
        assert pack is None

    def test_list_all_packs(self):
        """Test listing all available packs."""
        packs = list_packs()

        assert len(packs) >= 4  # We have at least 4 packs
        pack_names = [p.name for p in packs]
        assert "stripe_payments" in pack_names
        assert "hmrc_mtd_vat" in pack_names
        assert "companies_house_lookup" in pack_names
        assert "xero_accounting" in pack_names


class TestPackSearch:
    """Tests for searching API packs."""

    def test_search_by_category_payments(self):
        """Test searching packs by payments category."""
        packs = search_packs(category="payments")

        assert len(packs) >= 1
        assert all(p.category == "payments" for p in packs)
        assert any(p.name == "stripe_payments" for p in packs)

    def test_search_by_category_tax(self):
        """Test searching packs by tax category."""
        packs = search_packs(category="tax")

        assert len(packs) >= 1
        assert all(p.category == "tax" for p in packs)
        assert any(p.name == "hmrc_mtd_vat" for p in packs)

    def test_search_by_category_accounting(self):
        """Test searching packs by accounting category."""
        packs = search_packs(category="accounting")

        assert len(packs) >= 1
        assert all(p.category == "accounting" for p in packs)

    def test_search_by_provider_stripe(self):
        """Test searching packs by Stripe provider."""
        packs = search_packs(provider="Stripe")

        assert len(packs) >= 1
        assert all(p.provider == "Stripe" for p in packs)

    def test_search_by_provider_hmrc(self):
        """Test searching packs by HMRC provider."""
        packs = search_packs(provider="HMRC")

        assert len(packs) >= 1
        assert all(p.provider == "HMRC" for p in packs)

    def test_search_by_query(self):
        """Test searching packs by text query."""
        packs = search_packs(query="vat")

        assert len(packs) >= 1
        # Should find HMRC MTD VAT
        assert any("vat" in p.name.lower() or "vat" in p.description.lower() for p in packs)

    def test_search_by_query_payment(self):
        """Test searching packs by 'payment' query."""
        packs = search_packs(query="payment")

        assert len(packs) >= 1
        assert any(p.name == "stripe_payments" for p in packs)

    def test_search_no_results(self):
        """Test search with no matching results."""
        packs = search_packs(category="nonexistent_category")
        assert len(packs) == 0

    def test_search_combined_filters(self):
        """Test search with multiple filters."""
        packs = search_packs(category="payments", provider="Stripe")

        assert len(packs) >= 1
        assert all(p.category == "payments" and p.provider == "Stripe" for p in packs)


class TestPackContents:
    """Tests for pack content structure."""

    def test_stripe_pack_has_env_vars(self):
        """Test Stripe pack has required env vars."""
        pack = load_pack("stripe_payments")
        assert pack is not None

        env_var_names = [e.name for e in pack.env_vars]
        assert "STRIPE_SECRET_KEY" in env_var_names
        assert "STRIPE_PUBLISHABLE_KEY" in env_var_names

    def test_stripe_pack_has_operations(self):
        """Test Stripe pack has operations defined."""
        pack = load_pack("stripe_payments")
        assert pack is not None

        op_names = [o.name for o in pack.operations]
        assert "create_payment_intent" in op_names
        assert "get_payment_intent" in op_names
        assert "create_refund" in op_names

    def test_stripe_pack_has_foreign_models(self):
        """Test Stripe pack has foreign models defined."""
        pack = load_pack("stripe_payments")
        assert pack is not None

        model_names = [m.name for m in pack.foreign_models]
        assert "PaymentIntent" in model_names
        assert "Charge" in model_names
        assert "Refund" in model_names

    def test_hmrc_pack_has_oauth2_auth(self):
        """Test HMRC pack has OAuth2 auth configured."""
        pack = load_pack("hmrc_mtd_vat")
        assert pack is not None
        assert pack.auth is not None
        assert pack.auth.auth_type == "oauth2"
        assert pack.auth.token_url is not None

    def test_companies_house_pack_has_api_key_auth(self):
        """Test Companies House pack has API key auth."""
        pack = load_pack("companies_house_lookup")
        assert pack is not None
        assert pack.auth is not None
        assert pack.auth.auth_type == "api_key"

    def test_foreign_model_has_fields(self):
        """Test foreign models have field definitions."""
        pack = load_pack("stripe_payments")
        assert pack is not None

        payment_intent = next((m for m in pack.foreign_models if m.name == "PaymentIntent"), None)
        assert payment_intent is not None
        assert "id" in payment_intent.fields
        assert "amount" in payment_intent.fields
        assert "currency" in payment_intent.fields
        assert "status" in payment_intent.fields


class TestDSLGeneration:
    """Tests for DSL code generation from packs."""

    def test_generate_service_dsl_stripe(self):
        """Test generating DSL service block for Stripe."""
        pack = load_pack("stripe_payments")
        assert pack is not None

        dsl = pack.generate_service_dsl()

        assert 'service stripe' in dsl.lower() or 'service stripepayments' in dsl.lower()
        assert 'pack: stripe_payments' in dsl
        assert 'auth_profile:' in dsl

    def test_generate_service_dsl_hmrc(self):
        """Test generating DSL service block for HMRC."""
        pack = load_pack("hmrc_mtd_vat")
        assert pack is not None

        dsl = pack.generate_service_dsl()

        assert 'service' in dsl.lower()
        assert 'pack: hmrc_mtd_vat' in dsl
        assert 'oauth2' in dsl

    def test_generate_foreign_model_dsl(self):
        """Test generating DSL foreign_model block."""
        pack = load_pack("stripe_payments")
        assert pack is not None

        payment_intent = next((m for m in pack.foreign_models if m.name == "PaymentIntent"), None)
        assert payment_intent is not None

        dsl = pack.generate_foreign_model_dsl(payment_intent)

        assert "foreign_model PaymentIntent" in dsl
        assert "key: id" in dsl
        assert "id:" in dsl
        assert "amount:" in dsl

    def test_auth_profile_api_key(self):
        """Test auth profile DSL for API key auth."""
        pack = load_pack("stripe_payments")
        assert pack is not None
        assert pack.auth is not None

        profile = pack.auth.to_dsl_auth_profile()

        assert "api_key" in profile
        assert 'header="Authorization"' in profile
        assert "STRIPE_SECRET_KEY" in profile

    def test_auth_profile_oauth2(self):
        """Test auth profile DSL for OAuth2 auth."""
        pack = load_pack("hmrc_mtd_vat")
        assert pack is not None
        assert pack.auth is not None

        profile = pack.auth.to_dsl_auth_profile()

        assert "oauth2" in profile
        assert "client_id_env" in profile
        assert "client_secret_env" in profile
        assert "token_url" in profile


class TestEnvExampleGeneration:
    """Tests for .env.example generation."""

    def test_generate_env_example_single_pack(self):
        """Test generating .env.example for a single pack."""
        pack = load_pack("stripe_payments")
        assert pack is not None

        env_example = pack.generate_env_example()

        assert "Stripe" in env_example
        assert "STRIPE_SECRET_KEY" in env_example
        assert "STRIPE_PUBLISHABLE_KEY" in env_example

    def test_generate_env_example_multiple_packs(self):
        """Test generating .env.example for multiple packs."""
        env_example = generate_env_example(["stripe_payments", "hmrc_mtd_vat"])

        assert "Stripe" in env_example
        assert "STRIPE_SECRET_KEY" in env_example
        assert "HMRC" in env_example
        assert "HMRC_CLIENT_ID" in env_example

    def test_env_var_to_example_line(self):
        """Test EnvVarSpec to .env.example line conversion."""
        env_var = EnvVarSpec(
            name="TEST_API_KEY",
            required=True,
            description="Test API key",
            example="test_123",
        )

        line = env_var.to_env_example_line()

        assert "TEST_API_KEY" in line
        assert "test_123" in line
        assert "Test API key" in line


class TestPackDataIntegrity:
    """Tests for pack data integrity and consistency."""

    def test_all_packs_have_required_fields(self):
        """Test all packs have required fields populated."""
        packs = list_packs()

        for pack in packs:
            assert pack.name, f"Pack missing name"
            assert pack.provider, f"Pack {pack.name} missing provider"
            assert pack.category, f"Pack {pack.name} missing category"

    def test_all_packs_have_auth(self):
        """Test all packs have auth configuration."""
        packs = list_packs()

        for pack in packs:
            assert pack.auth is not None, f"Pack {pack.name} missing auth"
            assert pack.auth.auth_type, f"Pack {pack.name} missing auth type"

    def test_all_packs_have_env_vars(self):
        """Test authenticated packs have at least one env var."""
        packs = list_packs()

        for pack in packs:
            # Skip packs with no auth requirement (public APIs)
            if pack.auth and pack.auth.auth_type == "none":
                continue
            assert len(pack.env_vars) > 0, f"Pack {pack.name} has no env vars"

    def test_all_packs_have_operations(self):
        """Test all packs have at least one operation."""
        packs = list_packs()

        for pack in packs:
            assert len(pack.operations) > 0, f"Pack {pack.name} has no operations"

    def test_operation_has_method_and_path(self):
        """Test all operations have method and path."""
        packs = list_packs()

        for pack in packs:
            for op in pack.operations:
                assert op.method, f"Operation {op.name} in {pack.name} missing method"
                assert op.path, f"Operation {op.name} in {pack.name} missing path"
