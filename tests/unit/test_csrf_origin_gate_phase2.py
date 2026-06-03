"""Phase 2: Sec-Fetch-Site + Origin admission gate (spec §4.2)."""

from dazzle.back.runtime.csrf import CSRFConfig, origin_disposition


def _h(**kw) -> list[tuple[bytes, bytes]]:
    """Build raw ASGI headers from kwargs (underscores -> dashes)."""
    out = []
    for k, v in kw.items():
        out.append((k.replace("_", "-").encode("latin-1"), v.encode("latin-1")))
    return out


CFG = CSRFConfig(enabled=True)
CFG_TRUSTED = CSRFConfig(enabled=True, trusted_origins=["https://embed.partner.com"])


class TestSecFetchSite:
    def test_same_origin_admits(self) -> None:
        assert origin_disposition(_h(sec_fetch_site="same-origin"), "app.example.com", CFG) is True

    def test_none_admits(self) -> None:
        assert origin_disposition(_h(sec_fetch_site="none"), "app.example.com", CFG) is True

    def test_cross_site_rejects(self) -> None:
        assert origin_disposition(_h(sec_fetch_site="cross-site"), "app.example.com", CFG) is False

    def test_same_site_rejects_by_default(self) -> None:
        assert origin_disposition(_h(sec_fetch_site="same-site"), "app.example.com", CFG) is False


class TestOriginVsHost:
    def test_origin_matches_host_admits(self) -> None:
        hdrs = _h(origin="https://app.example.com", host="app.example.com")
        assert origin_disposition(hdrs, "app.example.com", CFG) is True

    def test_origin_matches_host_with_port_admits(self) -> None:
        hdrs = _h(origin="http://localhost:8000", host="localhost:8000")
        assert origin_disposition(hdrs, "localhost:8000", CFG) is True

    def test_origin_differs_from_host_rejects(self) -> None:
        hdrs = _h(origin="https://evil.com", host="app.example.com")
        assert origin_disposition(hdrs, "app.example.com", CFG) is False

    def test_cross_tenant_subdomain_rejects(self) -> None:
        hdrs = _h(origin="https://tenant-b.example.com", host="tenant-a.example.com")
        assert origin_disposition(hdrs, "tenant-a.example.com", CFG) is False

    def test_origin_null_rejects(self) -> None:
        hdrs = _h(origin="null", host="app.example.com")
        assert origin_disposition(hdrs, "app.example.com", CFG) is False


class TestTrustedOrigins:
    def test_trusted_origin_admits_despite_host_mismatch(self) -> None:
        hdrs = _h(origin="https://embed.partner.com", host="app.example.com")
        assert origin_disposition(hdrs, "app.example.com", CFG_TRUSTED) is True

    def test_untrusted_origin_still_rejects(self) -> None:
        hdrs = _h(origin="https://other.partner.com", host="app.example.com")
        assert origin_disposition(hdrs, "app.example.com", CFG_TRUSTED) is False

    def test_same_site_in_trusted_admits(self) -> None:
        hdrs = _h(sec_fetch_site="same-site", origin="https://embed.partner.com")
        assert origin_disposition(hdrs, "app.example.com", CFG_TRUSTED) is True


class TestNoSignalFallsBack:
    def test_no_origin_no_fetch_metadata_returns_none(self) -> None:
        assert origin_disposition(_h(host="app.example.com"), "app.example.com", CFG) is None


class TestFailClosedAndPrecedence:
    def test_unknown_sec_fetch_site_rejects(self) -> None:
        # A garbage/unknown Sec-Fetch-Site value must fail CLOSED (reject), not open.
        assert origin_disposition(_h(sec_fetch_site="bogus"), "app.example.com", CFG) is False

    def test_sec_fetch_site_same_origin_wins_over_mismatched_origin(self) -> None:
        # Both headers present (the real-browser case): the unforgeable
        # Sec-Fetch-Site=same-origin admits even if an Origin header is present
        # and mismatched — Sec-Fetch-Site takes precedence.
        hdrs = _h(sec_fetch_site="same-origin", origin="https://evil.com", host="app.example.com")
        assert origin_disposition(hdrs, "app.example.com", CFG) is True

    def test_sec_fetch_site_cross_site_wins_over_matching_origin(self) -> None:
        # Inverse precedence: Sec-Fetch-Site=cross-site rejects even if the Origin
        # header happens to match the Host (the strong signal wins).
        hdrs = _h(
            sec_fetch_site="cross-site", origin="https://app.example.com", host="app.example.com"
        )
        assert origin_disposition(hdrs, "app.example.com", CFG) is False

    def test_explicit_default_port_origin_does_not_match_bare_host(self) -> None:
        # Browsers omit default ports, so Origin "https://app.example.com" (no :443)
        # matches Host "app.example.com". An explicit :443 is treated as a distinct
        # authority and rejected — documenting the no-normalization behavior.
        hdrs = _h(origin="https://app.example.com:443", host="app.example.com")
        assert origin_disposition(hdrs, "app.example.com", CFG) is False
