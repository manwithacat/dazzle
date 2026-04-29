"""Storage layer for browser-direct uploads (#932, Part 1 of N).

Cycle 1 ships the *protocol* + the env-var interpolation helper. The
real S3 implementation, the in-memory fake, and the upload-ticket /
finalize routes land in cycle 2+.

Public API::

    from dazzle_back.runtime.storage import (
        StorageProvider,
        UploadTicket,
        ObjectMetadata,
        interpolate_env_vars,
    )

The protocol is intentionally tight — four methods + four config
attributes — so a third-party backend (R2, MinIO, GCS) can drop in
behind a 50-line subclass.
"""

from .env_vars import (
    EnvVarMissingError,
    extract_env_var_refs,
    interpolate_env_vars,
)
from .protocol import (
    ObjectMetadata,
    StorageProvider,
    UploadTicket,
)
from .proxy_routes import register_storage_proxy_routes
from .registry import StorageRegistry
from .routes import register_upload_ticket_routes
from .testing import FakeStorageProvider
from .verify import (
    StorageVerificationError,
    build_entity_storage_bindings,
    verify_storage_field_keys,
)

__all__ = [
    "EnvVarMissingError",
    "FakeStorageProvider",
    "ObjectMetadata",
    "StorageProvider",
    "StorageRegistry",
    "StorageVerificationError",
    "UploadTicket",
    "build_entity_storage_bindings",
    "extract_env_var_refs",
    "interpolate_env_vars",
    "register_storage_proxy_routes",
    "register_upload_ticket_routes",
    "verify_storage_field_keys",
]
