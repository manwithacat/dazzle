"""Phase 2: csrf_trusted_origins threads ServerConfig -> CSRFConfig."""

from dazzle.http.runtime.csrf import configure_csrf_for_profile


class TestConfigThreading:
    def test_extra_trusted_origins_merged(self) -> None:
        cfg = configure_csrf_for_profile(
            "standard", extra_trusted_origins=["https://embed.partner.com"]
        )
        assert "https://embed.partner.com" in cfg.trusted_origins

    def test_no_extra_trusted_origins_is_empty(self) -> None:
        cfg = configure_csrf_for_profile("standard")
        assert cfg.trusted_origins == []

    def test_extra_trusted_origins_dedupes(self) -> None:
        cfg = configure_csrf_for_profile(
            "standard", extra_trusted_origins=["https://a.com", "https://a.com"]
        )
        assert cfg.trusted_origins.count("https://a.com") == 1
