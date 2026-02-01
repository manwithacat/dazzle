"""SiteSpec tool handlers.

Handles site specification loading, validation, and scaffolding.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("dazzle.mcp")


def get_sitespec_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Load and return the SiteSpec from sitespec.yaml."""
    from dazzle.core.sitespec_loader import (
        SiteSpecError,
        load_sitespec,
        sitespec_exists,
    )

    use_defaults = args.get("use_defaults", True)

    try:
        sitespec = load_sitespec(project_root, use_defaults=use_defaults)

        # Convert to dict for JSON serialization
        result = {
            "exists": sitespec_exists(project_root),
            "version": sitespec.version,
            "brand": {
                "product_name": sitespec.brand.product_name,
                "tagline": sitespec.brand.tagline,
                "support_email": sitespec.brand.support_email,
                "company_legal_name": sitespec.brand.company_legal_name,
                "logo": {
                    "mode": sitespec.brand.logo.mode.value,
                    "text": sitespec.brand.logo.text,
                    "image_path": sitespec.brand.logo.image_path,
                },
            },
            "layout": {
                "theme": sitespec.layout.theme.value,
                "auth_entry": sitespec.layout.auth.primary_entry,
                "nav": {
                    "public": [
                        {"label": n.label, "href": n.href} for n in sitespec.layout.nav.public
                    ],
                    "authenticated": [
                        {"label": n.label, "href": n.href}
                        for n in sitespec.layout.nav.authenticated
                    ],
                },
                "footer": {
                    "columns": [
                        {
                            "title": col.title,
                            "links": [
                                {"label": link.label, "href": link.href} for link in col.links
                            ],
                        }
                        for col in sitespec.layout.footer.columns
                    ],
                    "disclaimer": sitespec.layout.footer.disclaimer,
                },
            },
            "pages": [
                {
                    "route": p.route,
                    "type": p.type.value,
                    "title": p.title,
                    "sections_count": len(p.sections),
                    "source": (
                        {"format": p.source.format.value, "path": p.source.path}
                        if p.source
                        else None
                    ),
                }
                for p in sitespec.pages
            ],
            "legal": {
                "terms": ({"route": sitespec.legal.terms.route} if sitespec.legal.terms else None),
                "privacy": (
                    {"route": sitespec.legal.privacy.route} if sitespec.legal.privacy else None
                ),
            },
            "auth_pages": {
                "login": {
                    "route": sitespec.auth_pages.login.route,
                    "enabled": sitespec.auth_pages.login.enabled,
                },
                "signup": {
                    "route": sitespec.auth_pages.signup.route,
                    "enabled": sitespec.auth_pages.signup.enabled,
                },
            },
            "integrations": {
                "app_mount_route": sitespec.integrations.app_mount_route,
                "auth_provider": sitespec.integrations.auth_provider.value,
            },
            "all_routes": sitespec.get_all_routes(),
        }

        return json.dumps(result, indent=2)

    except SiteSpecError as e:
        return json.dumps({"error": str(e)}, indent=2)
    except Exception as e:
        logger.exception("Error loading sitespec")
        return json.dumps({"error": f"Unexpected error: {e}"}, indent=2)


def validate_sitespec_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Validate the SiteSpec for semantic correctness."""
    from dazzle.core.sitespec_loader import (
        SiteSpecError,
        load_sitespec,
        validate_sitespec,
    )

    check_content_files = args.get("check_content_files", True)

    try:
        sitespec = load_sitespec(project_root, use_defaults=True)
        result = validate_sitespec(
            sitespec,
            project_root,
            check_content_files=check_content_files,
        )

        return json.dumps(
            {
                "is_valid": result.is_valid,
                "error_count": len(result.errors),
                "warning_count": len(result.warnings),
                "errors": result.errors,
                "warnings": result.warnings,
            },
            indent=2,
        )

    except SiteSpecError as e:
        return json.dumps({"error": str(e)}, indent=2)
    except Exception as e:
        logger.exception("Error validating sitespec")
        return json.dumps({"error": f"Unexpected error: {e}"}, indent=2)


def scaffold_site_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Create default site structure with templates."""
    from dazzle.core.sitespec_loader import scaffold_site as do_scaffold_site

    product_name = args.get("product_name", "My App")
    overwrite = args.get("overwrite", False)

    try:
        result = do_scaffold_site(project_root, product_name, overwrite=overwrite)

        created_files: list[str] = []
        if result["sitespec"]:
            created_files.append(str(result["sitespec"]))
        content_files = result["content"]
        if isinstance(content_files, list):
            for f in content_files:
                created_files.append(str(f))

        return json.dumps(
            {
                "success": True,
                "product_name": product_name,
                "created_files": created_files,
                "message": f"Created {len(created_files)} files for site shell",
            },
            indent=2,
        )

    except Exception as e:
        logger.exception("Error scaffolding site")
        return json.dumps({"error": f"Failed to scaffold site: {e}"}, indent=2)
