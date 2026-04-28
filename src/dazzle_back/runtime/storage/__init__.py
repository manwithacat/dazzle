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
from .registry import StorageRegistry
from .testing import FakeStorageProvider

__all__ = [
    "EnvVarMissingError",
    "FakeStorageProvider",
    "ObjectMetadata",
    "StorageProvider",
    "StorageRegistry",
    "UploadTicket",
    "extract_env_var_refs",
    "interpolate_env_vars",
]
