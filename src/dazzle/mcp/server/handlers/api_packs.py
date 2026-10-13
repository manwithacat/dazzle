"""
API pack implementations behind the ``dazzle api-pack`` CLI.

DSL generation, env-var templates, infrastructure summaries and pack
scaffolding. (The MCP ``api_pack`` tool was removed in flense ship I.)
"""

from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Impl functions (no MCP types, explicit params, return plain dicts)
# ---------------------------------------------------------------------------


def api_pack_generate_dsl_impl(*, pack_name: str) -> dict[str, Any]:
    """Generate DSL service and foreign_model blocks from an API pack."""
    from dazzle.api_kb import load_pack

    pack = load_pack(pack_name)
    if pack is None:
        return {"error": f"Pack '{pack_name}' not found"}

    dsl_parts = []
    dsl_parts.append(pack.generate_service_dsl())
    for model in pack.foreign_models:
        dsl_parts.append(pack.generate_foreign_model_dsl(model))

    dsl_code = "\n\n".join(dsl_parts)
    integration_template = pack.generate_integration_template()

    return {
        "pack": pack_name,
        "provider": pack.provider,
        "dsl": dsl_code,
        "integration_template": integration_template,
        "env_vars_required": [e.name for e in pack.env_vars if e.required],
        "hint": "Add the DSL blocks to your file. The integration_template shows recommended cache settings.",
    }


def api_pack_env_vars_impl(*, pack_names: list[str] | None = None) -> dict[str, Any]:
    """Get .env.example content for specified packs or all packs."""
    from dazzle.api_kb.loader import generate_env_example

    env_example = generate_env_example(pack_names)

    return {
        "packs": pack_names if pack_names else "all",
        "env_example": env_example,
        "hint": "Add this to your .env file and fill in the values",
    }


def api_pack_infrastructure_impl(project_path: Path) -> dict[str, Any]:
    """Discover infrastructure requirements for services declared in DSL."""
    from dazzle.api_kb import load_pack

    from .common import load_project_appspec

    appspec = load_project_appspec(project_path)
    services: list[dict[str, Any]] = []
    for svc in getattr(appspec, "services", []) or []:
        spec_inline = getattr(svc, "spec_inline", None) or ""
        pack_name = spec_inline.removeprefix("pack:") if spec_inline.startswith("pack:") else None
        pack = load_pack(pack_name) if pack_name else None

        entry: dict[str, Any] = {
            "service": svc.name,
            "title": getattr(svc, "title", None),
            "pack": pack_name,
        }

        if pack and pack.infrastructure:
            entry["infrastructure"] = _serialize_infrastructure(pack.infrastructure)
            entry["env_vars"] = [
                {"name": e.name, "required": e.required, "description": e.description}
                for e in pack.env_vars
            ]
        else:
            entry["infrastructure"] = None
            entry["hint"] = (
                "No infrastructure metadata in API pack" if pack_name else "No pack reference"
            )

        services.append(entry)

    self_hosted = [
        s
        for s in services
        if (s.get("infrastructure") or {}).get("hosting") in ("self_hosted", "both")
    ]
    cloud_only = [
        s for s in services if (s.get("infrastructure") or {}).get("hosting") == "cloud_only"
    ]
    unknown = [s for s in services if s.get("infrastructure") is None]

    return {
        "service_count": len(services),
        "self_hosted_count": len(self_hosted),
        "cloud_only_count": len(cloud_only),
        "unknown_count": len(unknown),
        "services": services,
    }


def api_pack_scaffold_impl(
    *,
    openapi_spec: dict[str, Any] | None = None,
    openapi_url: str | None = None,
    provider: str = "MyVendor",
    category: str = "api",
    pack_name: str = "",
) -> dict[str, Any]:
    """Scaffold a new API pack TOML from OpenAPI spec or blank template."""
    from dazzle.api_kb.openapi_importer import import_from_openapi, scaffold_blank

    toml_content: str

    if openapi_spec:
        toml_content = import_from_openapi(openapi_spec)
    elif openapi_url:
        import httpx

        resp = httpx.get(openapi_url, timeout=30.0, follow_redirects=True)
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "")
        if "yaml" in content_type or openapi_url.endswith((".yaml", ".yml")):
            try:
                import yaml

                spec_data = yaml.safe_load(resp.text)
            except ImportError:
                return {
                    "error": "PyYAML required for YAML OpenAPI specs. Install with: pip install pyyaml"
                }
        else:
            spec_data = resp.json()
        toml_content = import_from_openapi(spec_data)
    else:
        if not pack_name:
            pack_name = f"{provider.lower().replace(' ', '_')}_{category}"
        toml_content = scaffold_blank(provider, category, pack_name)

    if not pack_name:
        import re

        match = re.search(r'name\s*=\s*"([^"]+)"', toml_content)
        pack_name = match.group(1) if match else "custom_pack"

    parts = pack_name.split("_", 1)
    vendor_dir = parts[0] if len(parts) > 1 else pack_name
    save_path = f".dazzle/api_packs/{vendor_dir}/{pack_name}.toml"

    return {
        "toml": toml_content,
        "save_path": save_path,
        "hint": f'Save to {save_path} in your project directory, then reference with spec: inline "pack:{pack_name}"',
    }


def _serialize_infrastructure(infra: Any) -> dict[str, Any] | None:
    """Serialize InfrastructureSpec to JSON-compatible dict."""
    if infra is None:
        return None
    result: dict[str, Any] = {"hosting": infra.hosting}
    if infra.local_env_overrides:
        result["local_env_overrides"] = infra.local_env_overrides
    if infra.sandbox:
        result["sandbox"] = {
            "available": infra.sandbox.available,
            "env_prefix": infra.sandbox.env_prefix,
            "docs": infra.sandbox.docs,
        }
    return result
