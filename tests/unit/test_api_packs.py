"""Tests for API pack cache TTL loading."""


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
