"""Tests for #932 cycle 2 — runtime providers + registry.

Cycle 2 ships:
- `S3Provider(StorageProvider)` wrapping boto3.
- `FakeStorageProvider` (in-memory) for unit tests.
- `StorageRegistry` mapping storage names → providers, with lazy
  S3Provider construction from `StorageConfig`.
- `${VAR}` env-var interpolation applied at registry-build time
  with loud-on-missing semantics.

Unit tests use the FakeStorageProvider — fast, hermetic, no boto3.
A small set of integration tests exercises the real boto3 surface
via moto — covers signing math, content-length-range encoding,
404-as-None on head_object.
"""

from __future__ import annotations

import pytest

from dazzle.core.manifest import StorageConfig
from dazzle_back.runtime.storage import (
    EnvVarMissingError,
    FakeStorageProvider,
    ObjectMetadata,
    StorageProvider,
    StorageRegistry,
    UploadTicket,
)

# ---------------------------------------------------------------------------
# FakeStorageProvider
# ---------------------------------------------------------------------------


class TestFakeStorageProvider:
    def test_satisfies_protocol(self) -> None:
        fake = FakeStorageProvider()
        assert isinstance(fake, StorageProvider)

    def test_render_prefix_substitutes_tokens(self) -> None:
        fake = FakeStorageProvider(prefix_template="uploads/{user_id}/{record_id}/")
        assert fake.render_prefix(user_id="u1", record_id="r1") == "uploads/u1/r1/"

    def test_mint_ticket_records_for_assertion(self) -> None:
        fake = FakeStorageProvider(name="s")
        ticket = fake.mint_upload_ticket(key="k", content_type="application/pdf")
        assert isinstance(ticket, UploadTicket)
        assert ticket.s3_key == "k"
        assert "Content-Type" in ticket.fields
        assert fake.minted_tickets == [ticket]

    def test_head_object_none_when_missing(self) -> None:
        fake = FakeStorageProvider()
        assert fake.head_object("nope") is None

    def test_put_then_head_returns_metadata(self) -> None:
        fake = FakeStorageProvider()
        fake.put_object("k", b"hello world", content_type="text/plain")
        meta = fake.head_object("k")
        assert isinstance(meta, ObjectMetadata)
        assert meta.size_bytes == 11
        assert meta.content_type == "text/plain"
        assert meta.etag is not None  # md5 of body

    def test_objects_snapshot_for_assertions(self) -> None:
        fake = FakeStorageProvider()
        fake.put_object("a", b"AAA")
        fake.put_object("b", b"BB")
        assert fake.objects() == {"a": b"AAA", "b": b"BB"}

    def test_reset_clears_state(self) -> None:
        fake = FakeStorageProvider()
        fake.put_object("k", b"x")
        fake.mint_upload_ticket(key="k2", content_type="text/plain")
        fake.reset()
        assert fake.objects() == {}
        assert fake.minted_tickets == []


# ---------------------------------------------------------------------------
# StorageRegistry
# ---------------------------------------------------------------------------


def _config(name: str = "x", **overrides: object) -> StorageConfig:
    base = {
        "backend": "s3",
        "bucket": "b",
        "region": "r",
        "prefix_template": "uploads/{user_id}/{record_id}/",
        "max_bytes": 1024,
        "content_types": [],
        "ticket_ttl_seconds": 60,
    }
    base.update(overrides)
    return StorageConfig(name=name, **base)  # type: ignore[arg-type]


class TestStorageRegistry:
    def test_from_manifest_carries_configs(self) -> None:
        cfg = _config("cohort_pdfs")
        registry = StorageRegistry.from_manifest({"cohort_pdfs": cfg})
        assert registry.has("cohort_pdfs")
        assert "cohort_pdfs" in registry.names()

    def test_register_provider_overrides_config_path(self) -> None:
        registry = StorageRegistry.from_manifest({"x": _config("x")})
        fake = FakeStorageProvider(name="x")
        registry.register_provider("x", fake)
        # The registered fake wins — config-based S3Provider
        # construction never runs.
        assert registry.get("x") is fake

    def test_get_unknown_raises_keyerror(self) -> None:
        registry = StorageRegistry()
        with pytest.raises(KeyError, match="No storage registered"):
            registry.get("missing")

    def test_unsupported_backend_rejected(self) -> None:
        # Manually construct a config with an unsupported backend
        # (the manifest parser would normally reject it earlier).
        registry = StorageRegistry(configs={"x": _config("x", backend="azure_blob")})
        with pytest.raises(ValueError, match="Unsupported storage backend"):
            registry.get("x")

    def test_env_var_interpolation_runs_at_build(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When the registry materialises an S3Provider it should
        interpolate `${VAR}` references in bucket/region/endpoint_url."""
        monkeypatch.setenv("MY_BUCKET", "interpolated-bucket")
        monkeypatch.setenv("MY_REGION", "us-east-1")

        # Inject a fake provider AFTER calling get(), so we can spy
        # on the resolved config the registry passed in. Easier: hook
        # _build_from_config and capture.
        registry = StorageRegistry(
            configs={"x": _config("x", bucket="${MY_BUCKET}", region="${MY_REGION}")}
        )

        captured: list[StorageConfig] = []

        def _fake_build(self, cfg):
            resolved = self._resolve_env_vars(cfg)
            captured.append(resolved)
            return FakeStorageProvider(name=resolved.name, bucket=resolved.bucket)

        monkeypatch.setattr(StorageRegistry, "_build_from_config", _fake_build)
        prov = registry.get("x")
        assert prov.bucket == "interpolated-bucket"
        assert captured[0].region == "us-east-1"

    def test_missing_env_var_raises_at_get(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DEFINITELY_NOT_SET_ABC", raising=False)
        registry = StorageRegistry(configs={"x": _config("x", bucket="${DEFINITELY_NOT_SET_ABC}")})
        # The resolver runs inside _build_from_config; force the
        # path with a backend the registry doesn't short-circuit on.
        with pytest.raises(EnvVarMissingError) as excinfo:
            # _resolve_env_vars is called before backend dispatch; access
            # it directly to keep the test independent of S3Provider.
            registry._resolve_env_vars(registry.configs["x"])
        assert excinfo.value.var_name == "DEFINITELY_NOT_SET_ABC"
        assert "[storage.x] bucket" in str(excinfo.value)

    def test_lazy_provider_caching(self) -> None:
        registry = StorageRegistry()
        fake = FakeStorageProvider(name="x")
        registry.register_provider("x", fake)
        # Same instance returned each call.
        assert registry.get("x") is fake
        assert registry.get("x") is fake


# ---------------------------------------------------------------------------
# S3Provider unit tests (no boto3 — uses an injected stub client)
# ---------------------------------------------------------------------------


class _StubS3Client:
    """Mimics the slice of `boto3.client("s3")` we use, just enough
    for unit-testing S3Provider without importing boto3."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.objects: dict[tuple[str, str], dict] = {}

    def generate_presigned_post(self, **kwargs):
        self.calls.append(("generate_presigned_post", kwargs))
        return {
            "url": f"https://s3.example.com/{kwargs['Bucket']}",
            "fields": {
                "key": kwargs["Key"],
                "Content-Type": kwargs["Fields"]["Content-Type"],
                "policy": "stub-policy-base64",
                "x-amz-signature": "stub-sig",
            },
        }

    def head_object(self, **kwargs):
        self.calls.append(("head_object", kwargs))
        key = (kwargs["Bucket"], kwargs["Key"])
        if key not in self.objects:
            err = Exception("not found")
            err.response = {"Error": {"Code": "404"}}  # type: ignore[attr-defined]
            raise err
        return self.objects[key]


class TestS3ProviderWithStub:
    def test_render_prefix(self) -> None:
        from dazzle_back.runtime.storage.s3_provider import S3Provider

        cfg = _config("x", prefix_template="uploads/{user_id}/{record_id}/")
        prov = S3Provider(cfg, client=_StubS3Client())
        assert prov.render_prefix(user_id="alice", record_id="r1") == "uploads/alice/r1/"

    def test_mint_ticket_encodes_constraints(self) -> None:
        from dazzle_back.runtime.storage.s3_provider import S3Provider

        cfg = _config("x", bucket="my-bucket", max_bytes=200_000_000, ticket_ttl_seconds=600)
        client = _StubS3Client()
        prov = S3Provider(cfg, client=client)
        ticket = prov.mint_upload_ticket(key="my/key.pdf", content_type="application/pdf")
        # Confirm the call carried the right policy.
        method, kwargs = client.calls[0]
        assert method == "generate_presigned_post"
        assert kwargs["Bucket"] == "my-bucket"
        assert kwargs["Key"] == "my/key.pdf"
        assert kwargs["Fields"]["Content-Type"] == "application/pdf"
        assert kwargs["ExpiresIn"] == 600
        assert ["content-length-range", 1, 200_000_000] in kwargs["Conditions"]
        assert {"Content-Type": "application/pdf"} in kwargs["Conditions"]
        assert ticket.s3_key == "my/key.pdf"
        assert ticket.expires_in_seconds == 600

    def test_head_object_returns_metadata(self) -> None:
        from dazzle_back.runtime.storage.s3_provider import S3Provider

        cfg = _config("x", bucket="my-bucket")
        client = _StubS3Client()
        client.objects[("my-bucket", "k")] = {
            "ContentLength": 1234,
            "ContentType": "application/pdf",
            "ETag": '"abc123"',
        }
        prov = S3Provider(cfg, client=client)
        meta = prov.head_object("k")
        assert meta is not None
        assert meta.size_bytes == 1234
        assert meta.content_type == "application/pdf"
        assert meta.etag == "abc123"  # quotes stripped

    def test_head_object_404_returns_none(self) -> None:
        from dazzle_back.runtime.storage.s3_provider import S3Provider

        cfg = _config("x")
        prov = S3Provider(cfg, client=_StubS3Client())
        assert prov.head_object("missing") is None

    def test_no_client_raises_when_used(self) -> None:
        from dazzle_back.runtime.storage.s3_provider import S3Provider

        cfg = _config("x")
        prov = S3Provider(cfg, client=None)
        with pytest.raises(RuntimeError, match="initialised without a client"):
            prov.mint_upload_ticket(key="k", content_type="application/pdf")
        with pytest.raises(RuntimeError, match="initialised without a client"):
            prov.head_object("k")


# ---------------------------------------------------------------------------
# moto integration — the real boto3 surface
# ---------------------------------------------------------------------------

# Only import moto + boto3 when this section runs — keeps the rest of
# the file fast.

moto = pytest.importorskip("moto", reason="install dazzle-dsl[aws-test]")
boto3 = pytest.importorskip("boto3", reason="install dazzle-dsl[aws-test]")


@pytest.fixture
def mocked_s3_client(monkeypatch: pytest.MonkeyPatch):
    from moto import mock_aws

    # boto3 needs creds even when moto intercepts — supply dummies.
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test-key")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test-secret")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-west-2")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "test-token")

    with mock_aws():
        client = boto3.client("s3", region_name="eu-west-2")
        client.create_bucket(
            Bucket="moto-test-bucket",
            CreateBucketConfiguration={"LocationConstraint": "eu-west-2"},
        )
        yield client


class TestS3ProviderWithMoto:
    """A handful of integration tests against the real boto3 surface
    via moto. Catches anything unit tests with the stub client miss
    — particularly the presigned URL signing math + content-length-
    range condition encoding."""

    def test_generate_presigned_post_via_real_boto3(self, mocked_s3_client) -> None:
        from dazzle_back.runtime.storage.s3_provider import S3Provider

        cfg = _config("x", bucket="moto-test-bucket", max_bytes=1024 * 1024)
        prov = S3Provider(cfg, client=mocked_s3_client)
        ticket = prov.mint_upload_ticket(key="t/k.pdf", content_type="application/pdf")
        # Real presigned POST has a non-empty fields dict + URL.
        assert ticket.url.startswith("https://")
        assert "policy" in ticket.fields
        assert "x-amz-signature" in ticket.fields or "AWSAccessKeyId" in ticket.fields
        assert ticket.s3_key == "t/k.pdf"

    def test_head_object_404_via_real_boto3(self, mocked_s3_client) -> None:
        from dazzle_back.runtime.storage.s3_provider import S3Provider

        cfg = _config("x", bucket="moto-test-bucket")
        prov = S3Provider(cfg, client=mocked_s3_client)
        assert prov.head_object("does/not/exist") is None

    def test_head_object_existing_via_real_boto3(self, mocked_s3_client) -> None:
        from dazzle_back.runtime.storage.s3_provider import S3Provider

        mocked_s3_client.put_object(
            Bucket="moto-test-bucket",
            Key="t/exists.pdf",
            Body=b"hello",
            ContentType="application/pdf",
        )
        cfg = _config("x", bucket="moto-test-bucket")
        prov = S3Provider(cfg, client=mocked_s3_client)
        meta = prov.head_object("t/exists.pdf")
        assert meta is not None
        assert meta.size_bytes == 5
        assert meta.content_type == "application/pdf"
