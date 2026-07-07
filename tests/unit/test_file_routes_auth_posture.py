"""#1551 — the legacy ``/files/*`` surface honours the app's auth posture.

Pre-fix, ``create_file_routes``'s ``require_auth`` parameter was stored
and never enforced, and ``create_static_file_routes`` mounted the whole
uploads directory as anonymous ``StaticFiles`` — every stored byte was
readable by path, and a stored ``text/html`` upload served inline as
origin HTML. The hx-pdf P1 route (``/_dazzle/documents/...``) is the
scope-correct read path; this suite pins the posture floor for the
legacy routes:

- when the app enforces auth (``require_auth_by_default=True``),
  anonymous callers get 401 on every ``/files`` API route and the
  static byte path — exactly where their ``/api`` calls would 401;
- auth-less apps keep anonymous access (posture parity, not a lockout);
- inline rendering is restricted to the viewer-safe safelist — any
  other stored content type serves as ``attachment`` (upload-time
  content types are client-controlled);
- the static path handler refuses traversal outside the uploads root.
"""

import io
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from dazzle.http.runtime.file_routes import (
    create_file_routes,
    create_static_file_routes,
)


def _auth_dep(authenticated: bool):
    async def dep() -> Any:
        return SimpleNamespace(is_authenticated=authenticated) if authenticated else None

    return dep


def _metadata(content_type: str = "application/pdf") -> MagicMock:
    md = MagicMock()
    md.id = "11111111-1111-1111-1111-111111111111"
    md.filename = "doc.bin"
    md.content_type = content_type
    md.size = 4
    md.url = "/files/x/doc.bin"
    md.thumbnail_url = None
    md.created_at = datetime(2026, 1, 1)
    md.entity_name = None
    md.entity_id = None
    md.field_name = None
    return md


def _make_app(
    *,
    require_auth_by_default: bool,
    authenticated: bool,
    stream_content_type: str = "application/pdf",
    files_root: Path | None = None,
) -> FastAPI:
    app = FastAPI()
    file_service = MagicMock()
    md = _metadata(stream_content_type)
    file_service.upload = AsyncMock(return_value=md)
    file_service.get_metadata = MagicMock(return_value=md)
    file_service.download = AsyncMock(return_value=(b"data", md))

    async def _stream():
        yield b"data"

    file_service.stream = AsyncMock(return_value=(_stream(), md))
    file_service.delete = AsyncMock(return_value=True)
    file_service.get_files_for_entity = MagicMock(return_value=[])

    create_file_routes(
        app,
        file_service,
        optional_auth_dep=_auth_dep(authenticated),
        require_auth_by_default=require_auth_by_default,
    )
    if files_root is not None:
        create_static_file_routes(
            app,
            base_path=str(files_root),
            url_prefix="/files",
            optional_auth_dep=_auth_dep(authenticated),
            require_auth_by_default=require_auth_by_default,
        )
    return app


_FID = "11111111-1111-1111-1111-111111111111"


class TestApiPosture:
    def test_anonymous_denied_across_the_api_when_auth_enforced(self) -> None:
        client = TestClient(_make_app(require_auth_by_default=True, authenticated=False))
        assert (
            client.post(
                "/files/upload", files={"file": ("a.pdf", io.BytesIO(b"x"), "application/pdf")}
            ).status_code
            == 401
        )
        assert client.get(f"/files/{_FID}").status_code == 401
        assert client.get(f"/files/{_FID}/download").status_code == 401
        assert client.get(f"/files/{_FID}/stream").status_code == 401
        assert client.get(f"/files/{_FID}/thumbnail").status_code == 401
        assert client.delete(f"/files/{_FID}").status_code == 401
        assert client.get("/files/entity/Task/abc").status_code == 401

    def test_authenticated_caller_allowed(self) -> None:
        client = TestClient(_make_app(require_auth_by_default=True, authenticated=True))
        assert client.get(f"/files/{_FID}").status_code == 200
        assert client.get(f"/files/{_FID}/download").status_code == 200

    def test_authless_app_keeps_anonymous_access(self) -> None:
        client = TestClient(_make_app(require_auth_by_default=False, authenticated=False))
        assert client.get(f"/files/{_FID}").status_code == 200


class TestInlineSafelist:
    def test_stream_serves_unsafe_type_as_attachment_with_nosniff(self) -> None:
        client = TestClient(
            _make_app(
                require_auth_by_default=False,
                authenticated=False,
                stream_content_type="text/html",
            )
        )
        r = client.get(f"/files/{_FID}/stream")
        assert r.status_code == 200
        assert r.headers["content-disposition"].startswith("attachment")
        assert r.headers["x-content-type-options"] == "nosniff"

    def test_stream_keeps_pdf_inline(self) -> None:
        client = TestClient(_make_app(require_auth_by_default=False, authenticated=False))
        r = client.get(f"/files/{_FID}/stream")
        assert r.status_code == 200
        assert r.headers["content-disposition"].startswith("inline")
        assert r.headers["x-content-type-options"] == "nosniff"


class TestStaticPath:
    def test_anonymous_denied_when_auth_enforced(self, tmp_path: Path) -> None:
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "f.pdf").write_bytes(b"%PDF")
        client = TestClient(
            _make_app(require_auth_by_default=True, authenticated=False, files_root=tmp_path)
        )
        assert client.get("/files/sub/f.pdf").status_code == 401

    def test_authenticated_read_serves_bytes(self, tmp_path: Path) -> None:
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "f.pdf").write_bytes(b"%PDF")
        client = TestClient(
            _make_app(require_auth_by_default=True, authenticated=True, files_root=tmp_path)
        )
        r = client.get("/files/sub/f.pdf")
        assert r.status_code == 200
        assert r.content == b"%PDF"
        assert r.headers["x-content-type-options"] == "nosniff"

    def test_html_upload_never_serves_inline(self, tmp_path: Path) -> None:
        # Storage keys are always nested (date-based prefix); a
        # single-segment path would match the /files/{file_id} API
        # route first — same precedence the old StaticFiles mount had.
        (tmp_path / "2026").mkdir()
        (tmp_path / "2026" / "evil.html").write_text("<script>alert(1)</script>")
        (tmp_path / "2026" / "文件.pdf").write_bytes(b"%PDF")
        client = TestClient(
            _make_app(require_auth_by_default=False, authenticated=False, files_root=tmp_path)
        )
        r = client.get("/files/2026/evil.html")
        assert r.status_code == 200
        assert r.headers["content-disposition"].startswith("attachment")
        assert r.headers["x-content-type-options"] == "nosniff"
        # non-latin-1 filenames must not 500 (headers are latin-1;
        # the ASCII fold + filename* pattern from the P1 route)
        r2 = client.get("/files/2026/%E6%96%87%E4%BB%B6.pdf")
        assert r2.status_code == 200
        assert "filename*=UTF-8''" in r2.headers["content-disposition"]

    def test_traversal_outside_root_is_404(self, tmp_path: Path) -> None:
        root = tmp_path / "uploads"
        root.mkdir()
        (tmp_path / "secret.txt").write_text("s3cret")
        client = TestClient(
            _make_app(require_auth_by_default=False, authenticated=False, files_root=root)
        )
        assert client.get("/files/../secret.txt").status_code == 404
        assert client.get("/files/%2e%2e/secret.txt").status_code == 404

    def test_missing_file_is_404(self, tmp_path: Path) -> None:
        client = TestClient(
            _make_app(require_auth_by_default=False, authenticated=False, files_root=tmp_path)
        )
        assert client.get("/files/2026/nope.pdf").status_code == 404
