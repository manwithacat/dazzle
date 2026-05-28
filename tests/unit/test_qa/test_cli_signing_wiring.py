"""Unit tests for the signing-env provisioning helpers wired into qa_trial."""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

from dazzle.cli.qa import _provision_signing_env, _seed_signable_rows


def test_provision_returns_context_when_signable(tmp_path: Path):
    app_spec = MagicMock()
    app_spec.has_signable_entity.return_value = True
    with patch("dazzle.cli.qa.mint_ephemeral_cert_env") as mint:
        mint.return_value = {
            "SIGNING_CERT_PFX_B64": "x",
            "SIGNING_CERT_PASSWORD": "y",
            "SIGNING_TOKEN_SECRET": "z",
        }
        ctx = _provision_signing_env(app_spec, tmp_path, project_name="Test")
    assert ctx is not None
    assert ctx.env["SIGNING_TOKEN_SECRET"] == "z"


def test_provision_returns_none_when_no_signable(tmp_path: Path):
    app_spec = MagicMock()
    app_spec.has_signable_entity.return_value = False
    assert _provision_signing_env(app_spec, tmp_path, project_name="Test") is None


def test_seed_creates_one_doc_per_signable_entity():
    entity_a = MagicMock(signable=True)
    entity_a.name = "EngagementLetter"
    # No required REF fields on the mock entity (fields list is empty).
    entity_a.fields = []
    entity_b = MagicMock(signable=False)
    app_spec = MagicMock()
    app_spec.domain.entities = [entity_a, entity_b]

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"created": {"signable_row": {"id": "row-id-1"}}}

    with (
        patch("dazzle.cli.qa.mint_token", return_value="tok-abc"),
        patch("httpx.post", return_value=mock_response) as mock_post,
        patch.dict(os.environ, {"SIGNING_TOKEN_SECRET": "s"}),
    ):
        docs = _seed_signable_rows(
            app_spec=app_spec,
            base_url="http://localhost:3000",
            signatory_email="a@b.com",
            test_secret="dummy",
        )
    assert len(docs) == 1
    assert docs[0].entity == "EngagementLetter"
    assert docs[0].token == "tok-abc"
    # Verify that /__test__/seed was used (not Cedar-gated /api/{entity})
    call_url = mock_post.call_args[0][0]
    assert "/__test__/seed" in call_url, f"Expected /__test__/seed but got: {call_url}"
