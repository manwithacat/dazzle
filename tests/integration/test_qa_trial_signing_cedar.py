"""Regression test for #1285: signing seed must use /__test__/seed on Cedar-gated apps.

Boots examples/contact_manager (which has Cedar permit: policies on all surfaces)
and calls the production ``_seed_signable_rows`` directly.  The function must
return at least one SeededDoc — before the fix it got a 403 from /api/EngagementLetter
and raised, causing the trial harness to silently disable signing tools.

Marker: integration (requires DATABASE_URL / TEST_DATABASE_URL).
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
from contextlib import closing, suppress
from pathlib import Path
from typing import Any

import pytest

from dazzle.qa.signing_seed import SeededDoc, mint_ephemeral_cert_env

# One xdist group across both app-booting signing modules. Two hazards when
# boots overlap across workers: (1) each `dazzle serve` writes the booted
# app dir's .dazzle/runtime.json, which boot helpers delete + poll for port
# discovery — concurrent boots of the SAME dir clobber each other; (2)
# _free_port's bind-close-return is a TOCTOU race, so two concurrent booters
# can be handed the same port. Serializing every booter on one worker
# removes both.
pytestmark = [pytest.mark.integration, pytest.mark.xdist_group("signing-fixture-app")]

CONTACT_MANAGER = Path(__file__).resolve().parents[2] / "examples" / "contact_manager"


# ---------------------------------------------------------------------------
# Internal helpers (adapted from signable_runner.py)
# ---------------------------------------------------------------------------


def _free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("", 0))
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return s.getsockname()[1]


def _wait_for_health(url: str, timeout: float = 90.0) -> None:
    import httpx

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


def _wait_for_runtime_json(app_dir: Path, timeout: float = 90.0) -> int:
    runtime_file = app_dir / ".dazzle" / "runtime.json"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if runtime_file.exists():
            try:
                data = json.loads(runtime_file.read_text())
                return int(data.get("ui_port", data.get("port", 0)))
            except (json.JSONDecodeError, KeyError, ValueError):
                pass
        time.sleep(0.3)
    return 0


def _terminate_proc(proc: subprocess.Popen) -> None:  # type: ignore[type-arg]
    if proc.poll() is not None:
        return
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


# ---------------------------------------------------------------------------
# Fixture: booted contact_manager
# ---------------------------------------------------------------------------


@pytest.fixture
def running_contact_manager(tmp_path: Path) -> Any:
    """Boot examples/contact_manager (Cedar-gated) and yield base_url + appspec."""
    db_url = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not db_url:
        pytest.skip("no TEST_DATABASE_URL / DATABASE_URL — skipping Cedar signing regression")

    port = _free_port()
    cert_env = mint_ephemeral_cert_env(tmp_path, project_name="Contact Manager Trial")

    env: dict[str, str] = {**os.environ, **cert_env}
    env["DATABASE_URL"] = db_url
    env["PYTHONUNBUFFERED"] = "1"
    env["DAZZLE_SKIP_INFRA_CHECK"] = "1"

    runtime_file = CONTACT_MANAGER / ".dazzle" / "runtime.json"
    if runtime_file.exists():
        runtime_file.unlink()

    kwargs: dict[str, Any] = {}
    if sys.platform != "win32":
        kwargs["preexec_fn"] = os.setsid

    stdout_f = tempfile.NamedTemporaryFile(
        mode="w", prefix="dazzle-cm-stdout-", suffix=".log", delete=False
    )
    stderr_f = tempfile.NamedTemporaryFile(
        mode="w", prefix="dazzle-cm-stderr-", suffix=".log", delete=False
    )

    proc = subprocess.Popen(
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
        cwd=CONTACT_MANAGER,
        stdout=stdout_f,
        stderr=stderr_f,
        env=env,
        **kwargs,
    )
    try:
        actual_port = _wait_for_runtime_json(CONTACT_MANAGER) or port
        base_url = f"http://127.0.0.1:{actual_port}"
        _wait_for_health(f"{base_url}/health")

        # Load AppSpec for contact_manager so _seed_signable_rows can walk entities.
        from dazzle.cli.utils import load_project_appspec

        app_spec = load_project_appspec(CONTACT_MANAGER)

        # Merge cert_env into os.environ so mint_token() can read SIGNING_TOKEN_SECRET.
        os.environ.update(cert_env)

        yield {
            "base_url": base_url,
            "app_spec": app_spec,
            "test_secret": env.get("DAZZLE_TEST_SECRET", ""),
        }
    finally:
        _terminate_proc(proc)
        for f in (stdout_f, stderr_f):
            with suppress(OSError):
                f.close()
                os.unlink(f.name)
        with suppress(OSError):
            if runtime_file.exists():
                runtime_file.unlink()


# ---------------------------------------------------------------------------
# Regression test
# ---------------------------------------------------------------------------


def test_seed_signable_rows_bypasses_cedar(running_contact_manager: dict) -> None:
    """_seed_signable_rows must return >= 1 SeededDoc on a Cedar-gated app (#1285).

    Before the fix, _insert_seed_row POSTed /api/EngagementLetter which returned
    403 Forbidden (Cedar policy enforcement).  The harness then silently set
    signing_tools_list = [] and the LLM persona ran without signing tools.

    After the fix, /__test__/seed is used instead — it bypasses Cedar — and the
    seed must succeed.
    """
    from dazzle.cli.qa import _seed_signable_rows

    ctx = running_contact_manager
    docs = _seed_signable_rows(
        app_spec=ctx["app_spec"],
        base_url=ctx["base_url"],
        signatory_email="regression-test@example.com",
        test_secret=ctx["test_secret"],
    )

    assert len(docs) >= 1, (
        "Expected at least one SeededDoc — got zero.  "
        "This is the #1285 regression: _seed_signable_rows likely got 403 "
        "from Cedar-gated /api/{entity} instead of using /__test__/seed."
    )
    for doc in docs:
        assert isinstance(doc, SeededDoc)
        assert doc.id, f"SeededDoc for {doc.entity} has empty id"
        assert doc.token, f"SeededDoc for {doc.entity} has empty token"
        assert "EngagementLetter" in doc.signing_url or doc.entity in doc.signing_url
