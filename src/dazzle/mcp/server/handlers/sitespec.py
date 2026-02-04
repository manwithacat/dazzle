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

        # Try to load AppSpec for DSL route awareness
        appspec = None
        try:
            from dazzle.core.fileset import discover_dsl_files
            from dazzle.core.linker import build_appspec
            from dazzle.core.manifest import load_manifest
            from dazzle.core.parser import parse_modules

            manifest_path = project_root / "dazzle.toml"
            if manifest_path.exists():
                manifest = load_manifest(manifest_path)
                dsl_files = discover_dsl_files(project_root, manifest)
                if dsl_files:
                    modules = parse_modules(dsl_files)
                    if modules:
                        appspec = build_appspec(modules, manifest.project_root)
        except Exception:
            logger.debug("Could not load AppSpec for sitespec validation", exc_info=True)

        result = validate_sitespec(
            sitespec,
            project_root,
            check_content_files=check_content_files,
            appspec=appspec,
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


# =============================================================================
# Copy File Operations (v0.22.0)
# =============================================================================


def get_copy_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Load and return the parsed copy.md content.

    Returns the marketing copy in a structured format that's easy to
    review and edit. Each section includes its type, content, and
    any subsections (features, testimonials, etc.).
    """
    from dazzle.core.sitespec_loader import copy_file_exists, get_copy_file_path, load_copy

    try:
        copy_path = get_copy_file_path(project_root)
        exists = copy_file_exists(project_root)

        if not exists:
            return json.dumps(
                {
                    "exists": False,
                    "path": str(copy_path),
                    "message": "No copy.md found. Use scaffold operation to create one.",
                    "hint": "Run: sitespec(operation='scaffold_copy') to generate a template",
                },
                indent=2,
            )

        copy_data = load_copy(project_root)

        if copy_data is None:
            return json.dumps(
                {
                    "exists": True,
                    "path": str(copy_path),
                    "error": "Failed to parse copy.md",
                },
                indent=2,
            )

        # Format sections for easy reading
        formatted_sections = []
        for section in copy_data.get("sections", []):
            formatted = {
                "type": section.get("type"),
                "title": section.get("title"),
            }

            # Include key metadata
            metadata = section.get("metadata", {})
            if metadata:
                formatted["metadata"] = metadata

            # Include subsections count and sample
            subsections = section.get("subsections", [])
            if subsections:
                formatted["subsection_count"] = len(subsections)
                # Include first subsection as preview
                if subsections:
                    formatted["subsection_preview"] = subsections[0]

            formatted_sections.append(formatted)

        return json.dumps(
            {
                "exists": True,
                "path": str(copy_path),
                "section_count": len(formatted_sections),
                "sections": formatted_sections,
                "tip": "Edit copy.md directly to update marketing content. "
                "Changes are merged into sitespec at runtime.",
            },
            indent=2,
        )

    except Exception as e:
        logger.exception("Error loading copy")
        return json.dumps({"error": f"Failed to load copy: {e}"}, indent=2)


def scaffold_copy_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Create or regenerate the copy.md template file.

    Generates a founder-friendly markdown file with all standard marketing
    sections (hero, features, testimonials, pricing, FAQ, CTA). The file
    is designed for easy editing and works well with LLM-generated content.
    """
    from dazzle.core.sitespec_loader import (
        copy_file_exists,
        get_copy_file_path,
        scaffold_copy_file,
    )

    product_name = args.get("product_name", "My App")
    overwrite = args.get("overwrite", False)

    try:
        copy_path = get_copy_file_path(project_root)
        existed = copy_file_exists(project_root)

        if existed and not overwrite:
            return json.dumps(
                {
                    "success": False,
                    "path": str(copy_path),
                    "message": "copy.md already exists. Use overwrite=true to regenerate.",
                    "warning": "Overwriting will lose existing content!",
                },
                indent=2,
            )

        created_path = scaffold_copy_file(project_root, product_name, overwrite=overwrite)

        return json.dumps(
            {
                "success": True,
                "path": str(created_path or copy_path),
                "product_name": product_name,
                "overwritten": existed and overwrite,
                "message": f"Created copy.md with marketing sections for '{product_name}'",
                "sections": [
                    "Hero",
                    "Features",
                    "How It Works",
                    "Testimonials",
                    "Pricing",
                    "FAQ",
                    "CTA",
                ],
                "next_steps": [
                    "1. Open site/content/copy.md in your editor",
                    "2. Replace placeholder text with your actual content",
                    "3. Run the app to see changes reflected in the landing page",
                ],
            },
            indent=2,
        )

    except Exception as e:
        logger.exception("Error scaffolding copy")
        return json.dumps({"error": f"Failed to scaffold copy: {e}"}, indent=2)


def review_copy_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Review copy.md content in a founder-friendly format.

    Returns the raw content of copy.md along with validation hints
    and suggestions for improvement. Useful for quick content review
    without opening a text editor.
    """
    from dazzle.core.copy_parser import load_copy_file
    from dazzle.core.sitespec_loader import copy_file_exists, get_copy_file_path

    try:
        if not copy_file_exists(project_root):
            return json.dumps(
                {
                    "exists": False,
                    "message": "No copy.md found. Create one with scaffold_copy operation.",
                },
                indent=2,
            )

        copy_path = get_copy_file_path(project_root)
        parsed = load_copy_file(project_root)

        if parsed is None:
            return json.dumps({"error": "Failed to parse copy.md"}, indent=2)

        # Build a review summary
        section_summaries: list[dict[str, Any]] = []
        suggestions: list[str] = []

        section_types_found: set[str] = set()

        for section in parsed.sections:
            section_types_found.add(section.section_type)

            summary: dict[str, Any] = {
                "type": section.section_type,
                "title": section.title,
            }

            # Add specific details per section type
            if section.section_type == "hero":
                summary["headline"] = section.metadata.get("headline")
                summary["has_ctas"] = len(section.metadata.get("ctas", [])) > 0
            elif section.section_type == "features":
                summary["feature_count"] = len(section.subsections)
            elif section.section_type == "testimonials":
                summary["testimonial_count"] = len(section.subsections)
            elif section.section_type == "pricing":
                summary["tier_count"] = len(section.subsections)
            elif section.section_type == "faq":
                summary["question_count"] = len(section.subsections)

            section_summaries.append(summary)

        # Add suggestions for missing sections
        recommended = {"hero", "features", "pricing", "cta"}
        missing = recommended - section_types_found
        if missing:
            suggestions.append(f"Consider adding missing sections: {', '.join(sorted(missing))}")

        # Check for placeholder content
        if parsed.raw_markdown and "Your Tagline Here" in parsed.raw_markdown:
            suggestions.append(
                "Replace placeholder text (e.g., 'Your Tagline Here') with actual content"
            )

        # Build final review dict
        review = {
            "path": str(copy_path),
            "section_summary": section_summaries,
            "suggestions": suggestions,
            "raw_content": parsed.raw_markdown,
        }

        return json.dumps(review, indent=2)

    except Exception as e:
        logger.exception("Error reviewing copy")
        return json.dumps({"error": f"Failed to review copy: {e}"}, indent=2)


# =============================================================================
# Site Coherence Validation (v0.22.0)
# =============================================================================


def coherence_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Validate site coherence - does it feel like a real website?

    Checks that the generated site would feel complete and professional:
    - Navigation links resolve to actual pages
    - CTAs lead somewhere meaningful
    - Expected pages exist for the business type
    - Content isn't placeholder text
    - Internal linking is consistent
    - User flows are complete

    Returns a coherence score (0-100) and actionable suggestions.
    """
    from dazzle.core.site_coherence import validate_site_coherence
    from dazzle.core.sitespec_loader import (
        SiteSpecError,
        load_copy,
        load_sitespec,
    )

    business_context = args.get("business_context")

    try:
        # Load sitespec
        sitespec = load_sitespec(project_root, use_defaults=True)
        sitespec_data = sitespec.model_dump()

        # Load copy data if available
        copy_data = load_copy(project_root)

        # Run coherence validation
        report = validate_site_coherence(
            sitespec_data,
            copy_data=copy_data,
            project_root=project_root,
            business_context=business_context,
        )

        result = report.to_dict()

        # Add formatted output for easy reading
        result["formatted"] = report.format()

        # Add next steps based on issues
        if report.error_count > 0:
            result["priority"] = "Fix errors first - site has broken elements"
        elif report.warning_count > 0:
            result["priority"] = "Address warnings to improve site quality"
        else:
            result["priority"] = "Site is coherent - consider suggestions for polish"

        return json.dumps(result, indent=2)

    except SiteSpecError as e:
        return json.dumps({"error": str(e)}, indent=2)
    except Exception as e:
        logger.exception("Error validating coherence")
        return json.dumps({"error": f"Failed to validate coherence: {e}"}, indent=2)
