"""Phase 3: CSRF disposition model (spec §4.1)."""

from dazzle.http.runtime.csrf import (
    CSRFConfig,
    Disposition,
    csrf_admits,
    csrf_disposition,
)


def _h(**kw) -> list[tuple[bytes, bytes]]:
    out = []
    for k, v in kw.items():
        out.append((k.replace("_", "-").encode("latin-1"), v.encode("latin-1")))
    return out


CFG = CSRFConfig(enabled=True)


class TestCsrfDisposition:
    def test_bearer_is_na_bearer(self) -> None:
        d = csrf_disposition("POST", "/anything", _h(authorization="Bearer x"), CFG)
        assert d is Disposition.NA_BEARER

    def test_webhook_is_na_signature(self) -> None:
        d = csrf_disposition("POST", "/webhooks/stripe", _h(), CFG)
        assert d is Disposition.NA_SIGNATURE

    def test_sign_route_is_na_signature(self) -> None:
        path = "/api/sign/contract/12345678-1234-1234-1234-123456789abc"
        d = csrf_disposition("POST", path, _h(), CFG)
        assert d is Disposition.NA_SIGNATURE

    def test_sign_route_non_uuid_tail_is_protected_session(self) -> None:
        # The load-bearing UUID anchor on the sign regex (#1284): a non-UUID
        # tail must NOT derive NA_SIGNATURE — it falls back to CSRF validation.
        d = csrf_disposition("POST", "/api/sign/contract/not-a-uuid", _h(), CFG)
        assert d is Disposition.PROTECTED_SESSION

    def test_auth_prefix_is_na_preauth(self) -> None:
        d = csrf_disposition("POST", "/auth/login", _h(), CFG)
        assert d is Disposition.NA_PREAUTH

    def test_consent_exact_is_na_preauth(self) -> None:
        d = csrf_disposition("POST", "/_dazzle/consent", _h(), CFG)
        assert d is Disposition.NA_PREAUTH

    def test_ordinary_mutating_is_protected_session(self) -> None:
        d = csrf_disposition("POST", "/academicyears", _h(), CFG)
        assert d is Disposition.PROTECTED_SESSION

    def test_bearer_wins_over_signature_path(self) -> None:
        d = csrf_disposition("POST", "/webhooks/x", _h(authorization="Bearer t"), CFG)
        assert d is Disposition.NA_BEARER


class TestCsrfAdmits:
    def test_na_dispositions_admit(self) -> None:
        for d in (Disposition.NA_BEARER, Disposition.NA_SIGNATURE, Disposition.NA_PREAUTH):
            assert csrf_admits(d, _h(host="app.example.com"), "app.example.com", None, CFG) is True

    def test_protected_session_same_origin_admits_without_token(self) -> None:
        ok = csrf_admits(
            Disposition.PROTECTED_SESSION,
            _h(sec_fetch_site="same-origin", host="app.example.com"),
            "app.example.com",
            None,
            CFG,
        )
        assert ok is True

    def test_protected_session_cross_site_rejected_with_token(self) -> None:
        ok = csrf_admits(
            Disposition.PROTECTED_SESSION,
            _h(sec_fetch_site="cross-site", host="app.example.com"),
            "app.example.com",
            "tok",
            CFG,
        )
        assert ok is False

    def test_protected_session_no_signal_token_match_admits(self) -> None:
        ok = csrf_admits(
            Disposition.PROTECTED_SESSION,
            _h(host="app.example.com", x_csrf_token="tok"),
            "app.example.com",
            "tok",
            CFG,
        )
        assert ok is True

    def test_protected_session_no_signal_token_mismatch_rejects(self) -> None:
        ok = csrf_admits(
            Disposition.PROTECTED_SESSION,
            _h(host="app.example.com", x_csrf_token="WRONG"),
            "app.example.com",
            "tok",
            CFG,
        )
        assert ok is False


class TestProtectedPathOverrides:
    """auth Plan 1b: org-context POSTs under /auth/ must be PROTECTED_SESSION,
    not swept into the /auth/ NA_PREAUTH prefix exemption."""

    def test_switch_org_is_protected_session(self) -> None:
        d = csrf_disposition("POST", "/auth/switch-org", _h(), CFG)
        assert d is Disposition.PROTECTED_SESSION

    def test_select_org_is_protected_session(self) -> None:
        d = csrf_disposition("POST", "/auth/select-org", _h(), CFG)
        assert d is Disposition.PROTECTED_SESSION

    def test_other_auth_paths_stay_na_preauth(self) -> None:
        # The override is exact-match — the rest of /auth/ keeps its exemption.
        d = csrf_disposition("POST", "/auth/login/password", _h(), CFG)
        assert d is Disposition.NA_PREAUTH

    def test_switch_org_cross_origin_post_rejected(self) -> None:
        # Cross-site POST (mismatched Origin) → origin gate rejects.
        headers = _h(origin="https://evil.example", host="victim.app")
        assert (
            csrf_admits(Disposition.PROTECTED_SESSION, headers, "victim.app", "tok", CFG) is False
        )

    def test_switch_org_same_origin_post_admitted_without_token(self) -> None:
        # Same-origin form POST (no JS, no X-CSRF-Token header) → origin gate
        # admits via Origin==Host, so the no-JS picker form still works.
        headers = _h(origin="https://victim.app", host="victim.app")
        assert csrf_admits(Disposition.PROTECTED_SESSION, headers, "victim.app", None, CFG) is True
