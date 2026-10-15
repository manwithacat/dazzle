"""Unit tests for the signing-env provisioning helpers wired into qa_trial."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest

from dazzle.cli.qa import (
    _REALISTIC_SEED_OVERRIDES,
    _build_signing_seed_batch,
    _minimal_fields_for,
    _provision_signing_env,
    _seed_signable_rows,
)
from dazzle.core.ir.fields import FieldModifier, FieldTypeKind
from dazzle.signing.tokens import InvalidTokenError, verify_token


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


def _signable_app_spec(*names: str) -> SimpleNamespace:
    """An app_spec whose domain.entities are signable entities with the given names."""
    entities = [SimpleNamespace(name=n, signable=True, fields=[]) for n in names]
    return SimpleNamespace(
        domain=SimpleNamespace(entities=entities),
        has_signable_entity=lambda: bool(entities),
    )


# ---------------------------------------------------------------------------
# _provision_signing_env — real cert minting, real dependency preflight
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("validator_reject", [False, True], ids=["default", "validator-reject"])
def test_provision_mints_signing_env_and_pregenerates_ids(
    tmp_path: Path, validator_reject: bool
) -> None:
    """The env carries a cert + token secret; one UUID is pre-generated per
    signable entity and, with ``validator_reject`` (#1382), armed in
    ``DAZZLE_QA_SIGNING_REJECT_IDS`` before boot."""
    pytest.importorskip("pyhanko")
    pytest.importorskip("fpdf")

    ctx = _provision_signing_env(
        _signable_app_spec("SlaWaiver"),
        tmp_path,
        project_name="Test",
        validator_reject=validator_reject,
    )

    assert ctx is not None
    assert {"SIGNING_CERT_PFX_B64", "SIGNING_CERT_PASSWORD", "SIGNING_TOKEN_SECRET"} <= set(ctx.env)
    assert set(ctx.signable_ids) == {"SlaWaiver"}
    assert ctx.validator_reject is validator_reject
    armed = ctx.env.get("DAZZLE_QA_SIGNING_REJECT_IDS")
    assert armed == (ctx.signable_ids["SlaWaiver"] if validator_reject else None)


def test_provision_returns_none_when_no_signable(tmp_path: Path) -> None:
    assert _provision_signing_env(_signable_app_spec(), tmp_path, project_name="Test") is None


def test_provision_aborts_when_signing_server_deps_missing(tmp_path: Path) -> None:
    """#1377: provisioning the signing rig without fpdf2/pyhanko burned a
    full persona run into a guaranteed sign_document HTTP 500. The
    preflight must exit 2 with the install hint instead."""
    import typer

    with patch("dazzle.cli.qa._missing_signing_server_deps", return_value=["fpdf", "pyhanko"]):
        with pytest.raises(typer.Exit) as exc:
            _provision_signing_env(_signable_app_spec("SlaWaiver"), tmp_path, project_name="Test")
    assert exc.value.exit_code == 2


def test_build_batch_pins_signable_id_when_given() -> None:
    """#1382: an explicit signable_id is written into the signable row's
    data['id'] so the inserted row carries the armed UUID."""
    app_spec = _signable_app_spec("SlaWaiver")
    [entity] = app_spec.domain.entities

    batch = _build_signing_seed_batch(
        entity, app_spec, "a@b.com", signable_id="11111111-1111-1111-1111-111111111111"
    )
    signable_fixture = next(f for f in batch if f["id"] == "signable_row")
    assert signable_fixture["data"]["id"] == "11111111-1111-1111-1111-111111111111"


# ---------------------------------------------------------------------------
# _seed_signable_rows against a recording stand-in for the running app.
# Tokens are minted for real and checked with verify_token.
# ---------------------------------------------------------------------------


class _FakeApp:
    """Answers the three endpoints the seeder calls and records each request."""

    def __init__(self, row_id: str, reopen_html: str) -> None:
        self.row_id = row_id
        self.reopen_html = reopen_html
        self.requests: list[tuple[str, str, Any]] = []

    def post(self, url: str, *, json: Any, **_kw: Any) -> httpx.Response:
        self.requests.append(("POST", url, json))
        body = {"created": {"signable_row": {"id": self.row_id}}} if "/__test__/seed" in url else {}
        return httpx.Response(200, json=body, request=httpx.Request("POST", url))

    def get(self, url: str, *, params: Any, **_kw: Any) -> httpx.Response:
        self.requests.append(("GET", url, params))
        return httpx.Response(200, text=self.reopen_html, request=httpx.Request("GET", url))


_SIGNED_COPY_HTML = (
    '<html><a href="/sign/SlaWaiver/row-1/signed-copy?token=t">Download your signed copy</a>'
)


@pytest.fixture
def fake_app(monkeypatch: pytest.MonkeyPatch) -> _FakeApp:
    app = _FakeApp("row-1", _SIGNED_COPY_HTML)
    monkeypatch.setattr(httpx, "post", app.post)
    monkeypatch.setattr(httpx, "get", app.get)
    monkeypatch.setenv("SIGNING_TOKEN_SECRET", "test-secret")
    return app


def _seed(app_spec: Any, **kwargs: Any) -> list[Any]:
    return _seed_signable_rows(
        app_spec=app_spec,
        base_url="http://app.test",
        signatory_email="a@b.com",
        **kwargs,
    )


def test_seed_inserts_one_row_per_signable_entity_via_test_seed(fake_app: _FakeApp) -> None:
    """Only signable entities are seeded, through the Cedar-bypass
    ``/__test__/seed`` endpoint, with a fresh token that verifies."""
    app_spec = _signable_app_spec("EngagementLetter")
    app_spec.domain.entities.append(SimpleNamespace(name="Note", signable=False, fields=[]))

    [doc] = _seed(app_spec, test_secret="dummy")

    assert [(method, url) for method, url, _ in fake_app.requests] == [
        ("POST", "http://app.test/__test__/seed")
    ]
    assert (doc.entity, doc.id, doc.token_state) == ("EngagementLetter", "row-1", "fresh")
    assert verify_token(doc.token)[0] == "row-1"


def test_seed_expired_token_state_mints_a_token_that_fails_verification(
    fake_app: _FakeApp,
) -> None:
    """TR-51: ``token_state="expired"`` mints an already-expired token, so the
    scenario reaches the real "Invalid or expired link" page."""
    [doc] = _seed(_signable_app_spec("SlaWaiver"), token_state="expired")

    assert doc.token_state == "expired"
    with pytest.raises(InvalidTokenError, match="expired"):
        verify_token(doc.token)


def test_seed_uses_pregenerated_id_and_stamps_validator_reject(fake_app: _FakeApp) -> None:
    """#1382: the seed posts the pre-generated id and stamps the SeededDoc so
    the verifier expects a validator rejection."""
    pre_id = "22222222-2222-2222-2222-222222222222"
    fake_app.row_id = pre_id

    [doc] = _seed(
        _signable_app_spec("SlaWaiver"),
        signable_ids={"SlaWaiver": pre_id},
        validator_reject=True,
    )

    [(_, _, posted)] = fake_app.requests
    signable_fixture = next(f for f in posted["fixtures"] if f["id"] == "signable_row")
    assert signable_fixture["data"]["id"] == pre_id
    assert (doc.id, doc.validator_reject) == (pre_id, True)


def test_seed_already_signed_signs_through_the_production_api(fake_app: _FakeApp) -> None:
    """TR-49/50: already_signed seeds, POSTs ``/api/sign`` with the minted
    token and a signature, then re-opens the link expecting a Download."""
    [doc] = _seed(_signable_app_spec("SlaWaiver"), token_state="already_signed")

    assert doc.token_state == "already_signed"
    assert [(method, url) for method, url, _ in fake_app.requests] == [
        ("POST", "http://app.test/__test__/seed"),
        ("POST", "http://app.test/api/sign/SlaWaiver/row-1"),
        ("GET", "http://app.test/sign/SlaWaiver/row-1"),
    ]
    sign_body = fake_app.requests[1][2]
    assert sign_body["token"] == doc.token
    assert sign_body["signature_png_b64"]
    assert verify_token(doc.token)[0] == "row-1"


def test_seed_already_signed_raises_without_download_cta(fake_app: _FakeApp) -> None:
    """TR-49: pre-sign must fail loud if re-open has no Download path."""
    fake_app.reopen_html = "<html>Document unavailable</html>"

    with pytest.raises(RuntimeError, match="TR-49 already_signed"):
        _seed(_signable_app_spec("SlaWaiver"), token_state="already_signed")


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
