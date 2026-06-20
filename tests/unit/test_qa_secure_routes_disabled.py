"""qa_secure_routes is self-disabling without QA_AUTH_SECRET (Phase E.2)."""

from dazzle.http.runtime.qa_secure_routes import create_qa_secure_routes


def test_router_is_none_without_secret(monkeypatch) -> None:
    monkeypatch.delenv("QA_AUTH_SECRET", raising=False)
    assert create_qa_secure_routes() is None


def test_router_built_with_secret(monkeypatch) -> None:
    monkeypatch.setenv("QA_AUTH_SECRET", "s3cr3t")
    router = create_qa_secure_routes()
    assert router is not None
    assert any(getattr(r, "path", None) == "/qa/secure/mint" for r in router.routes)
