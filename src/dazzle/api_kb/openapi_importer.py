"""
OpenAPI to API pack TOML converter.

Converts OpenAPI 3.x specifications into Dazzle API pack TOML format,
and generates blank scaffold templates for new packs.
"""

from __future__ import annotations

import re
from typing import Any


def scaffold_blank(provider: str, category: str, pack_name: str) -> str:
    """Generate a minimal pack TOML template with placeholders.

    Args:
        provider: Provider name (e.g. "Acme").
        category: Pack category (e.g. "payments").
        pack_name: Pack name (e.g. "acme_payments").

    Returns:
        TOML string with placeholder sections.
    """
    return f'''# {provider} {category.title()} Pack
# Auto-generated template — fill in operations and models

[pack]
name = "{pack_name}"
provider = "{provider}"
category = "{category}"
version = "1.0"
description = ""
base_url = ""
docs_url = ""

[auth]
type = "api_key"
header = "Authorization"
prefix = "Bearer"
env_var = "{provider.upper()}_API_KEY"

[env_vars]
{provider.upper()}_API_KEY = {{ required = true, description = "{provider} API key", example = "" }}

# Add operations here:
# [operations]
# list_items = {{ method = "GET", path = "/items", description = "List all items" }}

# Add foreign models here:
# [foreign_models.Item]
# description = "An item"
# key = "id"
#
# [foreign_models.Item.fields]
# id = {{ type = "str(50)", required = true, pk = true }}
# name = {{ type = "str(200)" }}

# Add webhook events here:
# [webhooks.item_created]
# description = "Item was created"
# signing = "hmac-sha256"
# signing_header = "X-Webhook-Signature"
# webhook_path = "/webhooks/{pack_name}"
'''


def import_from_openapi(spec: dict[str, Any]) -> str:
    """Convert an OpenAPI 3.x spec dict to pack TOML string.

    Extracts:
    - Pack metadata from ``info`` (title, description, version)
    - ``base_url`` from ``servers[0].url``
    - Auth from ``components.securitySchemes``
    - Operations from ``paths`` (method + path + summary)
    - Foreign models from ``components.schemas`` (top-level object schemas)
    - Env vars inferred from security scheme requirements

    Args:
        spec: Parsed OpenAPI 3.x spec dictionary.

    Returns:
        TOML-formatted string representing the API pack.
    """
    info = spec.get("info", {})
    title = info.get("title", "API")
    description = info.get("description", "")
    version = info.get("version", "1.0")

    # Derive provider and pack name from title
    provider = _clean_identifier(title)
    pack_name = _to_snake(provider)
    category = "api"

    # Base URL from servers
    servers = spec.get("servers", [])
    base_url = servers[0].get("url", "") if servers else ""

    lines: list[str] = []
    lines.append(f"# {title} Pack")
    lines.append(f"# Auto-generated from OpenAPI spec v{version}")
    lines.append("")
    lines.append("[pack]")
    lines.append(f'name = "{pack_name}"')
    lines.append(f'provider = "{title}"')
    lines.append(f'category = "{category}"')
    lines.append(f'version = "{version}"')
    lines.append(f'description = "{_escape_toml(description[:200])}"')
    lines.append(f'base_url = "{base_url}"')
    lines.append("")

    # Auth
    security_schemes = spec.get("components", {}).get("securitySchemes", {})
    auth_lines, env_var_lines = _extract_auth(security_schemes, provider)
    if auth_lines:
        lines.extend(auth_lines)
        lines.append("")
    if env_var_lines:
        lines.append("[env_vars]")
        lines.extend(env_var_lines)
        lines.append("")

    # Operations from paths
    operations = _extract_operations(spec.get("paths", {}))
    if operations:
        lines.append("[operations]")
        for op in operations:
            desc = _escape_toml(op["description"])
            lines.append(
                f'{op["name"]} = {{ method = "{op["method"]}", '
                f'path = "{op["path"]}", '
                f'description = "{desc}" }}'
            )
        lines.append("")

    # Foreign models from schemas
    schemas = spec.get("components", {}).get("schemas", {})
    model_blocks = _extract_models(schemas)
    for block in model_blocks:
        lines.extend(block)
        lines.append("")

    return "\n".join(lines)


def _clean_identifier(text: str) -> str:
    """Clean a string to use as an identifier."""
    # Remove version suffixes, special chars
    cleaned = re.sub(r"[^a-zA-Z0-9\s]", "", text)
    return cleaned.strip()


def _to_snake(text: str) -> str:
    """Convert text to snake_case identifier."""
    # Insert underscores at camelCase boundaries (e.g. listPets -> list_Pets)
    result = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", text)
    # Replace spaces and special chars with underscores
    result = re.sub(r"[^a-zA-Z0-9]", "_", result.lower())
    result = re.sub(r"_+", "_", result)
    return result.strip("_")


def _escape_toml(text: str) -> str:
    """Escape a string for TOML value."""
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def _extract_auth(schemes: dict[str, Any], provider: str) -> tuple[list[str], list[str]]:
    """Extract auth config and env vars from security schemes."""
    auth_lines: list[str] = []
    env_lines: list[str] = []

    if not schemes:
        return auth_lines, env_lines

    # Pick the first scheme
    scheme_name, scheme = next(iter(schemes.items()))
    scheme_type = scheme.get("type", "")

    if scheme_type == "apiKey":
        auth_lines.append("[auth]")
        auth_lines.append('type = "api_key"')
        header = scheme.get("name", "Authorization")
        auth_lines.append(f'header = "{header}"')
        env_var = f"{provider.upper()}_API_KEY"
        auth_lines.append(f'env_var = "{env_var}"')
        env_lines.append(
            f'{env_var} = {{ required = true, description = "{provider} API key", example = "" }}'
        )

    elif scheme_type == "http":
        http_scheme = scheme.get("scheme", "bearer")
        if http_scheme == "bearer":
            auth_lines.append("[auth]")
            auth_lines.append('type = "bearer"')
            env_var = f"{provider.upper()}_TOKEN"
            auth_lines.append(f'env_var = "{env_var}"')
            env_lines.append(
                f'{env_var} = {{ required = true, description = "{provider} bearer token", example = "" }}'
            )
        elif http_scheme == "basic":
            auth_lines.append("[auth]")
            auth_lines.append('type = "basic"')
            env_var = f"{provider.upper()}_AUTH"
            auth_lines.append(f'env_var = "{env_var}"')
            env_lines.append(
                f'{provider.upper()}_USER = {{ required = true, description = "Username", example = "" }}'
            )
            env_lines.append(
                f'{provider.upper()}_PASS = {{ required = true, description = "Password", example = "" }}'
            )

    elif scheme_type == "oauth2":
        auth_lines.append("[auth]")
        auth_lines.append('type = "oauth2"')
        flows = scheme.get("flows", {})
        cc = flows.get("clientCredentials", {})
        token_url = cc.get("tokenUrl", "")
        if token_url:
            auth_lines.append(f'token_url = "{token_url}"')
        env_var = f"{provider.upper()}_OAUTH"
        auth_lines.append(f'env_var = "{env_var}"')
        env_lines.append(
            f'{provider.upper()}_CLIENT_ID = {{ required = true, description = "OAuth client ID", example = "" }}'
        )
        env_lines.append(
            f'{provider.upper()}_CLIENT_SECRET = {{ required = true, description = "OAuth client secret", example = "" }}'
        )

    return auth_lines, env_lines


def _extract_operations(paths: dict[str, Any]) -> list[dict[str, str]]:
    """Extract operations from OpenAPI paths."""
    ops: list[dict[str, str]] = []
    for path, methods in paths.items():
        if not isinstance(methods, dict):
            continue
        for method, details in methods.items():
            if method.lower() not in ("get", "post", "put", "patch", "delete"):
                continue
            if not isinstance(details, dict):
                continue
            op_id = details.get("operationId", "")
            if not op_id:
                # Generate from method + path
                op_id = _to_snake(f"{method}_{path}")
            summary = details.get("summary", details.get("description", ""))
            ops.append(
                {
                    "name": _to_snake(op_id),
                    "method": method.upper(),
                    "path": path,
                    "description": summary[:200] if summary else "",
                }
            )
    return ops


def _openapi_type_to_dsl(prop: dict[str, Any]) -> str:
    """Convert OpenAPI property type to DSL type string."""
    prop_type = prop.get("type", "string")
    prop_format = prop.get("format", "")

    if prop_type == "string":
        if prop_format == "date-time":
            return "datetime"
        elif prop_format == "date":
            return "date"
        elif prop_format == "email":
            return "email"
        elif prop_format == "uuid":
            return "uuid"
        max_len = prop.get("maxLength")
        if max_len:
            return f"str({max_len})"
        return "str"
    elif prop_type == "integer":
        return "int"
    elif prop_type == "number":
        return "decimal"
    elif prop_type == "boolean":
        return "bool"
    elif prop_type == "array":
        return "json"
    elif prop_type == "object":
        return "json"
    return "str"


def _extract_models(schemas: dict[str, Any]) -> list[list[str]]:
    """Extract foreign model blocks from OpenAPI schemas."""
    blocks: list[list[str]] = []
    for name, schema in schemas.items():
        if not isinstance(schema, dict):
            continue
        if schema.get("type") != "object":
            continue
        properties = schema.get("properties", {})
        if not properties:
            continue

        required_fields = set(schema.get("required", []))
        description = schema.get("description", f"A {name}")

        # Find key field
        key_field = "id"
        if "id" not in properties:
            # Use first field as key
            key_field = next(iter(properties))

        block: list[str] = []
        block.append(f"[foreign_models.{name}]")
        block.append(f'description = "{_escape_toml(description[:200])}"')
        block.append(f'key = "{key_field}"')
        block.append("")
        block.append(f"[foreign_models.{name}.fields]")

        for field_name, field_spec in properties.items():
            if not isinstance(field_spec, dict):
                continue
            dsl_type = _openapi_type_to_dsl(field_spec)
            field_desc = field_spec.get("description", "")
            parts: list[str] = [f'type = "{dsl_type}"']
            if field_name in required_fields:
                parts.append("required = true")
            if field_name == key_field:
                parts.append("pk = true")
            if field_desc:
                parts.append(f'description = "{_escape_toml(field_desc[:100])}"')
            block.append(f"{field_name} = {{ {', '.join(parts)} }}")

        blocks.append(block)

    return blocks
