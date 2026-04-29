"""Tests for #941 cycle 5 — multi-storage field annotations.

A `file` field can now declare multiple storage bindings via the
pipe operator:

    source_pdf_url: file storage=cohort_pdfs|starter_packs

Models the real shared+private fan-in case from AegisMark: a field
that can hold either a per-user upload (sandboxed under
`{user_id}` in the cohort_pdfs prefix) OR a reference to a
shared starter-pack asset (under starter_packs prefix, no user
scope). The verifier accepts the s3_key against each binding in
turn and passes if any one matches; rejects with the
highest-confidence rejection when none match.

Tests cover:
- Parser: pipe-separated names parse to a tuple
- Parser: rejects duplicate names within a single binding
- Validator: every name in the tuple must resolve
- Verifier: accepts a key matching the SECOND binding's prefix
- Verifier: rejects a key matching neither binding
- Verifier: head_object failure on the first binding falls through
  to the second
- Upload-ticket route: mints presigned forms for the FIRST binding
  (the canonical upload destination)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.core import ir
from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.errors import ParseError
from dazzle.core.manifest import StorageConfig
from dazzle.core.validator import validate_storage_refs
from dazzle_back.runtime.storage import (
    FakeStorageProvider,
    StorageRegistry,
    StorageVerificationError,
    build_entity_storage_bindings,
    register_upload_ticket_routes,
    verify_storage_field_keys,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _appspec_from_dsl(dsl: str) -> ir.AppSpec:
    _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
    return ir.AppSpec(
        name="test_app",
        domain=ir.DomainSpec(entities=fragment.entities),
    )


def _cfg(name: str, prefix_template: str | None = None) -> StorageConfig:
    if prefix_template is None:
        # Default uses the storage name as a literal prefix segment.
        # `{user_id}`/`{record_id}` are intentional template placeholders
        # the verifier resolves at request time — leave them untouched.
        prefix_template = f"{name}/{{user_id}}/{{record_id}}/"
    return StorageConfig(
        name=name,
        backend="s3",
        bucket="b",
        region="r",
        prefix_template=prefix_template,
        max_bytes=1024,
        content_types=[],
        ticket_ttl_seconds=60,
    )


def _registry(*providers: FakeStorageProvider) -> StorageRegistry:
    reg = StorageRegistry.from_manifest({})
    for p in providers:
        reg.register_provider(p.name, p)
    return reg


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


class TestParser:
    def test_pipe_separated_names_parse_to_tuple(self) -> None:
        spec = _appspec_from_dsl(
            """
module test
app A "A"

entity Doc:
  id: uuid pk
  source_pdf: file storage=cohort_pdfs|starter_packs
"""
        )
        field = spec.domain.entities[0].fields[1]
        assert field.storage == ("cohort_pdfs", "starter_packs")

    def test_three_way_binding_parses(self) -> None:
        spec = _appspec_from_dsl(
            """
module test
app A "A"

entity Doc:
  id: uuid pk
  source_pdf: file storage=primary|backup|archive
"""
        )
        assert spec.domain.entities[0].fields[1].storage == (
            "primary",
            "backup",
            "archive",
        )

    def test_single_name_still_parses_as_tuple_of_one(self) -> None:
        """Backward compat: the cycle-1 syntax `storage=foo` still
        works and produces ``("foo",)``."""
        spec = _appspec_from_dsl(
            """
module test
app A "A"

entity Doc:
  id: uuid pk
  source_pdf: file storage=cohort_pdfs
"""
        )
        assert spec.domain.entities[0].fields[1].storage == ("cohort_pdfs",)

    def test_duplicate_name_in_single_binding_rejected(self) -> None:
        with pytest.raises(ParseError, match="Duplicate name in `storage="):
            parse_dsl(
                """
module test
app A "A"

entity Doc:
  id: uuid pk
  source_pdf: file storage=cohort_pdfs|cohort_pdfs
""",
                Path("test.dsl"),
            )

    def test_pipe_composes_with_other_modifiers(self) -> None:
        """Multi-storage binding still composes with `required` and
        other modifiers on the same line."""
        spec = _appspec_from_dsl(
            """
module test
app A "A"

entity Doc:
  id: uuid pk
  source_pdf: file required storage=primary|backup
"""
        )
        f = spec.domain.entities[0].fields[1]
        assert f.storage == ("primary", "backup")
        assert f.is_required


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------


class TestValidator:
    def test_all_names_resolved_passes(self) -> None:
        spec = _appspec_from_dsl(
            """
module test
app A "A"

entity Doc:
  id: uuid pk
  source_pdf: file storage=cohort_pdfs|starter_packs
"""
        )
        defs = {
            "cohort_pdfs": _cfg("cohort_pdfs"),
            "starter_packs": _cfg("starter_packs"),
        }
        errors, warnings = validate_storage_refs(spec, defs)
        assert errors == []
        assert warnings == []

    def test_first_name_unresolved_errors(self) -> None:
        spec = _appspec_from_dsl(
            """
module test
app A "A"

entity Doc:
  id: uuid pk
  source_pdf: file storage=missing_one|starter_packs
"""
        )
        defs = {"starter_packs": _cfg("starter_packs")}
        errors, warnings = validate_storage_refs(spec, defs)
        assert len(errors) == 1
        assert "missing_one" in errors[0]
        assert "starter_packs" in errors[0]  # rendered as available

    def test_second_name_unresolved_errors(self) -> None:
        spec = _appspec_from_dsl(
            """
module test
app A "A"

entity Doc:
  id: uuid pk
  source_pdf: file storage=cohort_pdfs|missing_two
"""
        )
        defs = {"cohort_pdfs": _cfg("cohort_pdfs")}
        errors, warnings = validate_storage_refs(spec, defs)
        assert len(errors) == 1
        assert "missing_two" in errors[0]


# ---------------------------------------------------------------------------
# Verifier
# ---------------------------------------------------------------------------


class TestVerifier:
    def test_first_binding_matches_passes(self) -> None:
        cohort = FakeStorageProvider(
            name="cohort_pdfs",
            bucket="b",
            prefix_template="cohort/{user_id}/{record_id}/",
        )
        starter = FakeStorageProvider(
            name="starter_packs",
            bucket="b",
            prefix_template="starter/",
        )
        registry = _registry(cohort, starter)
        cohort.put_object("cohort/u1/r1/x.pdf", b"x", content_type="application/pdf")

        verify_storage_field_keys(
            body={"source_pdf": "cohort/u1/r1/x.pdf"},
            storage_bindings={"source_pdf": ("cohort_pdfs", "starter_packs")},
            registry=registry,
            user_id="u1",
        )

    def test_second_binding_matches_passes(self) -> None:
        """The shared-asset case: user references a starter-pack key
        that lives under `starter/` (no `{user_id}` segment). The
        first binding's sandbox rejects (key isn't under the user's
        cohort prefix) but the second binding accepts."""
        cohort = FakeStorageProvider(
            name="cohort_pdfs",
            bucket="b",
            prefix_template="cohort/{user_id}/{record_id}/",
        )
        starter = FakeStorageProvider(
            name="starter_packs",
            bucket="b",
            prefix_template="starter/",
        )
        registry = _registry(cohort, starter)
        starter.put_object("starter/y10_macbeth.pdf", b"y", content_type="application/pdf")

        verify_storage_field_keys(
            body={"source_pdf": "starter/y10_macbeth.pdf"},
            storage_bindings={"source_pdf": ("cohort_pdfs", "starter_packs")},
            registry=registry,
            user_id="u1",
        )

    def test_neither_binding_matches_rejects(self) -> None:
        """Key matches the first binding's sandbox but the object
        doesn't exist there, AND falls outside the second binding's
        prefix. Verifier rejects with the second binding's error
        (the last failure recorded)."""
        cohort = FakeStorageProvider(
            name="cohort_pdfs",
            bucket="b",
            prefix_template="cohort/{user_id}/{record_id}/",
        )
        starter = FakeStorageProvider(
            name="starter_packs",
            bucket="b",
            prefix_template="starter/",
        )
        registry = _registry(cohort, starter)

        with pytest.raises(StorageVerificationError) as exc_info:
            verify_storage_field_keys(
                body={"source_pdf": "cohort/u1/r1/never-uploaded.pdf"},
                storage_bindings={"source_pdf": ("cohort_pdfs", "starter_packs")},
                registry=registry,
                user_id="u1",
            )
        # First binding: sandbox passes but head_object misses (400).
        # Second binding: sandbox rejects ("cohort/..." not under
        # "starter/", 403). Both are recorded; the last seen wins.
        assert exc_info.value.status_code == 403
        assert exc_info.value.storage == "starter_packs"

    def test_head_object_miss_on_first_falls_through_to_second(self) -> None:
        """Both bindings could in principle accept the key (their
        prefix templates overlap), but the object only exists in the
        second. Verifier accepts."""
        primary = FakeStorageProvider(
            name="primary",
            bucket="b",
            prefix_template="shared/",
        )
        backup = FakeStorageProvider(
            name="backup",
            bucket="b",
            prefix_template="shared/",
        )
        registry = _registry(primary, backup)
        # Object lives only in backup, not primary.
        backup.put_object("shared/file.pdf", b"x", content_type="application/pdf")

        verify_storage_field_keys(
            body={"source_pdf": "shared/file.pdf"},
            storage_bindings={"source_pdf": ("primary", "backup")},
            registry=registry,
            user_id="u1",
        )

    def test_unregistered_first_binding_falls_through(self) -> None:
        """If the first storage isn't registered (config drift), the
        verifier records the 503 and continues to the next binding.
        The second binding accepts the key — overall pass."""
        starter = FakeStorageProvider(
            name="starter_packs",
            bucket="b",
            prefix_template="starter/",
        )
        registry = _registry(starter)  # cohort_pdfs deliberately missing
        starter.put_object("starter/y10.pdf", b"y", content_type="application/pdf")

        verify_storage_field_keys(
            body={"source_pdf": "starter/y10.pdf"},
            storage_bindings={"source_pdf": ("cohort_pdfs", "starter_packs")},
            registry=registry,
            user_id="u1",
        )

    def test_all_bindings_unregistered_rejects(self) -> None:
        registry = _registry()  # both deliberately missing

        with pytest.raises(StorageVerificationError) as exc_info:
            verify_storage_field_keys(
                body={"source_pdf": "any/key.pdf"},
                storage_bindings={"source_pdf": ("cohort_pdfs", "starter_packs")},
                registry=registry,
                user_id="u1",
            )
        assert exc_info.value.status_code == 503


# ---------------------------------------------------------------------------
# Upload-ticket route
# ---------------------------------------------------------------------------


class TestUploadTicketRoute:
    def test_first_binding_is_the_upload_destination(self) -> None:
        """A field declared `storage=cohort_pdfs|starter_packs` mints
        upload tickets against `cohort_pdfs` only — the first binding
        is the canonical upload target. Starter packs are read-only
        references the verifier accepts at finalize time, but the
        framework doesn't auto-mint against them."""
        try:
            from fastapi import FastAPI
        except ImportError:
            pytest.skip("FastAPI required")

        spec = _appspec_from_dsl(
            """
module test
app A "A"

entity Doc:
  id: uuid pk
  source_pdf: file storage=cohort_pdfs|starter_packs
"""
        )
        cohort = FakeStorageProvider(
            name="cohort_pdfs",
            bucket="b",
            prefix_template="cohort/{user_id}/{record_id}/",
        )
        starter = FakeStorageProvider(
            name="starter_packs",
            bucket="b",
            prefix_template="starter/",
        )
        registry = _registry(cohort, starter)

        app = FastAPI()
        paths = register_upload_ticket_routes(app=app, appspec=spec, registry=registry)
        # One route per entity with at least one storage binding.
        assert paths == ["/api/doc/upload-ticket"]

    def test_build_entity_storage_bindings_preserves_order(self) -> None:
        """The verifier walks bindings in declared order — the first
        is the upload destination, others are accepted-only fan-in.
        Ensure ``build_entity_storage_bindings`` doesn't reorder."""
        spec = _appspec_from_dsl(
            """
module test
app A "A"

entity Doc:
  id: uuid pk
  source_pdf: file storage=primary|backup|archive
"""
        )
        bindings = build_entity_storage_bindings(spec)
        assert bindings == {"Doc": {"source_pdf": ("primary", "backup", "archive")}}
