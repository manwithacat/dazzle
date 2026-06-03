"""Phase 3: the CSRF disposition policy is auditable in the compliance report."""

from dazzle.back.runtime.csrf import CSRFConfig, render_csrf_policy


class TestRenderCsrfPolicy:
    def test_lists_signature_and_preauth_rules_with_dispositions(self) -> None:
        md = "\n".join(render_csrf_policy(CSRFConfig(enabled=True)))
        assert "CSRF" in md
        assert "/webhooks/" in md
        assert "NA_SIGNATURE" in md or "na_signature" in md
        assert "/auth/" in md
        assert "NA_PREAUTH" in md or "na_preauth" in md
        assert "PROTECTED_SESSION" in md or "protected_session" in md

    def test_empty_or_disabled_notice_when_disabled(self) -> None:
        md = render_csrf_policy(CSRFConfig(enabled=False))
        assert md == [] or any("disabled" in line.lower() for line in md)
