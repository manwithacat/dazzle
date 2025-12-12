"""
Security documentation generator for DAZZLE applications.

Generates SECURITY.md from AppSpec security configuration.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dazzle.core.ir import AppSpec


def generate_security_md(app_spec: AppSpec) -> str:
    """
    Generate SECURITY.md content from application security configuration.

    Args:
        app_spec: The application specification

    Returns:
        Markdown content for SECURITY.md
    """
    security = app_spec.security
    if security is None:
        # Default to basic profile
        from dazzle.core.ir.security import SecurityConfig, SecurityProfile

        security = SecurityConfig.from_profile(SecurityProfile.BASIC)

    # Build sections
    sections = []

    # Header
    sections.append(f"# Security Configuration: {app_spec.name}")
    sections.append("")
    sections.append("*Auto-generated from DAZZLE security configuration*")
    sections.append("")

    # Security Profile
    sections.append("## Security Profile")
    sections.append("")
    profile_desc = {
        "basic": "Minimal security for internal tools and development",
        "standard": "Standard security for SaaS applications",
        "strict": "Maximum security for multi-tenant production deployments",
    }
    sections.append(f"**Profile:** `{security.profile.value}`")
    sections.append("")
    sections.append(profile_desc.get(security.profile.value, "Custom configuration"))
    sections.append("")

    # Authentication
    sections.append("## Authentication")
    sections.append("")
    if security.require_auth_by_default:
        sections.append("- **Default:** Authentication required for all surfaces")
    else:
        sections.append("- **Default:** Public access (auth optional)")
    sections.append("")

    # Protected Surfaces
    protected_surfaces = []
    for surface in app_spec.surfaces:
        if surface.access and surface.access.require_auth:
            protected_surfaces.append(surface)

    if protected_surfaces:
        sections.append("## Protected Surfaces")
        sections.append("")
        sections.append("| Surface | Allowed Personas | Denied Personas | Redirect |")
        sections.append("|---------|------------------|-----------------|----------|")
        for surface in protected_surfaces:
            access = surface.access
            if access is not None:
                allowed = (
                    ", ".join(access.allow_personas)
                    if access.allow_personas
                    else "all authenticated"
                )
                denied = ", ".join(access.deny_personas) if access.deny_personas else "-"
                redirect = access.redirect_unauthenticated or "/"
                sections.append(f"| {surface.name} | {allowed} | {denied} | {redirect} |")
        sections.append("")

    # CORS Policy
    sections.append("## CORS Policy")
    sections.append("")
    if security.cors_origins == ["*"]:
        sections.append("- **Mode:** Permissive (allow all origins)")
        sections.append("- **Note:** Only appropriate for development or internal tools")
    elif security.cors_origins:
        sections.append("- **Mode:** Restricted to specific origins")
        sections.append("- **Allowed Origins:**")
        for origin in security.cors_origins:
            sections.append(f"  - `{origin}`")
    else:
        sections.append("- **Mode:** Same-origin only (strictest)")
    sections.append("")

    # Security Headers
    sections.append("## Security Headers")
    sections.append("")
    headers = []
    if security.enable_hsts:
        headers.append("- `Strict-Transport-Security` (HSTS)")
    if security.enable_csp:
        headers.append("- `Content-Security-Policy` (CSP)")
    if security.profile.value != "basic":
        headers.append("- `X-Frame-Options: DENY`")
        headers.append("- `X-Content-Type-Options: nosniff`")
        headers.append("- `X-XSS-Protection: 1; mode=block`")
        headers.append("- `Referrer-Policy: strict-origin-when-cross-origin`")

    if headers:
        sections.append("**Enabled Headers:**")
        sections.append("")
        sections.extend(headers)
    else:
        sections.append("*Minimal security headers (basic profile)*")
    sections.append("")

    # Tenant Isolation
    sections.append("## Tenant Isolation")
    sections.append("")
    if security.tenant_isolation:
        sections.append("- **Mode:** Enabled")
        sections.append("- **Development:** Separate SQLite database per tenant")
        sections.append("- **Production:** Tenant-per-schema in PostgreSQL")
        sections.append("")
        sections.append("**Tenant Identification:**")
        sections.append("- Header: `X-Tenant-ID`")
        sections.append("- Cookie: `dazzle_tenant_id`")
    else:
        sections.append("- **Mode:** Disabled (single database)")
    sections.append("")

    # Recommendations
    sections.append("## Security Recommendations")
    sections.append("")

    recommendations = []

    if security.profile.value == "basic":
        recommendations.append("⚠️ **Basic profile** - Only use for internal tools or development")
        recommendations.append("Consider upgrading to `standard` or `strict` for production")

    if security.cors_origins == ["*"]:
        recommendations.append("⚠️ **Permissive CORS** - Consider restricting to specific origins")

    if not security.enable_hsts:
        recommendations.append("📋 Consider enabling HSTS for production HTTPS deployments")

    if not security.enable_csp:
        recommendations.append("📋 Consider enabling CSP for additional XSS protection")

    if security.profile.value == "strict" and not security.tenant_isolation:
        recommendations.append(
            "⚠️ **Strict profile without tenant isolation** - Enable multi_tenant for full isolation"
        )

    if recommendations:
        for rec in recommendations:
            sections.append(f"- {rec}")
    else:
        sections.append("✅ Configuration looks good for the selected profile")
    sections.append("")

    # Footer
    sections.append("---")
    sections.append("")
    sections.append("*Generated by DAZZLE v0.11.0*")

    return "\n".join(sections)


def write_security_md(app_spec: AppSpec, output_path: str = ".dazzle/SECURITY.md") -> str:
    """
    Generate and write SECURITY.md file.

    Args:
        app_spec: The application specification
        output_path: Path to write the file

    Returns:
        Path to the written file
    """
    from pathlib import Path

    content = generate_security_md(app_spec)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return str(path)
