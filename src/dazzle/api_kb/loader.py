"""
API Knowledgebase loader - loads and queries API packs.

Packs are TOML files containing pre-validated API configurations.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class EnvVarSpec:
    """Specification for an environment variable."""

    name: str
    required: bool = True
    description: str = ""
    example: str = ""

    def to_env_example_line(self) -> str:
        """Generate a line for .env.example file."""
        comment = f"# {self.description}" if self.description else ""
        example_value = self.example or ""
        return f"{comment}\n{self.name}={example_value}" if comment else f"{self.name}={example_value}"


@dataclass
class OperationSpec:
    """Specification for an API operation."""

    name: str
    method: str
    path: str
    description: str = ""
    request_schema: dict[str, Any] = field(default_factory=dict)
    response_schema: dict[str, Any] = field(default_factory=dict)


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

    def to_dsl_auth_profile(self) -> str:
        """Generate DSL auth_profile declaration."""
        if self.auth_type == "api_key":
            parts = ['api_key']
            if self.header:
                parts.append(f'header="{self.header}"')
            if self.env_var:
                parts.append(f'key_env="{self.env_var}"')
            return " ".join(parts)
        elif self.auth_type == "oauth2":
            parts = ["oauth2"]
            if self.env_var:
                # Convention: CLIENT_ID and CLIENT_SECRET derived from base env var
                base = self.env_var.replace("_CLIENT_ID", "").replace("_CLIENT_SECRET", "")
                parts.append(f'client_id_env="{base}_CLIENT_ID"')
                parts.append(f'client_secret_env="{base}_CLIENT_SECRET"')
            if self.token_url:
                parts.append(f'token_url="{self.token_url}"')
            return " ".join(parts)
        elif self.auth_type == "bearer":
            parts = ["bearer"]
            if self.env_var:
                parts.append(f'token_env="{self.env_var}"')
            return " ".join(parts)
        elif self.auth_type == "basic":
            parts = ["basic"]
            if self.env_var:
                base = self.env_var.replace("_USER", "").replace("_PASS", "")
                parts.append(f'username_env="{base}_USER"')
                parts.append(f'password_env="{base}_PASS"')
            return " ".join(parts)
        else:
            return "none"


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

    def generate_env_example(self) -> str:
        """Generate .env.example content for this pack."""
        lines = [f"# {self.provider} ({self.name} pack)"]
        for env_var in self.env_vars:
            lines.append(env_var.to_env_example_line())
        return "\n".join(lines)

    def generate_service_dsl(self) -> str:
        """Generate DSL service block for this pack.

        Note: The parser requires spec: and auth_profile: directives.
        Uses inline spec with pack reference for traceability.
        """
        lines = [f'service {self.name.replace("_", "")} "{self.provider}":']
        # Use inline spec with pack name for documentation
        lines.append(f'  spec: inline "pack:{self.name}"')
        if self.auth:
            lines.append(f'  auth_profile: {self.auth.to_dsl_auth_profile()}')
        if self.docs_url:
            lines.append(f'  # Docs: {self.docs_url}')
        return "\n".join(lines)

    def generate_foreign_model_dsl(self, model: ForeignModelSpec) -> str:
        """Generate DSL foreign_model block for a model."""
        service_name = self.name.replace("_", "")
        lines = [f'foreign_model {model.name} from {service_name} "{model.description}":']
        lines.append(f'  key: {model.key_field}')
        if model.cache_ttl:
            lines.append(f'  constraint cache ttl="{model.cache_ttl}"')
        lines.append("")
        for field_name, field_spec in model.fields.items():
            field_type = field_spec.get("type", "str")
            modifiers = []
            if field_spec.get("required"):
                modifiers.append("required")
            if field_spec.get("pk"):
                modifiers.append("pk")
            modifier_str = " " + " ".join(modifiers) if modifiers else ""
            lines.append(f"  {field_name}: {field_type}{modifier_str}")
        return "\n".join(lines)


# Module-level cache for loaded packs
_pack_cache: dict[str, ApiPack] = {}
_packs_loaded = False


def _get_packs_dir() -> Path:
    """Get the directory containing API pack definitions."""
    return Path(__file__).parent


def _load_pack_from_toml(toml_path: Path) -> ApiPack:
    """Load a single pack from a TOML file."""
    with open(toml_path, "rb") as f:
        data = tomllib.load(f)

    pack_info = data.get("pack", {})

    # Parse auth
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

    # Parse env vars
    env_vars = []
    for name, spec in data.get("env_vars", {}).items():
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

    # Parse operations
    operations = []
    for op_name, op_spec in data.get("operations", {}).items():
        if isinstance(op_spec, dict):
            operations.append(
                OperationSpec(
                    name=op_name,
                    method=op_spec.get("method", "GET"),
                    path=op_spec.get("path", ""),
                    description=op_spec.get("description", ""),
                    request_schema=op_spec.get("request_schema", {}),
                    response_schema=op_spec.get("response_schema", {}),
                )
            )

    # Parse foreign models
    foreign_models = []
    for model_name, model_spec in data.get("foreign_models", {}).items():
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

    return ApiPack(
        name=pack_info.get("name", toml_path.stem),
        provider=pack_info.get("provider", ""),
        category=pack_info.get("category", ""),
        version=pack_info.get("version", ""),
        description=pack_info.get("description", ""),
        base_url=pack_info.get("base_url", ""),
        docs_url=pack_info.get("docs_url", ""),
        auth=auth,
        env_vars=env_vars,
        operations=operations,
        foreign_models=foreign_models,
    )


def _discover_packs() -> None:
    """Discover all available packs in the api_kb directory."""
    global _packs_loaded, _pack_cache

    if _packs_loaded:
        return

    packs_dir = _get_packs_dir()
    for provider_dir in packs_dir.iterdir():
        if provider_dir.is_dir() and not provider_dir.name.startswith("_"):
            for toml_file in provider_dir.glob("*.toml"):
                try:
                    pack = _load_pack_from_toml(toml_file)
                    _pack_cache[pack.name] = pack
                except Exception:
                    # Skip malformed packs
                    pass

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
        provider: Filter by provider name (e.g., "Stripe", "HMRC")
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


def get_all_env_vars() -> list[EnvVarSpec]:
    """
    Get all environment variables from all packs.

    Returns:
        Deduplicated list of all env vars across packs
    """
    _discover_packs()
    seen: set[str] = set()
    result: list[EnvVarSpec] = []

    for pack in _pack_cache.values():
        for env_var in pack.env_vars:
            if env_var.name not in seen:
                seen.add(env_var.name)
                result.append(env_var)

    return result


def generate_env_example(pack_names: list[str] | None = None) -> str:
    """
    Generate .env.example content for specified packs or all loaded packs.

    Args:
        pack_names: List of pack names, or None for all packs

    Returns:
        Combined .env.example content
    """
    _discover_packs()

    if pack_names is None:
        packs = list(_pack_cache.values())
    else:
        packs = [_pack_cache[name] for name in pack_names if name in _pack_cache]

    sections = []
    for pack in packs:
        if pack.env_vars:
            sections.append(pack.generate_env_example())

    return "\n\n".join(sections)
