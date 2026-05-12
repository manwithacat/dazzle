"""`StorageRegistry` — single source of truth for runtime providers (#932 cycle 2).

The registry holds one provider per `StorageConfig`. Cycle 3's
upload-ticket / finalize routes call `registry.get(name)` to look up
the provider for an entity field's `storage=` binding.

Lazy instantiation: the boto3 client for an `S3Provider` is created
the first time the storage is used, not at app startup. Lets a
project declare unused storages without paying boto3's import cost.

Tests: `register_provider(name, FakeStorageProvider(...))` overrides
the default S3-from-config behaviour. The route generator is
provider-agnostic — it sees only the `StorageProvider` protocol.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .protocol import StorageProvider

if TYPE_CHECKING:
    from dazzle.core.manifest import StorageConfig


@dataclass
class StorageRegistry:
    """Map of storage name → provider. Builds providers lazily from
    `StorageConfig`s as they're requested."""

    configs: dict[str, StorageConfig] = field(default_factory=dict)
    _providers: dict[str, StorageProvider] = field(default_factory=dict, repr=False)

    @classmethod
    def from_manifest(cls, storage_defs: dict[str, StorageConfig]) -> StorageRegistry:
        """Build a registry from `ProjectManifest.storage_defs`.

        Configs aren't materialised into providers here — that
        happens on first `get(name)` so unused storages don't
        trigger boto3 imports.
        """
        return cls(configs=dict(storage_defs))

    def register_provider(self, name: str, provider: StorageProvider) -> None:
        """Inject a provider directly, bypassing config-based
        construction. Tests use this to wire a `FakeStorageProvider`."""
        self._providers[name] = provider

    def get(self, name: str) -> StorageProvider:
        """Return the provider for `name`. Builds it from
        `configs[name]` on first request. Raises KeyError if
        neither a registered provider nor a config exists for that
        name — callers should treat this as a 500-class internal
        error (the validator is supposed to catch unresolved
        references at startup)."""
        if name in self._providers:
            return self._providers[name]
        if name not in self.configs:
            raise KeyError(
                f"No storage registered for {name!r}. Declare [storage.{name}] in dazzle.toml."
            )
        provider = self._build_from_config(self.configs[name])
        self._providers[name] = provider
        return provider

    def has(self, name: str) -> bool:
        """True when `get(name)` would succeed (config or
        registered provider exists)."""
        return name in self._providers or name in self.configs

    def names(self) -> list[str]:
        """Sorted list of every storage name the registry knows
        about (configured or directly registered)."""
        return sorted(set(self._providers) | set(self.configs))

    # ── Internal: backend dispatch ────────────────────────────────

    def _build_from_config(self, config: StorageConfig) -> StorageProvider:
        """Map a config's `backend` field to a concrete provider
        class. v1 supports `s3` only; future backends slot in here."""
        from dazzle.core.manifest import StorageConfig as _SC  # local import for runtime types

        assert isinstance(config, _SC), "config must be a StorageConfig"
        if config.backend == "s3":
            from .s3_provider import S3Provider

            return S3Provider.from_config(self._resolve_env_vars(config))
        raise ValueError(
            f"Unsupported storage backend {config.backend!r} for [storage.{config.name}]. "
            f"Supported: s3"
        )

    def _resolve_env_vars(self, config: StorageConfig) -> StorageConfig:
        """Run `${VAR}` interpolation across the config's string
        fields, returning a new `StorageConfig`. Loud-on-missing —
        any unresolved var raises `EnvVarMissingError` with the
        config name in the context for diagnostics."""
        from dazzle.core.manifest import StorageConfig as _SC

        from .env_vars import interpolate_env_vars

        ctx_root = f"[storage.{config.name}]"
        return _SC(
            name=config.name,
            backend=config.backend,
            bucket=interpolate_env_vars(config.bucket, context=f"{ctx_root} bucket") or "",
            region=interpolate_env_vars(config.region, context=f"{ctx_root} region") or "",
            prefix_template=config.prefix_template,
            max_bytes=config.max_bytes,
            content_types=list(config.content_types),
            ticket_ttl_seconds=config.ticket_ttl_seconds,
            endpoint_url=interpolate_env_vars(
                config.endpoint_url, context=f"{ctx_root} endpoint_url"
            ),
        )
