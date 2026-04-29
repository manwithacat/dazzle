"""S3-backed `StorageProvider` implementation (#932 cycle 2).

Wraps `boto3.client("s3")` to mint presigned-POST tickets and verify
uploaded objects via `head_object`. The endpoint_url override on
`AWSConfig` (already shipped) means this same class works against
real AWS S3, MinIO, Cloudflare R2, and a moto / LocalStack server
without any extra plumbing.

The class is intentionally thin — every behaviour the framework
needs is one boto3 call, parameterised by the `StorageConfig` that
declared this storage. No state beyond the boto3 client itself.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .protocol import ObjectMetadata, UploadTicket

if TYPE_CHECKING:
    from dazzle.core.manifest import StorageConfig


class S3Provider:
    """`StorageProvider` backed by an S3-compatible store.

    The constructor takes a fully-resolved `StorageConfig` (env-var
    interpolation already applied) plus an optional pre-built boto3
    client. In production code the registry constructs the client
    from `dazzle_back.runtime.aws_config.AWSConfig`; tests inject a
    moto-backed client directly.
    """

    def __init__(
        self,
        config: StorageConfig,
        *,
        client: Any | None = None,
    ) -> None:
        self._config = config
        self._client = client
        # Mirror the protocol attributes from config so route
        # generators can read them off the provider directly.
        self.name = config.name
        self.bucket = config.bucket
        self.prefix_template = config.prefix_template
        self.max_bytes = config.max_bytes
        self.content_types = list(config.content_types)
        self.ticket_ttl_seconds = config.ticket_ttl_seconds

    @classmethod
    def from_config(cls, config: StorageConfig) -> S3Provider:
        """Build an `S3Provider` from a `StorageConfig`, resolving
        AWS credentials from `aws_config.get_aws_config()` and
        respecting any `endpoint_url` override declared on the
        config (R2 / MinIO / LocalStack)."""
        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:  # pragma: no cover — soft-required dep
            raise ImportError(
                "boto3 is required for S3 storage. Install with: pip install dazzle-dsl[aws]"
            ) from exc

        from dazzle_back.runtime.aws_config import get_aws_config

        aws_cfg = get_aws_config()
        kwargs: dict[str, Any] = {
            "region_name": config.region or aws_cfg.region,
            "config": Config(signature_version="s3v4"),
        }
        # Storage-config endpoint_url wins over global aws_config —
        # lets a project route different storages at different
        # backends (e.g. one bucket on real S3, one on R2).
        if config.endpoint_url:
            kwargs["endpoint_url"] = config.endpoint_url
        elif aws_cfg.endpoint_url:
            kwargs["endpoint_url"] = aws_cfg.endpoint_url
        if aws_cfg.access_key_id:
            kwargs["aws_access_key_id"] = aws_cfg.access_key_id
        if aws_cfg.secret_access_key:
            kwargs["aws_secret_access_key"] = aws_cfg.secret_access_key

        client = boto3.client("s3", **kwargs)
        return cls(config, client=client)

    # ── Protocol surface ──────────────────────────────────────────

    def render_prefix(self, *, user_id: str, record_id: str) -> str:
        """Substitute `{user_id}` / `{record_id}` placeholders.

        Other tokens (e.g. `{filename}`) pass through unchanged so
        a future framework version can extend the substitution set
        without breaking templates that contain stray braces.
        """
        return self.prefix_template.format(user_id=user_id, record_id=record_id)

    def mint_upload_ticket(
        self,
        *,
        key: str,
        content_type: str,
    ) -> UploadTicket:
        """Mint a presigned POST policy for `key`.

        The policy carries:
        - `Content-Type` field locked to `content_type`.
        - `content-length-range` condition between 1 byte and
          `self.max_bytes` — anything outside is rejected by S3.

        When `self.content_types` is non-empty the caller is
        responsible for verifying `content_type` is in that allowlist
        before calling this; we take their word for it (the policy
        encodes the SAME content type they passed in).
        """
        if self._client is None:
            raise RuntimeError(
                "S3Provider initialised without a client; "
                "use S3Provider.from_config() in production"
            )
        ticket = self._client.generate_presigned_post(
            Bucket=self.bucket,
            Key=key,
            Fields={"Content-Type": content_type},
            Conditions=[
                {"Content-Type": content_type},
                ["content-length-range", 1, self.max_bytes],
            ],
            ExpiresIn=self.ticket_ttl_seconds,
        )
        return UploadTicket(
            url=ticket["url"],
            fields=dict(ticket["fields"]),
            s3_key=key,
            expires_in_seconds=self.ticket_ttl_seconds,
        )

    def head_object(self, key: str) -> ObjectMetadata | None:
        """Return metadata for `key`, or None if the object doesn't
        exist. Any S3 error other than 404 propagates so the route
        generator can map it to a 5xx response."""
        if self._client is None:
            raise RuntimeError(
                "S3Provider initialised without a client; "
                "use S3Provider.from_config() in production"
            )
        try:
            head = self._client.head_object(Bucket=self.bucket, Key=key)
        except Exception as exc:
            # boto3's ClientError carries `response['Error']['Code']`.
            # Match the shape without importing botocore at module
            # load (keeps the soft-dep boundary).
            response = getattr(exc, "response", None)
            if isinstance(response, dict):
                code = response.get("Error", {}).get("Code")
                if code in {"404", "NoSuchKey", "NotFound"}:
                    return None
            raise
        return ObjectMetadata(
            key=key,
            size_bytes=int(head.get("ContentLength", 0)),
            content_type=head.get("ContentType"),
            etag=str(head["ETag"]).strip('"') if head.get("ETag") else None,
        )

    def get_object(self, key: str) -> bytes | None:
        """Fetch the full body of `key`, or None if missing. Buffers
        in memory — fine for the 200MB cap most projects use; if a
        future use case needs gigabyte-scale streaming, a separate
        ``stream_object`` method can land alongside without touching
        this one."""
        if self._client is None:
            raise RuntimeError(
                "S3Provider initialised without a client; "
                "use S3Provider.from_config() in production"
            )
        try:
            obj = self._client.get_object(Bucket=self.bucket, Key=key)
        except Exception as exc:
            response = getattr(exc, "response", None)
            if isinstance(response, dict):
                code = response.get("Error", {}).get("Code")
                if code in {"404", "NoSuchKey", "NotFound"}:
                    return None
            raise
        body = obj.get("Body")
        if body is None:
            return b""
        result: bytes = body.read()
        return result
