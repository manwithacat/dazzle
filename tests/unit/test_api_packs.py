"""Tests for API pack cache TTL and integration template generation."""

from __future__ import annotations

from dazzle.api_kb.loader import ApiPack, AuthSpec, ForeignModelSpec, OperationSpec
from dazzle.core.dsl_parser_impl.process import format_duration

# ---------------------------------------------------------------------------
# format_duration tests
# ---------------------------------------------------------------------------


class TestFormatDuration:
    def test_days(self) -> None:
        assert format_duration(86400) == "1d"

    def test_hours(self) -> None:
        assert format_duration(3600) == "1h"

    def test_24_hours(self) -> None:
        assert format_duration(86400) == "1d"

    def test_minutes(self) -> None:
        assert format_duration(300) == "5m"

    def test_one_minute(self) -> None:
        assert format_duration(60) == "1m"

    def test_seconds(self) -> None:
        assert format_duration(45) == "45s"

    def test_zero(self) -> None:
        assert format_duration(0) == "0s"

    def test_negative(self) -> None:
        assert format_duration(-10) == "0s"

    def test_non_clean_falls_to_seconds(self) -> None:
        # 61 seconds doesn't divide evenly into minutes
        assert format_duration(61) == "61s"


# ---------------------------------------------------------------------------
# generate_integration_template tests
# ---------------------------------------------------------------------------


def _make_pack(
    foreign_models: list[ForeignModelSpec] | None = None,
    operations: list[OperationSpec] | None = None,
) -> ApiPack:
    return ApiPack(
        name="test_pack",
        provider="TestProvider",
        category="testing",
        version="1.0",
        base_url="https://api.test.com",
        auth=AuthSpec(auth_type="api_key", header="X-Key", env_var="TEST_KEY"),
        foreign_models=foreign_models or [],
        operations=operations or [],
    )


class TestGenerateIntegrationTemplate:
    def test_returns_template_with_cache(self) -> None:
        pack = _make_pack(
            foreign_models=[
                ForeignModelSpec(
                    name="Widget",
                    description="A widget",
                    cache_ttl=300,
                    fields={"id": {"type": "int"}},
                ),
            ],
            operations=[
                OperationSpec(
                    name="get_widget",
                    method="GET",
                    path="/widgets/{id}",
                    description="Get a widget",
                ),
            ],
        )
        result = pack.generate_integration_template()
        assert result is not None
        assert 'cache: "5m"' in result
        assert "mapping get_widget:" in result
        assert "entity: Widget" in result

    def test_returns_none_when_no_cacheable_models(self) -> None:
        pack = _make_pack(
            foreign_models=[
                ForeignModelSpec(
                    name="Widget",
                    description="A widget",
                    cache_ttl=None,  # No TTL
                    fields={"id": {"type": "int"}},
                ),
            ],
            operations=[
                OperationSpec(
                    name="get_widget",
                    method="GET",
                    path="/widgets/{id}",
                    description="Get a widget",
                ),
            ],
        )
        assert pack.generate_integration_template() is None

    def test_returns_none_when_no_get_operations(self) -> None:
        pack = _make_pack(
            foreign_models=[
                ForeignModelSpec(
                    name="Widget",
                    description="A widget",
                    cache_ttl=300,
                    fields={"id": {"type": "int"}},
                ),
            ],
            operations=[
                OperationSpec(
                    name="create_widget",
                    method="POST",
                    path="/widgets",
                    description="Create a widget",
                ),
            ],
        )
        assert pack.generate_integration_template() is None

    def test_zero_ttl_renders_as_0s(self) -> None:
        pack = _make_pack(
            foreign_models=[
                ForeignModelSpec(
                    name="Token",
                    description="Access token",
                    cache_ttl=0,
                    fields={"token": {"type": "str"}},
                ),
            ],
            operations=[
                OperationSpec(
                    name="get_token",
                    method="GET",
                    path="/tokens/{id}",
                    description="Get a token",
                ),
            ],
        )
        result = pack.generate_integration_template()
        assert result is not None
        assert 'cache: "0s"' in result

    def test_multiple_models_and_operations(self) -> None:
        pack = _make_pack(
            foreign_models=[
                ForeignModelSpec(
                    name="Company",
                    description="A company",
                    cache_ttl=86400,
                    fields={"id": {"type": "str"}},
                ),
                ForeignModelSpec(
                    name="Officer",
                    description="Company officer",
                    cache_ttl=3600,
                    fields={"id": {"type": "str"}},
                ),
            ],
            operations=[
                OperationSpec(
                    name="get_company",
                    method="GET",
                    path="/company/{id}",
                    description="Get a company",
                ),
                OperationSpec(
                    name="list_officers",
                    method="GET",
                    path="/company/{id}/officers",
                    description="List officers for company",
                ),
            ],
        )
        result = pack.generate_integration_template()
        assert result is not None
        assert 'cache: "1d"' in result
        assert 'cache: "1h"' in result
        assert "mapping get_company:" in result
        assert "mapping list_officers:" in result


# ---------------------------------------------------------------------------
# Pack TOML loading — verify cache_ttl values loaded correctly
# ---------------------------------------------------------------------------


class TestPackCacheTtlLoaded:
    def test_all_packs_load_with_cache_ttl(self) -> None:
        """Verify all pack TOMLs load and every foreign model has cache_ttl."""
        from dazzle.api_kb import list_packs

        packs = list_packs()
        assert len(packs) > 0

        for pack in packs:
            for model in pack.foreign_models:
                assert model.cache_ttl is not None, (
                    f"Pack '{pack.name}' model '{model.name}' missing cache_ttl"
                )
