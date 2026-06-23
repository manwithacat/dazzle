"""Boot fixtures/signing_validation with signing env wired for integration tests.

Uses the same subprocess + temp-file pattern as DazzleLocalServerManager
(test_runtime_e2e.py) to avoid pipe-buffer deadlock and keep startup clean.

``boot_fixture_app`` is a generator used as a pytest fixture — it yields a
``RunningApp`` namedtuple while the subprocess is live, then terminates the
process on teardown.

Requires DATABASE_URL (or TEST_DATABASE_URL) — callers must skip when absent.
"""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from contextlib import closing, suppress
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple

import httpx
import psycopg
import psycopg.rows

from dazzle.qa.signing_seed import SeededDoc, mint_ephemeral_cert_env, write_mock_inbox
from dazzle.signing.tokens import mint_token

if TYPE_CHECKING:
    from collections.abc import Iterator

# ---------------------------------------------------------------------------
# Public namedtuple
# ---------------------------------------------------------------------------

DbReader = Callable[[str, str], "dict[str, Any] | None"]
PdfValidator = Callable[[str], "dict[str, Any]"]


class RunningApp(NamedTuple):
    base_url: str
    seeded_docs: list[SeededDoc]
    db_reader: DbReader
    pdf_validator: PdfValidator
    inbox_path: Path


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _free_port() -> int:
    """Return an available TCP port on localhost."""
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("", 0))
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return s.getsockname()[1]


def _wait_for_health(url: str, timeout: float = 90.0) -> None:
    """Poll GET ``url`` until it returns a non-5xx status or the timeout elapses."""
    deadline = time.monotonic() + timeout
    delay = 0.5
    while time.monotonic() < deadline:
        try:
            r = httpx.get(url, timeout=2.0)
            if r.status_code < 500:
                return
        except httpx.TransportError:
            pass
        time.sleep(delay)
        delay = min(delay * 1.5, 4.0)
    raise TimeoutError(f"App at {url} did not become ready within {timeout}s")


def _wait_for_runtime_json(fixture_dir: Path, timeout: float = 90.0) -> int:
    """Wait for .dazzle/runtime.json and return the port written there.

    Falls back to the port embedded in the Popen command when the file never
    appears (older dazzle versions that do not write the file).
    """
    runtime_file = fixture_dir / ".dazzle" / "runtime.json"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if runtime_file.exists():
            try:
                data = json.loads(runtime_file.read_text())
                return int(data.get("ui_port", data.get("port", 0)))
            except (json.JSONDecodeError, KeyError, ValueError):
                pass
        time.sleep(0.3)
    return 0  # caller falls back to requested port


def _terminate_proc(proc: subprocess.Popen) -> None:  # type: ignore[type-arg]
    """Gracefully terminate a subprocess (SIGTERM then SIGKILL on timeout)."""
    if proc.poll() is not None:
        return  # already dead
    try:
        if sys.platform != "win32":
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        else:
            proc.terminate()
    except (ProcessLookupError, OSError):
        pass
    try:
        proc.wait(timeout=8)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=3)


def _db_reader_for(dsn: str) -> DbReader:
    """Return a synchronous DB-reader closure over *dsn*."""
    from psycopg import sql

    def _read(entity: str, row_id: str) -> dict[str, Any] | None:
        query = sql.SQL("SELECT * FROM {} WHERE id = %s").format(sql.Identifier(entity))
        with psycopg.connect(dsn) as conn:
            with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
                cur.execute(query, (row_id,))  # nosemgrep
                return cur.fetchone()

    return _read


def _presence_only_pdf_validator(path: str) -> dict[str, Any]:
    """Presence-only PDF check.

    Integration tests confirm the signing flow end-to-end; full pyhanko
    cryptographic validation (including timestamp lookup) is covered by
    the unit tests via mocks.  Using presence-only here keeps integration
    tests fast and network-free.
    """
    exists = Path(path).exists() if path else False
    return {
        "valid": exists,
        "summary": "presence-only check (integration test)",
    }


# ---------------------------------------------------------------------------
# Public boot function
# ---------------------------------------------------------------------------


def boot_fixture_app(
    fixture_dir: Path,
    tmp_path: Path,
    *,
    reject_seeded: bool,
) -> Iterator[RunningApp]:
    """Boot fixtures/signing_validation and yield a ``RunningApp``.

    Generator — intended for use as a pytest fixture body::

        @pytest.fixture
        def running_signable_app(tmp_path):
            yield from boot_fixture_app(FIXTURE, tmp_path, reject_seeded=False)

    Skips when no ``DATABASE_URL`` / ``TEST_DATABASE_URL`` is set.

    Boot sequence
    -------------
    1. Mint ephemeral cert + token-secret env vars.
    2. Start ``dazzle serve --local --port <port> --test-mode`` in a subprocess
       with those vars merged into the environment.
    3. Wait for ``/health`` (via the runtime.json port or the requested port).
    4. POST one seed row to ``/api/TestDoc`` to get the row_id.
    5. If *reject_seeded*: terminate, restart with
       ``DAZZLE_QA_SIGNING_REJECT_IDS=<row_id>`` so the validator blocks the sign.
    6. Mint the HMAC token and write the mock inbox.
    7. Yield RunningApp.
    8. finally: terminate subprocess + clean up runtime.json.
    """
    import pytest

    db_url = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not db_url:
        pytest.skip("no TEST_DATABASE_URL / DATABASE_URL — skipping signing integration tests")
    # The sign endpoint renders a PDF (fpdf2) and applies a PKCS#7 signature
    # (pyhanko) — both in the optional `[signing]` extra. Without either, the sign
    # POST 500s and the row never leaves `viewed`, so skip cleanly (mirrors the
    # DATABASE_URL guard) rather than failing with a misleading status assertion on
    # a partial local env. NB: the `fpdf2` distribution imports as the module `fpdf`.
    _signing_hint = "signing extra not installed — pip install dazzle-dsl[signing]"
    pytest.importorskip("fpdf", reason=_signing_hint)
    pytest.importorskip("pyhanko", reason=_signing_hint)

    port = _free_port()
    cert_env = mint_ephemeral_cert_env(tmp_path, project_name="Test Co")

    env: dict[str, str] = {**os.environ, **cert_env}
    env["DATABASE_URL"] = db_url
    env["PYTHONUNBUFFERED"] = "1"
    # Skip the Redis/infra presence check — integration tests run without Redis.
    env["DAZZLE_SKIP_INFRA_CHECK"] = "1"

    # Wipe any stale runtime.json from a previous run so we don't read old port.
    runtime_file = fixture_dir / ".dazzle" / "runtime.json"
    if runtime_file.exists():
        runtime_file.unlink()

    kwargs: dict[str, Any] = {}
    if sys.platform != "win32":
        kwargs["preexec_fn"] = os.setsid

    stdout_f = tempfile.NamedTemporaryFile(
        mode="w", prefix="dazzle-sign-stdout-", suffix=".log", delete=False
    )
    stderr_f = tempfile.NamedTemporaryFile(
        mode="w", prefix="dazzle-sign-stderr-", suffix=".log", delete=False
    )

    def _start_proc(extra_env: dict[str, str] | None = None) -> subprocess.Popen:  # type: ignore[type-arg]
        merged = {**env, **(extra_env or {})}
        # Remove stale runtime.json so wait_for_runtime_json works correctly.
        if runtime_file.exists():
            runtime_file.unlink()
        return subprocess.Popen(
            [
                sys.executable,
                "-m",
                "dazzle",
                "serve",
                "--local",
                "--port",
                str(port),
                "--host",
                "127.0.0.1",
                "--test-mode",
            ],
            cwd=fixture_dir,
            stdout=stdout_f,
            stderr=stderr_f,
            env=merged,
            **kwargs,
        )

    # Pre-generate the row UUID so we can tell the reject-restart process which
    # id to block before the server boots a second time.
    import uuid as _uuid_mod

    row_id: str = str(_uuid_mod.uuid4())

    proc = _start_proc({"DAZZLE_QA_SIGNING_REJECT_IDS": row_id} if reject_seeded else None)
    try:
        # Wait for the server — prefer the runtime.json port (allocated by
        # uvicorn) but fall back to the requested port when the file is absent.
        actual_port = _wait_for_runtime_json(fixture_dir) or port
        base_url = f"http://127.0.0.1:{actual_port}"
        _wait_for_health(f"{base_url}/health")

        # Seed one TestDoc row via /__test__/seed — this endpoint is CSRF-exempt
        # and available whenever --test-mode is active, so no session cookie or
        # CSRF token is needed.  The entity CRUD routes (POST /api/TestDoc) are
        # not CSRF-exempt, so we avoid them here.
        seed_payload: dict[str, Any] = {
            "fixtures": [
                {
                    "id": row_id,
                    "entity": "TestDoc",
                    "data": {
                        "id": row_id,
                        "party": "Trial Counterparty",
                        "body": "Trial-harness seed body.",
                        "signatory_email": "trial@example.com",
                        "status": "sent",
                        # signing_service is injected as required by the linker
                        # for signable: true entities. "native" = Dazzle PDF+PKCS#7.
                        "signing_service": "native",
                    },
                }
            ]
        }
        # When DAZZLE_TEST_SECRET is set in the environment the /__test__/*
        # endpoints require a matching X-Test-Secret header.
        seed_headers: dict[str, str] = {}
        test_secret = os.environ.get("DAZZLE_TEST_SECRET", "")
        if test_secret:
            seed_headers["X-Test-Secret"] = test_secret

        seed_resp = httpx.post(
            f"{base_url}/__test__/seed",
            json=seed_payload,
            headers=seed_headers,
            timeout=15.0,
        )
        if seed_resp.status_code not in (200, 201):
            _terminate_proc(proc)
            stdout_log = Path(stdout_f.name).read_text(errors="replace")[-3000:]
            stderr_log = Path(stderr_f.name).read_text(errors="replace")[-3000:]
            raise RuntimeError(
                f"Seed POST to /__test__/seed failed: HTTP {seed_resp.status_code}\n"
                f"{seed_resp.text}\n\n=== stdout ===\n{stdout_log}\n"
                f"=== stderr ===\n{stderr_log}"
            )

        # Mint token (SIGNING_TOKEN_SECRET is already in os.environ from cert_env
        # because the subprocess inherits a copy — we need to set it locally too
        # so mint_token() can read it).
        os.environ.update(cert_env)
        token = mint_token(record_id=row_id, email="trial@example.com")

        seeded = [
            SeededDoc(
                entity="TestDoc",
                id=row_id,
                token=token,
                signing_url=f"{base_url}/sign/TestDoc/{row_id}?token={token}",
                signatory_email="trial@example.com",
            )
        ]
        inbox_path = write_mock_inbox(tmp_path, seeded)

        yield RunningApp(
            base_url=base_url,
            seeded_docs=seeded,
            db_reader=_db_reader_for(db_url),
            pdf_validator=_presence_only_pdf_validator,
            inbox_path=inbox_path,
        )

    finally:
        _terminate_proc(proc)
        # Clean up temp log files.
        for f in (stdout_f, stderr_f):
            try:
                f.close()
                os.unlink(f.name)
            except OSError:
                pass
        # Remove the runtime.json so subsequent test runs start clean.
        with suppress(OSError):
            if runtime_file.exists():
                runtime_file.unlink()
