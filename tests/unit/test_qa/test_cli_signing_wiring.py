"""Unit tests for the signing-env provisioning helpers wired into qa_trial."""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

from dazzle.cli.qa import (
    _REALISTIC_SEED_OVERRIDES,
    _build_signing_seed_batch,
    _minimal_fields_for,
    _provision_signing_env,
    _seed_signable_rows,
)
from dazzle.core.ir.fields import FieldModifier, FieldTypeKind


def _make_field(name: str, kind: FieldTypeKind, *modifiers: FieldModifier) -> MagicMock:
    """Return a MagicMock that looks like a FieldSpec with the given type/modifiers."""
    field = MagicMock()
    field.name = name
    field.type = MagicMock()
    field.type.kind = kind
    field.type.enum_values = []
    field.modifiers = list(modifiers)
    return field


def _make_entity(name: str, *fields: MagicMock) -> MagicMock:
    """Return a MagicMock that looks like an EntitySpec."""
    entity = MagicMock()
    entity.name = name
    entity.fields = list(fields)
    return entity


def test_provision_returns_context_when_signable(tmp_path: Path):
    app_spec = MagicMock()
    app_spec.has_signable_entity.return_value = True
    with (
        patch("dazzle.cli.qa._missing_signing_server_deps", return_value=[]),
        patch("dazzle.cli.qa.mint_ephemeral_cert_env") as mint,
    ):
        mint.return_value = {
            "SIGNING_CERT_PFX_B64": "x",
            "SIGNING_CERT_PASSWORD": "y",
            "SIGNING_TOKEN_SECRET": "z",
        }
        ctx = _provision_signing_env(app_spec, tmp_path, project_name="Test")
    assert ctx is not None
    assert ctx.env["SIGNING_TOKEN_SECRET"] == "z"


def _signable_app_spec(*names: str) -> MagicMock:
    """An app_spec whose domain.entities are signable entities with the given names."""
    entities = []
    for n in names:
        ent = MagicMock(signable=True)
        ent.name = n
        ent.fields = []
        entities.append(ent)
    app_spec = MagicMock()
    app_spec.has_signable_entity.return_value = bool(entities)
    app_spec.domain.entities = entities
    return app_spec


def test_provision_arms_reject_env_with_pregenerated_ids(tmp_path: Path):
    """#1382: validator_reject pre-generates a UUID per signable entity, arms
    DAZZLE_QA_SIGNING_REJECT_IDS with them, and records them in signable_ids
    so the seed can insert the row under the armed id."""
    app_spec = _signable_app_spec("SlaWaiver")
    with (
        patch("dazzle.cli.qa._missing_signing_server_deps", return_value=[]),
        patch("dazzle.cli.qa.mint_ephemeral_cert_env", return_value={"SIGNING_TOKEN_SECRET": "z"}),
    ):
        ctx = _provision_signing_env(app_spec, tmp_path, project_name="Test", validator_reject=True)
    assert ctx is not None
    assert ctx.validator_reject is True
    assert set(ctx.signable_ids) == {"SlaWaiver"}
    armed = ctx.env["DAZZLE_QA_SIGNING_REJECT_IDS"].split(",")
    assert armed == [ctx.signable_ids["SlaWaiver"]]


def test_provision_does_not_arm_reject_env_by_default(tmp_path: Path):
    """Without validator_reject the env var is never set — fresh scenarios and
    the existing token-state scenarios are unaffected."""
    app_spec = _signable_app_spec("SlaWaiver")
    with (
        patch("dazzle.cli.qa._missing_signing_server_deps", return_value=[]),
        patch("dazzle.cli.qa.mint_ephemeral_cert_env", return_value={"SIGNING_TOKEN_SECRET": "z"}),
    ):
        ctx = _provision_signing_env(app_spec, tmp_path, project_name="Test")
    assert ctx is not None
    assert ctx.validator_reject is False
    assert "DAZZLE_QA_SIGNING_REJECT_IDS" not in ctx.env
    # ids are still pre-generated (harmless), just not armed.
    assert set(ctx.signable_ids) == {"SlaWaiver"}


def test_build_batch_pins_signable_id_when_given():
    """#1382: an explicit signable_id is written into the signable row's
    data['id'] so the inserted row carries the armed UUID."""
    entity = MagicMock(signable=True)
    entity.name = "SlaWaiver"
    entity.fields = []
    app_spec = MagicMock()
    app_spec.domain.entities = [entity]

    batch = _build_signing_seed_batch(
        entity, app_spec, "a@b.com", signable_id="11111111-1111-1111-1111-111111111111"
    )
    signable_fixture = next(f for f in batch if f["id"] == "signable_row")
    assert signable_fixture["data"]["id"] == "11111111-1111-1111-1111-111111111111"


def test_seed_uses_pregenerated_id_and_stamps_validator_reject():
    """#1382: _seed_signable_rows posts the pre-generated id and stamps the
    SeededDoc so the verifier expects a validator rejection."""
    entity = MagicMock(signable=True)
    entity.name = "SlaWaiver"
    entity.fields = []
    app_spec = MagicMock()
    app_spec.domain.entities = [entity]
    pre_id = "22222222-2222-2222-2222-222222222222"

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"created": {"signable_row": {"id": pre_id}}}

    with (
        patch("dazzle.cli.qa.mint_token", return_value="tok-abc"),
        patch("httpx.post", return_value=mock_response) as mock_post,
        patch.dict(os.environ, {"SIGNING_TOKEN_SECRET": "s"}),
    ):
        docs = _seed_signable_rows(
            app_spec=app_spec,
            base_url="http://localhost:3000",
            signatory_email="a@b.com",
            signable_ids={"SlaWaiver": pre_id},
            validator_reject=True,
        )
    # The posted fixture carried the pre-generated id.
    posted = mock_post.call_args.kwargs["json"]["fixtures"]
    signable_fixture = next(f for f in posted if f["id"] == "signable_row")
    assert signable_fixture["data"]["id"] == pre_id
    # The SeededDoc is stamped so the verifier fixes the expectation.
    assert len(docs) == 1
    assert docs[0].id == pre_id
    assert docs[0].validator_reject is True


def test_provision_returns_none_when_no_signable(tmp_path: Path):
    app_spec = MagicMock()
    app_spec.has_signable_entity.return_value = False
    assert _provision_signing_env(app_spec, tmp_path, project_name="Test") is None


def test_provision_aborts_when_signing_server_deps_missing(tmp_path: Path):
    """#1377: provisioning the signing rig without fpdf2/pyhanko burned a
    full persona run into a guaranteed sign_document HTTP 500. The
    preflight must exit 2 with the install hint instead."""
    import pytest
    import typer

    app_spec = MagicMock()
    app_spec.has_signable_entity.return_value = True
    with patch("dazzle.cli.qa._missing_signing_server_deps", return_value=["fpdf", "pyhanko"]):
        with pytest.raises(typer.Exit) as exc:
            _provision_signing_env(app_spec, tmp_path, project_name="Test")
    assert exc.value.exit_code == 2


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
    assert docs[0].token_state == "fresh"
    # Verify that /__test__/seed was used (not Cedar-gated /api/{entity})
    call_url = mock_post.call_args[0][0]
    assert "/__test__/seed" in call_url, f"Expected /__test__/seed but got: {call_url}"


def test_seed_expired_token_state_mints_already_expired(tmp_path: Path):
    """TR-51: token_state='expired' must mint a token whose expiry is in
    the past (negative expires_hours) and stamp the SeededDoc so the
    verifier expects the row to stay untouched."""
    entity = MagicMock(signable=True)
    entity.name = "SlaWaiver"
    entity.fields = []
    app_spec = MagicMock()
    app_spec.domain.entities = [entity]

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"created": {"signable_row": {"id": "row-id-2"}}}

    with (
        patch("dazzle.cli.qa.mint_token", return_value="tok-expired") as mint,
        patch("httpx.post", return_value=mock_response),
        patch.dict(os.environ, {"SIGNING_TOKEN_SECRET": "s"}),
    ):
        docs = _seed_signable_rows(
            app_spec=app_spec,
            base_url="http://localhost:3000",
            signatory_email="a@b.com",
            token_state="expired",
        )
    assert docs[0].token_state == "expired"
    assert mint.call_args.kwargs["expires_hours"] < 0


def test_expired_token_actually_fails_verification(tmp_path: Path):
    """End-to-end at the token layer: a token minted with negative
    expires_hours must be rejected by verify_token as expired."""
    import pytest

    from dazzle.signing.tokens import InvalidTokenError, mint_token, verify_token

    with patch.dict(os.environ, {"SIGNING_TOKEN_SECRET": "test-secret"}):
        token = mint_token("row-1", "a@b.com", expires_hours=-1)
        with pytest.raises(InvalidTokenError, match="expired"):
            verify_token(token)


# ---------------------------------------------------------------------------
# Tests for _REALISTIC_SEED_OVERRIDES and the _minimal_fields_for merge logic
# ---------------------------------------------------------------------------


def test_minimal_fields_for_uses_realistic_overrides_when_present():
    """EngagementLetter.party should resolve to the realistic override, not 'Trial parent'."""
    party_field = _make_field("party", FieldTypeKind.STR, FieldModifier.REQUIRED)
    scope_field = _make_field("scope_summary", FieldTypeKind.TEXT, FieldModifier.REQUIRED)
    entity = _make_entity("EngagementLetter", party_field, scope_field)

    data = _minimal_fields_for(entity)

    assert data["party"] == "Northwind Apparel Ltd"
    assert "Q4 brand refresh" in data["scope_summary"]


def test_minimal_fields_for_fallback_for_unknown_entity():
    """An entity with no override falls back to generic placeholders."""
    title_field = _make_field("title", FieldTypeKind.STR, FieldModifier.REQUIRED)
    entity = _make_entity("UnknownEntity", title_field)

    data = _minimal_fields_for(entity)

    # Generic STR placeholder, not an override value.
    assert data["title"] == "Trial parent"


def test_minimal_fields_for_skips_override_keys_not_on_entity():
    """Override keys for fields not present on the entity are silently ignored."""
    # EngagementLetter override includes "party" but we omit that field.
    scope_field = _make_field("scope_summary", FieldTypeKind.TEXT, FieldModifier.REQUIRED)
    entity = _make_entity("EngagementLetter", scope_field)

    data = _minimal_fields_for(entity)

    # "party" is in the override dict but not on the entity — must not appear in data.
    assert "party" not in data
    assert "Q4 brand refresh" in data["scope_summary"]


def test_minimal_fields_for_suffixes_unique_str_fields():
    """Unique STR fields get a run-id suffix to avoid collisions across seed runs."""
    ticket_number_field = _make_field(
        "ticket_number",
        FieldTypeKind.STR,
        FieldModifier.REQUIRED,
        FieldModifier.UNIQUE,
    )
    entity = _make_entity("Ticket", ticket_number_field)

    data = _minimal_fields_for(entity, _run_id="abcdef12")

    # The override value is "INC-2026-0428"; the suffix should be the first 6 chars of run_id.
    assert data["ticket_number"] == "INC-2026-0428-abcdef"


def test_minimal_fields_for_no_suffix_without_run_id():
    """Without a _run_id, unique STR fields keep the base override value."""
    ticket_number_field = _make_field(
        "ticket_number",
        FieldTypeKind.STR,
        FieldModifier.REQUIRED,
        FieldModifier.UNIQUE,
    )
    entity = _make_entity("Ticket", ticket_number_field)

    data = _minimal_fields_for(entity, _run_id=None)

    assert data["ticket_number"] == "INC-2026-0428"


def test_minimal_fields_for_suffixes_unique_email_override():
    """Unique EMAIL override values get a run-id infix (before @) so the address stays valid."""
    email_field = _make_field(
        "email",
        FieldTypeKind.EMAIL,
        FieldModifier.REQUIRED,
        FieldModifier.UNIQUE,
    )
    # Use Contact entity which has email in its override dict.
    entity = _make_entity("Contact", email_field)

    data = _minimal_fields_for(entity, _run_id="abcdef12")

    # Override sets "marcus.chen@northwind-apparel.example"; suffix goes before "@".
    assert data["email"] == "marcus.chen-abcdef@northwind-apparel.example"
    assert "@" in data["email"]  # still a valid email


def test_realistic_seed_overrides_contains_required_entities():
    """Sanity check: all four main entities are present in the override dict."""
    assert "Contact" in _REALISTIC_SEED_OVERRIDES
    assert "EngagementLetter" in _REALISTIC_SEED_OVERRIDES
    assert "Ticket" in _REALISTIC_SEED_OVERRIDES
    assert "SlaWaiver" in _REALISTIC_SEED_OVERRIDES
    assert "TestDoc" in _REALISTIC_SEED_OVERRIDES


def test_engagement_letter_override_has_realistic_signatory():
    """EngagementLetter override should contain a named person, not 'Trial Signatory'."""
    override = _REALISTIC_SEED_OVERRIDES["EngagementLetter"]
    assert override["signatory_name"] == "Priya Sharma"
    assert "northwind-apparel" in override["signatory_email"]


def test_sla_waiver_override_has_realistic_terms():
    """SlaWaiver override should contain actionable waiver text, not 'Trial-harness seed'."""
    override = _REALISTIC_SEED_OVERRIDES["SlaWaiver"]
    assert "service credit" in override["waiver_terms"]
    assert "Trial-harness seed" not in override["waiver_terms"]
    assert "Trial parent" not in override["breach_summary"]


def test_build_signing_seed_batch_resolves_grandparent_refs():
    """SlaWaiver→Ticket→User multi-hop chain: batch must include a User grandparent fixture.

    If the harness only resolves one level, the Ticket parent fixture will be
    missing its required ``created_by`` User ref and the seed POST will 400.
    """
    # User entity — no required REF fields
    user_entity = _make_entity(
        "User",
        _make_field("email", FieldTypeKind.EMAIL, FieldModifier.REQUIRED),
    )
    user_ref_field = _make_field("created_by", FieldTypeKind.REF, FieldModifier.REQUIRED)
    user_ref_field.type.ref_entity = "User"

    # Ticket entity — has a required REF to User
    ticket_title_field = _make_field("title", FieldTypeKind.STR, FieldModifier.REQUIRED)
    ticket_entity = _make_entity("Ticket", user_ref_field, ticket_title_field)

    ticket_ref_field = _make_field("ticket", FieldTypeKind.REF, FieldModifier.REQUIRED)
    ticket_ref_field.type.ref_entity = "Ticket"

    # SlaWaiver entity — has a required REF to Ticket (signable)
    waiver_entity = MagicMock(signable=True)
    waiver_entity.name = "SlaWaiver"
    waiver_entity.fields = [
        ticket_ref_field,
        _make_field("breach_summary", FieldTypeKind.TEXT, FieldModifier.REQUIRED),
        _make_field("waiver_terms", FieldTypeKind.TEXT, FieldModifier.REQUIRED),
        _make_field("signatory_name", FieldTypeKind.STR, FieldModifier.REQUIRED),
        _make_field("signatory_email", FieldTypeKind.EMAIL, FieldModifier.REQUIRED),
        _make_field("signatory_role", FieldTypeKind.STR, FieldModifier.REQUIRED),
    ]

    app_spec = MagicMock()
    app_spec.domain.entities = [user_entity, ticket_entity, waiver_entity]

    batch = _build_signing_seed_batch(waiver_entity, app_spec, "test@example.com")

    fixture_ids = [f["id"] for f in batch]
    fixture_entities = [f["entity"] for f in batch]

    # Must include a User grandparent, a Ticket parent, and the SlaWaiver signable.
    assert "User" in fixture_entities, f"Missing User grandparent in batch: {fixture_entities}"
    assert "Ticket" in fixture_entities, f"Missing Ticket parent in batch: {fixture_entities}"
    assert "signable_row" in fixture_ids, f"Missing signable_row in batch: {fixture_ids}"

    # The SlaWaiver (signable_row) must come last.
    assert fixture_ids[-1] == "signable_row"

    # The Ticket fixture must reference the User fixture via its refs mapping.
    ticket_fixture = next(f for f in batch if f["entity"] == "Ticket")
    assert "refs" in ticket_fixture, "Ticket fixture missing refs mapping for created_by"
    user_fixture_id = next(f["id"] for f in batch if f["entity"] == "User")
    assert user_fixture_id in ticket_fixture["refs"].values(), (
        f"Ticket refs {ticket_fixture['refs']} don't point to User fixture {user_fixture_id}"
    )
