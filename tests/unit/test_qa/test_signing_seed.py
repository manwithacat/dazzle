"""Tests for dazzle.qa.signing_seed — ephemeral cert + mock inbox provisioning."""

import json
from pathlib import Path

from dazzle.qa.signing_seed import (
    SeededDoc,
    SigningSeedContext,
    mint_ephemeral_cert_env,
    write_mock_inbox,
)


def test_mint_ephemeral_cert_env_sets_three_vars(tmp_path: Path):
    env = mint_ephemeral_cert_env(tmp_path, project_name="Test Co")
    assert env["SIGNING_CERT_PFX_B64"]
    assert env["SIGNING_CERT_PASSWORD"]
    assert env["SIGNING_TOKEN_SECRET"]


def test_write_mock_inbox_dumps_seeded_docs(tmp_path: Path):
    docs = [
        SeededDoc(
            entity="TestDoc",
            id="abc-123",
            token="tok-xyz",
            signing_url="http://localhost:3000/sign/TestDoc/abc-123?token=tok-xyz",
            signatory_email="a@b.com",
        )
    ]
    inbox_path = write_mock_inbox(tmp_path, docs)
    payload = json.loads(inbox_path.read_text())
    assert payload[0]["entity"] == "TestDoc"
    assert payload[0]["signing_url"].startswith("http://")


def test_seed_context_is_a_dataclass(tmp_path: Path):
    ctx = SigningSeedContext(env={"X": "Y"}, inbox_path=tmp_path / "inbox.json", seeded_docs=[])
    assert ctx.env == {"X": "Y"}
