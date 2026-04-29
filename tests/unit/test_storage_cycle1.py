"""Tests for #932 cycle 1 — storage config + protocol types + DSL field binding.

Cycle 1 ships:
- `[storage.<name>]` blocks parsed from `dazzle.toml` into
  `StorageConfig` dataclasses.
- `${VAR}` env-var interpolation with loud-on-missing semantics.
- `field foo: file storage=<name>` DSL syntax (parser-only; the
  field-spec carries `storage: str | None`).
- `StorageProvider` Protocol + `UploadTicket` / `ObjectMetadata`
  dataclasses for the cycle-2 backend implementations to satisfy.

No runtime / boto3 / route changes yet.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.manifest import StorageConfig, _parse_storage_configs
from dazzle_back.runtime.storage import (
    EnvVarMissingError,
    ObjectMetadata,
    StorageProvider,
    UploadTicket,
    extract_env_var_refs,
    interpolate_env_vars,
)

# ---------------------------------------------------------------------------
# Manifest config parsing
# ---------------------------------------------------------------------------


class TestStorageConfigParsing:
    def test_minimal_block(self) -> None:
        data = {
            "storage": {
                "cohort_pdfs": {
                    "backend": "s3",
                    "bucket": "my-bucket",
                    "region": "eu-west-2",
                    "prefix": "uploads/{user_id}/{record_id}/",
                }
            }
        }
        out = _parse_storage_configs(data)
        assert "cohort_pdfs" in out
        cfg = out["cohort_pdfs"]
        assert cfg.name == "cohort_pdfs"
        assert cfg.backend == "s3"
        assert cfg.bucket == "my-bucket"
        assert cfg.region == "eu-west-2"
        assert cfg.prefix_template == "uploads/{user_id}/{record_id}/"
        # Defaults
        assert cfg.max_bytes == 50 * 1024 * 1024
        assert cfg.ticket_ttl_seconds == 600
        assert cfg.content_types == []
        assert cfg.endpoint_url is None

    def test_full_block(self) -> None:
        data = {
            "storage": {
                "cohort_pdfs": {
                    "backend": "s3",
                    "bucket": "${S3_BUCKET}",
                    "region": "${AWS_REGION}",
                    "endpoint_url": "${S3_ENDPOINT_URL}",
                    "prefix": "production/{user_id}/{record_id}/",
                    "max_bytes": 200_000_000,
                    "content_types": ["application/pdf"],
                    "ticket_ttl_seconds": 1200,
                }
            }
        }
        cfg = _parse_storage_configs(data)["cohort_pdfs"]
        # Env-var references survive parsing; interpolation happens at
        # runtime via `interpolate_env_vars`.
        assert cfg.bucket == "${S3_BUCKET}"
        assert cfg.region == "${AWS_REGION}"
        assert cfg.endpoint_url == "${S3_ENDPOINT_URL}"
        assert cfg.max_bytes == 200_000_000
        assert cfg.content_types == ["application/pdf"]
        assert cfg.ticket_ttl_seconds == 1200

    def test_prefix_auto_terminates_with_slash(self) -> None:
        """Authors might forget the trailing slash; the parser adds it
        so key concatenation downstream is unambiguous."""
        data = {
            "storage": {
                "x": {
                    "backend": "s3",
                    "bucket": "b",
                    "region": "r",
                    "prefix": "uploads/{user_id}/{record_id}",
                }
            }
        }
        cfg = _parse_storage_configs(data)["x"]
        assert cfg.prefix_template.endswith("/")

    def test_unknown_backend_rejected(self) -> None:
        data = {
            "storage": {
                "x": {"backend": "azure_blob", "bucket": "b", "region": "r", "prefix": "p/"}
            }
        }
        with pytest.raises(ValueError, match="backend must be one of"):
            _parse_storage_configs(data)

    def test_missing_required_keys_rejected(self) -> None:
        data = {"storage": {"x": {"backend": "s3", "bucket": "b"}}}
        with pytest.raises(ValueError, match="missing required key"):
            _parse_storage_configs(data)

    def test_empty_when_no_storage_section(self) -> None:
        assert _parse_storage_configs({"project": {}}) == {}

    def test_storage_section_must_be_table(self) -> None:
        with pytest.raises(ValueError, match="must be a TOML table"):
            _parse_storage_configs({"storage": {"x": "not-a-dict"}})


# ---------------------------------------------------------------------------
# Env-var interpolation
# ---------------------------------------------------------------------------


class TestEnvVarInterpolation:
    def test_extract_refs_in_order(self) -> None:
        assert extract_env_var_refs("${A}/${B}/static/${C}") == ["A", "B", "C"]

    def test_extract_dedupes(self) -> None:
        assert extract_env_var_refs("${A}/${A}/${B}") == ["A", "B"]

    def test_extract_none_safe(self) -> None:
        assert extract_env_var_refs(None) == []

    def test_interpolate_substitutes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("S3_BUCKET", "my-bucket")
        monkeypatch.setenv("AWS_REGION", "eu-west-2")
        assert interpolate_env_vars("s3://${S3_BUCKET}/${AWS_REGION}") == "s3://my-bucket/eu-west-2"

    def test_interpolate_passes_through_literals(self) -> None:
        assert interpolate_env_vars("plain-string") == "plain-string"

    def test_interpolate_none(self) -> None:
        assert interpolate_env_vars(None) is None

    def test_missing_var_raises_loud(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DEFINITELY_NOT_SET_XYZ", raising=False)
        with pytest.raises(EnvVarMissingError) as excinfo:
            interpolate_env_vars("${DEFINITELY_NOT_SET_XYZ}", context="[storage.x] bucket")
        assert excinfo.value.var_name == "DEFINITELY_NOT_SET_XYZ"
        assert "[storage.x] bucket" in str(excinfo.value)

    def test_lowercase_var_not_recognised(self) -> None:
        """`${var}` (lowercase) is intentionally rejected — env vars
        are uppercase by convention; lowercase is almost certainly a
        typo for a literal value."""
        # The pattern only matches uppercase, so this passes through
        # unchanged rather than silently injecting empty string.
        assert interpolate_env_vars("${var_name}") == "${var_name}"


# ---------------------------------------------------------------------------
# Protocol shape
# ---------------------------------------------------------------------------


class _SatisfiesProtocol:
    """Minimal class satisfying StorageProvider — used to confirm the
    protocol's runtime_checkable check accepts a real implementation."""

    name = "x"
    bucket = "b"
    prefix_template = "p/"
    max_bytes = 1024
    content_types: list[str] = []
    ticket_ttl_seconds = 60

    def render_prefix(self, *, user_id: str, record_id: str) -> str:
        return f"p/{user_id}/{record_id}/"

    def mint_upload_ticket(self, *, key: str, content_type: str) -> UploadTicket:
        return UploadTicket(url="https://x", fields={}, s3_key=key, expires_in_seconds=60)

    def head_object(self, key: str) -> ObjectMetadata | None:
        return None


class TestStorageProviderProtocol:
    def test_runtime_check_accepts_full_impl(self) -> None:
        assert isinstance(_SatisfiesProtocol(), StorageProvider)

    def test_runtime_check_rejects_partial_impl(self) -> None:
        class Partial:
            name = "x"
            # missing the rest

        assert not isinstance(Partial(), StorageProvider)

    def test_upload_ticket_is_immutable(self) -> None:
        from dataclasses import FrozenInstanceError

        t = UploadTicket(url="u", fields={}, s3_key="k", expires_in_seconds=60)
        with pytest.raises(FrozenInstanceError):
            t.url = "other"  # type: ignore[misc]

    def test_object_metadata_optional_fields_default_none(self) -> None:
        m = ObjectMetadata(key="k", size_bytes=100)
        assert m.content_type is None
        assert m.etag is None


# ---------------------------------------------------------------------------
# DSL field binding
# ---------------------------------------------------------------------------


class TestStorageFieldBinding:
    def test_file_field_with_storage_attribute(self) -> None:
        dsl = """
module test
app A "A"

entity Doc:
  id: uuid pk
  source_pdf_url: file storage=cohort_pdfs
  thumbnail_url: file
  notes: str(200)
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        e = fragment.entities[0]
        fields = {f.name: f for f in e.fields}
        assert fields["source_pdf_url"].storage == ("cohort_pdfs",)
        # Non-storage file field still parses; .storage is the empty tuple.
        assert fields["thumbnail_url"].storage == ()
        # Non-file fields don't acquire storage bindings.
        assert fields["notes"].storage == ()

    def test_storage_with_other_modifiers(self) -> None:
        """`storage=` composes with `required` and other modifiers
        on the same line."""
        dsl = """
module test
app A "A"

entity Doc:
  id: uuid pk
  source_pdf_url: file required storage=cohort_pdfs
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        f = fragment.entities[0].fields[1]
        assert f.storage == ("cohort_pdfs",)
        assert f.is_required

    def test_duplicate_storage_rejected(self) -> None:
        from dazzle.core.errors import ParseError

        dsl = """
module test
app A "A"

entity Doc:
  id: uuid pk
  source_pdf_url: file storage=a storage=b
"""
        with pytest.raises(ParseError, match="Duplicate `storage="):
            parse_dsl(dsl, Path("test.dsl"))


# ---------------------------------------------------------------------------
# StorageConfig dataclass surface
# ---------------------------------------------------------------------------


class TestStorageConfigDataclass:
    def test_frozen(self) -> None:
        from dataclasses import FrozenInstanceError

        cfg = StorageConfig(
            name="x", backend="s3", bucket="b", region="r", prefix_template="p/", max_bytes=1
        )
        with pytest.raises(FrozenInstanceError):
            cfg.bucket = "other"  # type: ignore[misc]

    def test_equality_by_value(self) -> None:
        a = StorageConfig(
            name="x", backend="s3", bucket="b", region="r", prefix_template="p/", max_bytes=1
        )
        b = StorageConfig(
            name="x", backend="s3", bucket="b", region="r", prefix_template="p/", max_bytes=1
        )
        assert a == b
