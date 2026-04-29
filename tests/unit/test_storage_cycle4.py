"""Tests for #932 cycle 4 — storage-bound field auto-verification.

When a DSL field is declared ``field foo: file storage=<name>``, the
framework's auto-generated ``POST /api/{entity}`` (and PUT/PATCH)
handlers now verify any s3_key in the body before persisting:

    - prefix sandbox: the key must lie under the caller's own prefix
      (built from ``provider.prefix_template`` with ``{user_id}``
      bound to ``current_user``)
    - object existence: ``provider.head_object(s3_key)`` must return
      non-None

Tests run against the helper (``verify_storage_field_keys``) and the
binding builder (``build_entity_storage_bindings``); end-to-end route
verification is covered by ``test_storage_cycle3.py``'s upload-ticket
suite plus integration tests downstream.
"""

from __future__ import annotations

from typing import Any

import pytest

from dazzle_back.runtime.storage import (
    FakeStorageProvider,
    StorageRegistry,
    StorageVerificationError,
    build_entity_storage_bindings,
    verify_storage_field_keys,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _registry_with_provider(
    name: str = "cohort_pdfs",
    prefix_template: str = "uploads/{user_id}/{record_id}/",
) -> tuple[StorageRegistry, FakeStorageProvider]:
    registry = StorageRegistry.from_manifest({})
    provider = FakeStorageProvider(
        name=name,
        bucket="b",
        prefix_template=prefix_template,
    )
    registry.register_provider(name, provider)
    return registry, provider


# ---------------------------------------------------------------------------
# verify_storage_field_keys — happy path + skips
# ---------------------------------------------------------------------------


class TestVerifySkipsEmptyCases:
    def test_no_bindings_is_noop(self) -> None:
        verify_storage_field_keys(
            body={"source_pdf": "uploads/u1/r1/x.pdf"},
            storage_bindings={},
            registry=None,
            user_id="u1",
        )

    def test_empty_body_is_noop(self) -> None:
        registry, _ = _registry_with_provider()
        verify_storage_field_keys(
            body={},
            storage_bindings={"source_pdf": ("cohort_pdfs",)},
            registry=registry,
            user_id="u1",
        )

    def test_field_absent_from_body_is_noop(self) -> None:
        registry, _ = _registry_with_provider()
        verify_storage_field_keys(
            body={"title": "hello"},
            storage_bindings={"source_pdf": ("cohort_pdfs",)},
            registry=registry,
            user_id="u1",
        )

    def test_field_value_none_is_noop(self) -> None:
        registry, _ = _registry_with_provider()
        verify_storage_field_keys(
            body={"source_pdf": None},
            storage_bindings={"source_pdf": ("cohort_pdfs",)},
            registry=registry,
            user_id="u1",
        )

    def test_field_value_empty_string_is_noop(self) -> None:
        registry, _ = _registry_with_provider()
        verify_storage_field_keys(
            body={"source_pdf": ""},
            storage_bindings={"source_pdf": ("cohort_pdfs",)},
            registry=registry,
            user_id="u1",
        )


class TestVerifyHappyPath:
    def test_valid_key_passes(self) -> None:
        registry, provider = _registry_with_provider()
        provider.put_object("uploads/u1/r1/file.pdf", b"x", content_type="application/pdf")
        verify_storage_field_keys(
            body={"source_pdf": "uploads/u1/r1/file.pdf"},
            storage_bindings={"source_pdf": ("cohort_pdfs",)},
            registry=registry,
            user_id="u1",
        )

    def test_multi_storage_entity(self) -> None:
        """An entity with two file fields backed by two different
        storages — each field verified against its own provider."""
        reg = StorageRegistry.from_manifest({})
        primary = FakeStorageProvider(
            name="primary",
            bucket="b",
            prefix_template="primary/{user_id}/{record_id}/",
        )
        thumbs = FakeStorageProvider(
            name="thumbs",
            bucket="b",
            prefix_template="thumbs/{user_id}/{record_id}/",
        )
        reg.register_provider("primary", primary)
        reg.register_provider("thumbs", thumbs)
        primary.put_object("primary/u1/r1/x.pdf", b"x", content_type="application/pdf")
        thumbs.put_object("thumbs/u1/r1/t.png", b"y", content_type="image/png")

        verify_storage_field_keys(
            body={
                "source_pdf": "primary/u1/r1/x.pdf",
                "thumbnail": "thumbs/u1/r1/t.png",
            },
            storage_bindings={"source_pdf": ("primary",), "thumbnail": ("thumbs",)},
            registry=reg,
            user_id="u1",
        )


# ---------------------------------------------------------------------------
# verify_storage_field_keys — failure modes
# ---------------------------------------------------------------------------


class TestVerifyRejects:
    def test_non_string_value_400(self) -> None:
        registry, _ = _registry_with_provider()
        with pytest.raises(StorageVerificationError) as exc_info:
            verify_storage_field_keys(
                body={"source_pdf": 42},
                storage_bindings={"source_pdf": ("cohort_pdfs",)},
                registry=registry,
                user_id="u1",
            )
        assert exc_info.value.status_code == 400
        assert "must be a string" in exc_info.value.reason

    def test_missing_registry_500(self) -> None:
        with pytest.raises(StorageVerificationError) as exc_info:
            verify_storage_field_keys(
                body={"source_pdf": "uploads/u1/r1/x.pdf"},
                storage_bindings={"source_pdf": ("cohort_pdfs",)},
                registry=None,
                user_id="u1",
            )
        assert exc_info.value.status_code == 500
        assert "no StorageRegistry" in exc_info.value.reason

    def test_missing_user_401(self) -> None:
        registry, provider = _registry_with_provider()
        provider.put_object("uploads/u1/r1/x.pdf", b"x", content_type="application/pdf")
        with pytest.raises(StorageVerificationError) as exc_info:
            verify_storage_field_keys(
                body={"source_pdf": "uploads/u1/r1/x.pdf"},
                storage_bindings={"source_pdf": ("cohort_pdfs",)},
                registry=registry,
                user_id=None,
            )
        assert exc_info.value.status_code == 401

    def test_unregistered_storage_503(self) -> None:
        registry = StorageRegistry.from_manifest({})
        with pytest.raises(StorageVerificationError) as exc_info:
            verify_storage_field_keys(
                body={"source_pdf": "uploads/u1/r1/x.pdf"},
                storage_bindings={"source_pdf": ("missing_storage",)},
                registry=registry,
                user_id="u1",
            )
        assert exc_info.value.status_code == 503
        assert "missing_storage" in exc_info.value.reason

    def test_other_users_prefix_403(self) -> None:
        """The security-critical case: user u1 tries to claim user u2's
        already-uploaded object."""
        registry, provider = _registry_with_provider()
        provider.put_object("uploads/u2/r1/x.pdf", b"x", content_type="application/pdf")
        with pytest.raises(StorageVerificationError) as exc_info:
            verify_storage_field_keys(
                body={"source_pdf": "uploads/u2/r1/x.pdf"},
                storage_bindings={"source_pdf": ("cohort_pdfs",)},
                registry=registry,
                user_id="u1",
            )
        assert exc_info.value.status_code == 403
        assert "sandbox" in exc_info.value.reason

    def test_object_does_not_exist_400(self) -> None:
        """User submits a key they never actually uploaded — the
        mint-ticket flow may have happened, but the upload itself
        either failed or didn't fire."""
        registry, _ = _registry_with_provider()
        with pytest.raises(StorageVerificationError) as exc_info:
            verify_storage_field_keys(
                body={"source_pdf": "uploads/u1/r1/never-uploaded.pdf"},
                storage_bindings={"source_pdf": ("cohort_pdfs",)},
                registry=registry,
                user_id="u1",
            )
        assert exc_info.value.status_code == 400
        assert "no object" in exc_info.value.reason

    def test_provider_head_object_raises_503(self) -> None:
        """Network/auth failure to S3 surfaces as 503 — distinguishable
        from 400 (object missing) so clients don't retry indefinitely
        on a transient infra fault."""
        registry, provider = _registry_with_provider()

        def boom(_key: str) -> Any:
            raise RuntimeError("boto auth failed")

        provider.head_object = boom  # type: ignore[method-assign]
        with pytest.raises(StorageVerificationError) as exc_info:
            verify_storage_field_keys(
                body={"source_pdf": "uploads/u1/r1/x.pdf"},
                storage_bindings={"source_pdf": ("cohort_pdfs",)},
                registry=registry,
                user_id="u1",
            )
        assert exc_info.value.status_code == 503
        assert "head_object raised" in exc_info.value.reason


# ---------------------------------------------------------------------------
# Prefix-sandbox edge cases
# ---------------------------------------------------------------------------


class TestPrefixSandbox:
    def test_user_id_substring_collision_does_not_pass(self) -> None:
        """Naive substring matching would let user 'u1' claim a key
        under 'u11'. The regex builds whole-segment boundaries from
        the prefix template's ``{user_id}`` placeholder so the match
        is exact, not substring."""
        registry, provider = _registry_with_provider()
        provider.put_object("uploads/u11/r1/x.pdf", b"x", content_type="application/pdf")
        with pytest.raises(StorageVerificationError) as exc_info:
            verify_storage_field_keys(
                body={"source_pdf": "uploads/u11/r1/x.pdf"},
                storage_bindings={"source_pdf": ("cohort_pdfs",)},
                registry=registry,
                user_id="u1",
            )
        assert exc_info.value.status_code == 403

    def test_user_with_special_regex_chars_in_id(self) -> None:
        """User ids that contain regex metacharacters (``.``, ``+``,
        ``(``, etc.) must still match exactly — the prefix builder
        escapes them rather than treating them as patterns."""
        registry, provider = _registry_with_provider(
            prefix_template="uploads/{user_id}/{record_id}/",
        )
        provider.put_object(
            "uploads/user.with+special/r1/x.pdf",
            b"x",
            content_type="application/pdf",
        )
        # Same pattern, the literal user_id matches.
        verify_storage_field_keys(
            body={"source_pdf": "uploads/user.with+special/r1/x.pdf"},
            storage_bindings={"source_pdf": ("cohort_pdfs",)},
            registry=registry,
            user_id="user.with+special",
        )
        # A different user with the literal string ``user.with`` (the
        # ``.`` would match anything if unescaped) must NOT pass.
        with pytest.raises(StorageVerificationError) as exc_info:
            verify_storage_field_keys(
                body={"source_pdf": "uploads/userXwithYspecial/r1/x.pdf"},
                storage_bindings={"source_pdf": ("cohort_pdfs",)},
                registry=registry,
                user_id="user.with+special",
            )
        assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# build_entity_storage_bindings
# ---------------------------------------------------------------------------


class TestBuildBindings:
    def test_no_domain_returns_empty(self) -> None:
        class _Empty:
            domain = None

        assert build_entity_storage_bindings(_Empty()) == {}

    def test_empty_entities_returns_empty(self) -> None:
        class _Domain:
            entities: list[Any] = []

        class _Spec:
            domain = _Domain()

        assert build_entity_storage_bindings(_Spec()) == {}

    def test_mixed_fields_extracts_storage_only(self) -> None:
        from pathlib import Path

        from dazzle.core import ir
        from dazzle.core.dsl_parser_impl import parse_dsl

        _, _, _, _, _, fragment = parse_dsl(
            """
module test
app A "A"

entity Doc:
  id: uuid pk
  title: str(200)
  source_pdf: file storage=cohort_pdfs

entity NoStorage:
  id: uuid pk
  title: str(200)

entity TwoFiles:
  id: uuid pk
  primary: file storage=primary
  thumb: file storage=thumbs
""",
            Path("test.dsl"),
        )
        spec = ir.AppSpec(name="t", domain=ir.DomainSpec(entities=fragment.entities))

        bindings = build_entity_storage_bindings(spec)
        assert bindings == {
            "Doc": {"source_pdf": ("cohort_pdfs",)},
            "TwoFiles": {"primary": ("primary",), "thumb": ("thumbs",)},
        }
        # Entity without any storage-bound fields is omitted entirely.
        assert "NoStorage" not in bindings
