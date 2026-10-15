"""
API Knowledgebase loader - loads and queries API packs.

Packs are TOML files containing pre-validated API configurations.
"""

from __future__ import annotations  # required: forward reference

import logging
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class EnvVarSpec:
    """Specification for an environment variable."""

    name: str
    required: bool = True
    description: str = ""
    example: str = ""


@dataclass
class OperationSpec:
    """Specification for an API operation."""

    name: str
    method: str
    path: str
    description: str = ""
    request_schema: dict[str, Any] = field(default_factory=dict)
    response_schema: dict[str, Any] = field(default_factory=dict)
    # Fragment / search_select keys (search vs detail may differ from foreign model).
    # e.g. display_key, value_key, secondary_key, items_key, query_param, detail_url
    fragment: dict[str, Any] = field(default_factory=dict)
    # API response field → canonical/foreign-model field (e.g. title → company_name).
    # Applied by fragment_routes before display_key / autofill lookup.
    field_map: dict[str, str] = field(default_factory=dict)


@dataclass
class ForeignModelSpec:
    """Specification for a foreign model from an external API."""

    name: str
    description: str = ""
    key_field: str = "id"
    cache_ttl: int | None = None
    fields: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class AuthSpec:
    """Authentication specification for an API."""

    auth_type: str  # api_key, oauth2, basic, bearer
    header: str | None = None
    prefix: str | None = None
    env_var: str | None = None
    token_url: str | None = None
    scopes: list[str] = field(default_factory=list)


@dataclass
class SandboxSpec:
    """Sandbox/test mode specification."""

    available: bool = False
    env_prefix: str = ""
    docs: str = ""


@dataclass
class InfrastructureSpec:
    """Infrastructure provisioning metadata for an API pack.

    Describes how to provision and run the service locally,
    whether it's cloud-only, self-hosted, or both.
    """

    hosting: str = "cloud_only"  # cloud_only, self_hosted, both
    local_env_overrides: dict[str, str] = field(default_factory=dict)
    sandbox: SandboxSpec | None = None


@dataclass
class ApiPack:
    """A complete API pack configuration."""

    name: str
    provider: str
    category: str
    version: str
    description: str = ""
    base_url: str = ""
    docs_url: str = ""
    auth: AuthSpec | None = None
    env_vars: list[EnvVarSpec] = field(default_factory=list)
    operations: list[OperationSpec] = field(default_factory=list)
    foreign_models: list[ForeignModelSpec] = field(default_factory=list)
    infrastructure: InfrastructureSpec | None = None

    def generate_fragment_source(self, operation: str, **overrides: Any) -> dict[str, Any]:
        """Convert a pack operation into a fragment source config dict.

        Produces the dict shape expected by ``create_fragment_router()``:
        ``url``, ``display_key``, ``value_key``, ``secondary_key``, ``headers``,
        ``query_param``, ``items_key``, ``autofill``.

        Args:
            operation: Name of the operation (e.g. ``"search_companies"``).
            **overrides: Override any inferred key (``display_key``, ``value_key``,
                ``secondary_key``, ``items_key``, ``query_param``, ``autofill``).

        Returns:
            Config dict ready for ``create_fragment_router()``.

        Raises:
            ValueError: If the operation is not found in this pack.
        """
        op = next((o for o in self.operations if o.name == operation), None)
        if op is None:
            raise ValueError(f"Operation '{operation}' not found in pack '{self.name}'")

        url = f"{self.base_url.rstrip('/')}{op.path}"

        # Build auth headers
        headers: dict[str, str] = {}
        if self.auth:
            if self.auth.auth_type == "basic" and self.auth.env_var:
                import base64
                import os

                api_key = os.environ.get(self.auth.env_var, "")
                encoded = base64.b64encode(f"{api_key}:".encode()).decode()
                headers[self.auth.header or "Authorization"] = f"Basic {encoded}"
            elif self.auth.auth_type == "api_key" and self.auth.env_var:
                import os

                api_key = os.environ.get(self.auth.env_var, "")
                prefix = self.auth.prefix or ""
                if prefix == "Basic":
                    import base64

                    encoded = base64.b64encode(f"{api_key}:".encode()).decode()
                    headers[self.auth.header or "Authorization"] = f"Basic {encoded}"
                elif prefix:
                    headers[self.auth.header or "Authorization"] = f"{prefix} {api_key}"
                else:
                    headers[self.auth.header or "Authorization"] = api_key
            elif self.auth.auth_type == "bearer" and self.auth.env_var:
                import os

                token = os.environ.get(self.auth.env_var, "")
                headers["Authorization"] = f"Bearer {token}"

        # Infer display/value keys from the first foreign model, then layer
        # per-operation fragment keys (search APIs often use different shapes
        # than profile/detail — e.g. Companies House search `title` vs profile
        # `company_name`). Explicit op.fragment wins over inference.
        display_key = "name"
        value_key = "id"
        secondary_key = ""
        if self.foreign_models:
            fm = self.foreign_models[0]
            value_key = fm.key_field
            # Prefer canonical foreign-model names; field_map remaps API → these.
            for candidate in ("name", "company_name", "title", "label", "description"):
                if candidate in fm.fields:
                    display_key = candidate
                    break
            for candidate in ("company_number", "status", "company_status", "type", "category"):
                if candidate in fm.fields and candidate != display_key:
                    secondary_key = candidate
                    break

        result: dict[str, Any] = {
            "url": url,
            "display_key": display_key,
            "value_key": value_key,
            "secondary_key": secondary_key,
            "headers": headers,
            "query_param": "q",
            "items_key": "items",
            "autofill": {},
        }
        # Per-op fragment config (search_display_key / detail keys / etc.)
        frag = op.fragment or {}
        for key in (
            "display_key",
            "value_key",
            "secondary_key",
            "items_key",
            "query_param",
            "detail_url",
            "autofill",
        ):
            if key in frag and frag[key] is not None:
                result[key] = frag[key]
        if op.field_map:
            result["field_map"] = dict(op.field_map)
        result.update(overrides)
        return result


def _get_packs_dir() -> Path:
    """Get the directory containing built-in API pack definitions."""
    return Path(__file__).parent


# Module-level pack registry (#1616) — no MCP dependency. Dual-lock installs
# without the mcp extra must still resolve companies_house_lookup etc.
_pack_cache: dict[str, ApiPack] = {}
_packs_loaded: bool = False
_pack_project_root: Path | None = None


def set_pack_project_root(path: Path | None) -> None:
    """Point discovery at a project root (optional local ``.dazzle/api_packs``).

    Clears the pack cache so the next ``load_pack`` rediscovers. Called from
    HTTP boot and MCP ``set_project_root`` when available.
    """
    global _pack_project_root, _packs_loaded, _pack_cache
    _pack_project_root = path.resolve() if path is not None else None
    _packs_loaded = False
    _pack_cache = {}


def _resolve_project_root() -> Path:
    if _pack_project_root is not None:
        return _pack_project_root
    return Path.cwd()


def _parse_operations(raw: dict[str, Any]) -> list[OperationSpec]:
    """Parse operations tables, including fragment keys and field_map aliases."""
    operations: list[OperationSpec] = []
    for op_name, op_spec in raw.items():
        if not isinstance(op_spec, dict):
            continue
        frag_raw = op_spec.get("fragment") or {}
        fragment: dict[str, Any] = dict(frag_raw) if isinstance(frag_raw, dict) else {}
        map_raw = op_spec.get("field_map") or {}
        field_map: dict[str, str] = (
            {str(k): str(v) for k, v in map_raw.items()} if isinstance(map_raw, dict) else {}
        )
        operations.append(
            OperationSpec(
                name=op_name,
                method=op_spec.get("method", "GET"),
                path=op_spec.get("path", ""),
                description=op_spec.get("description", ""),
                request_schema=op_spec.get("request_schema", {}),
                response_schema=op_spec.get("response_schema", {}),
                fragment=fragment,
                field_map=field_map,
            )
        )
    return operations


def _parse_env_vars(raw: dict[str, Any]) -> list[EnvVarSpec]:
    env_vars: list[EnvVarSpec] = []
    for name, spec in raw.items():
        if isinstance(spec, dict):
            env_vars.append(
                EnvVarSpec(
                    name=name,
                    required=spec.get("required", True),
                    description=spec.get("description", ""),
                    example=spec.get("example", ""),
                )
            )
        else:
            env_vars.append(EnvVarSpec(name=name, description=str(spec)))
    return env_vars


def _parse_foreign_models(raw: dict[str, Any]) -> list[ForeignModelSpec]:
    foreign_models: list[ForeignModelSpec] = []
    for model_name, model_spec in raw.items():
        if isinstance(model_spec, dict):
            foreign_models.append(
                ForeignModelSpec(
                    name=model_name,
                    description=model_spec.get("description", ""),
                    key_field=model_spec.get("key", "id"),
                    cache_ttl=model_spec.get("cache_ttl"),
                    fields=model_spec.get("fields", {}),
                )
            )
    return foreign_models


def _parse_infrastructure(infra_data: dict[str, Any]) -> InfrastructureSpec | None:
    if not infra_data:
        return None
    sandbox_data = infra_data.get("sandbox", {})
    sandbox = None
    if sandbox_data:
        sandbox = SandboxSpec(
            available=sandbox_data.get("available", False),
            env_prefix=sandbox_data.get("env_prefix", ""),
            docs=sandbox_data.get("docs", ""),
        )
    return InfrastructureSpec(
        hosting=infra_data.get("hosting", "cloud_only"),
        local_env_overrides=infra_data.get("local_env_overrides", {}),
        sandbox=sandbox,
    )


def _load_pack_from_toml(toml_path: Path) -> ApiPack:
    """Load a single pack from a TOML file."""
    with open(toml_path, "rb") as f:
        data = tomllib.load(f)

    pack_info = data.get("pack", {})

    auth_data = data.get("auth", {})
    auth = None
    if auth_data:
        auth = AuthSpec(
            auth_type=auth_data.get("type", "none"),
            header=auth_data.get("header"),
            prefix=auth_data.get("prefix"),
            env_var=auth_data.get("env_var"),
            token_url=auth_data.get("token_url"),
            scopes=auth_data.get("scopes", []),
        )

    return ApiPack(
        name=pack_info.get("name", toml_path.stem),
        provider=pack_info.get("provider", ""),
        category=pack_info.get("category", ""),
        version=pack_info.get("version", ""),
        description=pack_info.get("description", ""),
        base_url=pack_info.get("base_url", ""),
        docs_url=pack_info.get("docs_url", ""),
        auth=auth,
        env_vars=_parse_env_vars(data.get("env_vars", {})),
        operations=_parse_operations(data.get("operations", {})),
        foreign_models=_parse_foreign_models(data.get("foreign_models", {})),
        infrastructure=_parse_infrastructure(data.get("infrastructure", {})),
    )


def _collect_packs_from_dir(packs_dir: Path, into: dict[str, ApiPack]) -> None:
    """Collect packs from a single directory tree into a local dict (provider/name.toml)."""
    if not packs_dir.is_dir():
        return
    for provider_dir in packs_dir.iterdir():
        if provider_dir.is_dir() and not provider_dir.name.startswith("_"):
            for toml_file in provider_dir.glob("*.toml"):
                try:
                    pack = _load_pack_from_toml(toml_file)
                    # Don't overwrite — first-discovered wins (project-local first)
                    if pack.name not in into:
                        into[pack.name] = pack
                except Exception:
                    logger.warning("Failed to load API pack from %s", toml_file, exc_info=True)


def _discover_packs() -> None:
    """Discover all available packs (project-local first, then built-in).

    #1616: pure path — no ``dazzle.mcp`` import. HTTP dual-lock pins without
    the mcp extra must still resolve ``companies_house_lookup`` etc.
    """
    global _pack_cache, _packs_loaded
    if _packs_loaded:
        return

    new_cache: dict[str, ApiPack] = {}

    # Project-local packs take priority
    project_packs_dir = _resolve_project_root() / ".dazzle" / "api_packs"
    _collect_packs_from_dir(project_packs_dir, new_cache)

    # Built-in packs (won't overwrite project-local ones with same name)
    _collect_packs_from_dir(_get_packs_dir(), new_cache)

    _pack_cache = new_cache
    _packs_loaded = True


def load_pack(pack_name: str) -> ApiPack | None:
    """
    Load a specific API pack by name.

    Args:
        pack_name: The pack name (e.g., "stripe_payments")

    Returns:
        The ApiPack if found, None otherwise
    """
    _discover_packs()
    return _pack_cache.get(pack_name)


def list_packs() -> list[ApiPack]:
    """
    List all available API packs.

    Returns:
        List of all discovered ApiPacks
    """
    _discover_packs()
    return list(_pack_cache.values())


def search_packs(
    category: str | None = None,
    provider: str | None = None,
    query: str | None = None,
) -> list[ApiPack]:
    """
    Search for API packs by category, provider, or text query.

    Args:
        category: Filter by category (e.g., "payments", "accounting")
        provider: Filter by provider name (e.g., "Stripe", "Companies House")
        query: Text search in name, provider, description

    Returns:
        List of matching ApiPacks
    """
    _discover_packs()
    results = list(_pack_cache.values())

    if category:
        category_lower = category.lower()
        results = [p for p in results if p.category.lower() == category_lower]

    if provider:
        provider_lower = provider.lower()
        results = [p for p in results if p.provider.lower() == provider_lower]

    if query:
        query_lower = query.lower()
        results = [
            p
            for p in results
            if query_lower in p.name.lower()
            or query_lower in p.provider.lower()
            or query_lower in p.description.lower()
        ]

    return results
