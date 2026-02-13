"""SiteSpec tool handlers.

Handles site specification loading, validation, and scaffolding.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from dazzle.mcp.server.progress import ProgressContext
from dazzle.mcp.server.progress import noop as _noop_progress

logger = logging.getLogger("dazzle.mcp")


def get_sitespec_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Load and return the SiteSpec from sitespec.yaml."""
    from dazzle.core.sitespec_loader import (
        SiteSpecError,
        load_sitespec,
        sitespec_exists,
    )

    progress: ProgressContext = args.get("_progress") or _noop_progress()
    use_defaults = args.get("use_defaults", True)

    try:
        progress.log_sync("Loading sitespec...")
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

    progress: ProgressContext = args.get("_progress") or _noop_progress()
    check_content_files = args.get("check_content_files", True)

    try:
        progress.log_sync("Validating sitespec...")
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

    progress: ProgressContext = args.get("_progress") or _noop_progress()
    product_name = args.get("product_name", "My App")
    overwrite = args.get("overwrite", False)

    try:
        progress.log_sync("Scaffolding sitespec...")
        result = do_scaffold_site(project_root, product_name, overwrite=overwrite)

        created_files: list[str] = []
        if result["sitespec"]:
            created_files.append(str(result["sitespec"]))
        content_files = result["content"]
        if isinstance(content_files, list):
            for f in content_files:
                created_files.append(str(f))

        # Create static/images/ directory convention for project assets
        static_images_dir = project_root / "static" / "images"
        if not static_images_dir.exists():
            static_images_dir.mkdir(parents=True, exist_ok=True)
            gitkeep = static_images_dir / ".gitkeep"
            gitkeep.touch()
            created_files.append(str(gitkeep))

        return json.dumps(
            {
                "success": True,
                "product_name": product_name,
                "created_files": created_files,
                "message": f"Created {len(created_files)} files for site shell",
                "static_assets": {
                    "convention": "Place project images in static/images/",
                    "usage": "Reference as /static/images/filename.ext in sitespec media.src",
                    "path": str(static_images_dir),
                },
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

    progress: ProgressContext = args.get("_progress") or _noop_progress()

    try:
        progress.log_sync("Loading copy...")
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

    progress: ProgressContext = args.get("_progress") or _noop_progress()
    product_name = args.get("product_name", "My App")
    overwrite = args.get("overwrite", False)

    try:
        progress.log_sync("Scaffolding copy...")
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

    progress: ProgressContext = args.get("_progress") or _noop_progress()

    try:
        progress.log_sync("Reviewing copy...")
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

    progress: ProgressContext = args.get("_progress") or _noop_progress()
    business_context = args.get("business_context")

    try:
        progress.log_sync("Validating site coherence...")
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


def review_sitespec_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Live Review — page-by-page comparison of spec vs rendering status.

    For each page and section defined in the sitespec, reports:
    - Whether the section type has a renderer
    - Whether required content fields are populated
    - Coherence issues specific to that section

    Returns a structured comparison and a markdown summary.
    """
    from dazzle.core.site_coherence import validate_site_coherence
    from dazzle.core.sitespec_loader import SiteSpecError, load_copy, load_sitespec

    progress: ProgressContext = args.get("_progress") or _noop_progress()
    business_context = args.get("business_context")

    try:
        progress.log_sync("Reviewing sitespec...")
        sitespec = load_sitespec(project_root, use_defaults=True)
        sitespec_data = sitespec.model_dump()
        copy_data = load_copy(project_root)

        # Run coherence for issues
        report = validate_site_coherence(
            sitespec_data,
            copy_data=copy_data,
            project_root=project_root,
            business_context=business_context,
        )

        # Known renderers from site_renderer.py
        known_renderers = {
            "hero",
            "features",
            "feature_grid",
            "cta",
            "faq",
            "stats",
            "steps",
            "testimonials",
            "pricing",
            "markdown",
            "card_grid",
            "split_content",
            "trust_bar",
            "value_highlight",
            "logo_cloud",
            "comparison",
        }

        # Required content fields per section type
        required_fields: dict[str, list[str]] = {
            "hero": ["headline"],
            "features": ["items"],
            "cta": ["headline"],
            "faq": ["items"],
            "steps": ["items"],
            "testimonials": ["items"],
            "pricing": ["plans"],
            "card_grid": ["cards"],
            "split_content": ["headline"],
            "trust_bar": ["items"],
            "value_highlight": ["metric"],
            "logo_cloud": ["logos"],
            "comparison": ["plans"],
        }

        # Build issues index by location
        issues_by_location: dict[str, list[dict[str, str]]] = {}
        for issue in report.issues:
            loc = issue.location or "global"
            issues_by_location.setdefault(loc, []).append(
                {
                    "severity": issue.severity.value,
                    "message": issue.message,
                    "suggestion": issue.suggestion or "",
                }
            )

        # Analyze each page and section
        pages: list[dict[str, Any]] = []
        total_sections = 0
        rendering_sections = 0

        for page in sitespec_data.get("pages", []):
            page_route = page.get("route", "unknown")
            page_title = page.get("title", page_route)
            sections: list[dict[str, Any]] = []

            for section in page.get("sections", []):
                total_sections += 1
                sec_type = section.get("type", "unknown")
                has_renderer = sec_type in known_renderers

                # Check required fields
                missing_fields: list[str] = []
                for field_name in required_fields.get(sec_type, []):
                    val = section.get(field_name)
                    if not val or (isinstance(val, list) and len(val) == 0):
                        missing_fields.append(field_name)

                renders = has_renderer and len(missing_fields) == 0
                if renders:
                    rendering_sections += 1

                sections.append(
                    {
                        "type": sec_type,
                        "has_renderer": has_renderer,
                        "missing_fields": missing_fields,
                        "renders": renders,
                        "headline": section.get("headline", ""),
                    }
                )

            page_issues = issues_by_location.get(page_route, [])
            pages.append(
                {
                    "route": page_route,
                    "title": page_title,
                    "sections": sections,
                    "issue_count": len(page_issues),
                    "issues": page_issues,
                }
            )

        render_pct = (
            round(rendering_sections / total_sections * 100, 1) if total_sections > 0 else 0
        )

        # Render markdown
        md_lines = ["Site Review", ""]
        md_lines.append(
            f"Rendering: {rendering_sections}/{total_sections} sections ({render_pct}%)"
        )
        md_lines.append("")

        for pg in pages:
            md_lines.append(f"  {pg['title']} ({pg['route']})")
            for sec in pg["sections"]:
                status = "[ok]" if sec["renders"] else "[!!]"
                label = sec.get("headline") or sec["type"]
                line = f"    {status} {label}"
                if not sec["has_renderer"]:
                    line += " (no renderer)"
                elif sec["missing_fields"]:
                    line += f" (missing: {', '.join(sec['missing_fields'])})"
                md_lines.append(line)
            if pg["issues"]:
                for issue in pg["issues"]:
                    md_lines.append(f"    {issue['severity']}: {issue['message']}")
            md_lines.append("")

        return json.dumps(
            {
                "status": "complete",
                "total_sections": total_sections,
                "rendering_sections": rendering_sections,
                "render_percent": render_pct,
                "pages": pages,
                "coherence_score": report.score,
                "markdown": "\n".join(md_lines),
            },
            indent=2,
        )

    except SiteSpecError as e:
        return json.dumps({"error": str(e)}, indent=2)
    except Exception as e:
        logger.exception("Error in site review")
        return json.dumps({"error": f"Failed to review site: {e}"}, indent=2)


# =============================================================================
# ThemeSpec Operations (v0.25.0)
# =============================================================================


def get_theme_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Load and return the ThemeSpec from themespec.yaml."""
    from dazzle.core.themespec_loader import (
        ThemeSpecError,
        load_themespec,
        themespec_exists,
    )

    progress: ProgressContext = args.get("_progress") or _noop_progress()
    use_defaults = args.get("use_defaults", True)

    try:
        progress.log_sync("Loading themespec...")
        themespec = load_themespec(project_root, use_defaults=use_defaults)

        result = {
            "exists": themespec_exists(project_root),
            "palette": {
                "brand_hue": themespec.palette.brand_hue,
                "brand_chroma": themespec.palette.brand_chroma,
                "mode": themespec.palette.mode.value,
                "accent_hue_offset": themespec.palette.accent_hue_offset,
                "neutral_chroma": themespec.palette.neutral_chroma,
            },
            "typography": {
                "base_size_px": themespec.typography.base_size_px,
                "ratio": themespec.typography.ratio.value,
                "line_height_body": themespec.typography.line_height_body,
                "line_height_heading": themespec.typography.line_height_heading,
                "font_stacks": {
                    "heading": themespec.typography.font_stacks.heading,
                    "body": themespec.typography.font_stacks.body,
                    "mono": themespec.typography.font_stacks.mono,
                },
            },
            "spacing": {
                "base_unit_px": themespec.spacing.base_unit_px,
                "density": themespec.spacing.density.value,
            },
            "shape": {
                "radius_preset": themespec.shape.radius_preset.value,
                "shadow_preset": themespec.shape.shadow_preset.value,
                "border_width_px": themespec.shape.border_width_px,
            },
            "attention_map": {
                "rule_count": len(themespec.attention_map.rules),
            },
            "layout": {
                "max_columns": themespec.layout.surfaces.max_columns,
                "sidebar_width_px": themespec.layout.surfaces.sidebar_width_px,
                "content_max_width_px": themespec.layout.surfaces.content_max_width_px,
            },
            "imagery": {
                "style_keywords": themespec.imagery.vocabulary.style_keywords,
                "mood_keywords": themespec.imagery.vocabulary.mood_keywords,
                "default_aspect_ratio": themespec.imagery.default_aspect_ratio,
                "default_resolution": themespec.imagery.default_resolution,
            },
            "meta": {
                "version": themespec.meta.version,
                "generated_by": themespec.meta.generated_by,
                "agent_editable_fields": themespec.meta.agent_editable_fields,
            },
        }

        return json.dumps(result, indent=2)

    except ThemeSpecError as e:
        return json.dumps({"error": str(e)}, indent=2)
    except Exception as e:
        logger.exception("Error loading themespec")
        return json.dumps({"error": f"Unexpected error: {e}"}, indent=2)


def scaffold_theme_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Create a default themespec.yaml file."""
    from dazzle.core.themespec_loader import scaffold_themespec, themespec_exists

    progress: ProgressContext = args.get("_progress") or _noop_progress()
    progress.log_sync("Scaffolding themespec...")
    brand_hue = args.get("brand_hue", 260.0)
    brand_chroma = args.get("brand_chroma", 0.15)
    product_name = args.get("product_name", "My App")
    overwrite = args.get("overwrite", False)

    try:
        existed = themespec_exists(project_root)

        if existed and not overwrite:
            return json.dumps(
                {
                    "success": False,
                    "message": "themespec.yaml already exists. Use overwrite=true to regenerate.",
                },
                indent=2,
            )

        # Try to read brand info from sitespec if available
        try:
            from dazzle.core.sitespec_loader import load_sitespec

            sitespec = load_sitespec(project_root, use_defaults=False)
            if product_name == "My App" and sitespec.brand.product_name:
                product_name = sitespec.brand.product_name
        except Exception:
            pass

        created_path = scaffold_themespec(
            project_root,
            brand_hue=brand_hue,
            brand_chroma=brand_chroma,
            product_name=product_name,
            overwrite=overwrite,
        )

        return json.dumps(
            {
                "success": True,
                "path": str(created_path) if created_path else None,
                "brand_hue": brand_hue,
                "brand_chroma": brand_chroma,
                "overwritten": existed and overwrite,
                "message": f"Created themespec.yaml (hue={brand_hue}, chroma={brand_chroma})",
                "next_steps": [
                    "1. Run get_theme to inspect generated values",
                    "2. Adjust brand_hue/brand_chroma to match your brand",
                    "3. Run validate_theme to check for issues",
                    "4. Run generate_tokens for DTCG tokens.json export",
                ],
            },
            indent=2,
        )

    except Exception as e:
        logger.exception("Error scaffolding themespec")
        return json.dumps({"error": f"Failed to scaffold themespec: {e}"}, indent=2)


def validate_theme_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Validate the ThemeSpec for semantic correctness."""
    from dazzle.core.themespec_loader import (
        ThemeSpecError,
        load_themespec,
        validate_themespec,
    )

    progress: ProgressContext = args.get("_progress") or _noop_progress()

    try:
        progress.log_sync("Validating themespec...")
        themespec = load_themespec(project_root, use_defaults=True)
        result = validate_themespec(themespec, project_root)

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

    except ThemeSpecError as e:
        return json.dumps({"error": str(e)}, indent=2)
    except Exception as e:
        logger.exception("Error validating themespec")
        return json.dumps({"error": f"Unexpected error: {e}"}, indent=2)


def generate_tokens_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Generate DTCG tokens.json from themespec.yaml."""
    from dazzle.core.dtcg_export import export_dtcg_file, generate_dtcg_tokens
    from dazzle.core.themespec_loader import ThemeSpecError, load_themespec

    progress: ProgressContext = args.get("_progress") or _noop_progress()

    try:
        progress.log_sync("Generating design tokens...")
        themespec = load_themespec(project_root, use_defaults=True)
        tokens = generate_dtcg_tokens(themespec)

        # Write to project
        output_path = project_root / "tokens.json"
        export_dtcg_file(themespec, output_path)

        # Summarize token counts
        summary: dict[str, int] = {}
        for group_name, group in tokens.items():
            if isinstance(group, dict):
                count = 0
                for v in group.values():
                    if isinstance(v, dict) and "$type" in v:
                        count += 1
                    elif isinstance(v, dict):
                        count += len(v)
                summary[group_name] = count

        return json.dumps(
            {
                "success": True,
                "path": str(output_path),
                "token_groups": summary,
                "total_tokens": sum(summary.values()),
                "format": "W3C DTCG",
            },
            indent=2,
        )

    except ThemeSpecError as e:
        return json.dumps({"error": str(e)}, indent=2)
    except Exception as e:
        logger.exception("Error generating tokens")
        return json.dumps({"error": f"Failed to generate tokens: {e}"}, indent=2)


def generate_imagery_prompts_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Generate imagery prompts from themespec.yaml."""
    from dazzle.core.imagery_prompts import generate_imagery_prompts
    from dazzle.core.themespec_loader import ThemeSpecError, load_themespec

    progress: ProgressContext = args.get("_progress") or _noop_progress()

    try:
        progress.log_sync("Generating imagery prompts...")
        themespec = load_themespec(project_root, use_defaults=True)

        # Try to load sitespec for section context
        sitespec = None
        try:
            from dazzle.core.sitespec_loader import load_sitespec

            sitespec = load_sitespec(project_root, use_defaults=False)
        except Exception:
            pass

        prompts = generate_imagery_prompts(themespec, sitespec)

        return json.dumps(
            {
                "prompt_count": len(prompts),
                "prompts": [
                    {
                        "section": p.section,
                        "prompt": p.prompt,
                        "negative_prompt": p.negative_prompt,
                        "aspect_ratio": p.aspect_ratio,
                        "resolution": p.resolution,
                    }
                    for p in prompts
                ],
            },
            indent=2,
        )

    except ThemeSpecError as e:
        return json.dumps({"error": str(e)}, indent=2)
    except Exception as e:
        logger.exception("Error generating imagery prompts")
        return json.dumps({"error": f"Failed to generate imagery prompts: {e}"}, indent=2)
