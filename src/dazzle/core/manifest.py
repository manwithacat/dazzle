import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DockerConfig:
    """Docker infrastructure configuration."""

    variant: str = "compose"  # "compose" or "dockerfile"
    image_name: str | None = None
    base_image: str = "python:3.11-slim"
    port: int = 8000


# =============================================================================
# Shell Configuration
# =============================================================================


@dataclass
class ShellNavConfig:
    """Navigation configuration."""

    style: str = "sidebar"  # "sidebar" | "topbar" | "tabs"
    source: str = "workspaces"  # "workspaces" | "manual"


@dataclass
class ShellFooterLink:
    """A link in the footer."""

    label: str
    href: str


@dataclass
class ShellFooterConfig:
    """Footer configuration."""

    powered_by: bool = True  # Show "Made with Dazzle" link
    links: list[ShellFooterLink] = field(default_factory=list)
    slot: str | None = None  # Optional custom template


@dataclass
class ShellHeaderConfig:
    """Header configuration."""

    show_auth: bool = True  # Show login/logout UI
    slot: str | None = None  # Optional custom template


@dataclass
class ShellPageConfig:
    """Static page configuration."""

    src: str  # Source file (e.g., "pages/privacy.md")
    route: str  # URL route (e.g., "/privacy")
    title: str | None = None  # Page title
    content: str | None = None  # Inline content (markdown or HTML)


@dataclass
class ShellConfig:
    """Shell configuration - app chrome around workspace content."""

    layout: str = "app-shell"  # "app-shell" | "minimal"
    nav: ShellNavConfig = field(default_factory=ShellNavConfig)
    header: ShellHeaderConfig = field(default_factory=ShellHeaderConfig)
    footer: ShellFooterConfig = field(default_factory=ShellFooterConfig)
    pages: list[ShellPageConfig] = field(default_factory=list)


# =============================================================================
# Auth Configuration
# =============================================================================


@dataclass
class AuthSessionConfig:
    """Session-based auth configuration."""

    duration_hours: int = 24
    cookie_name: str = "dazzle_session"
    cookie_secure: bool = True  # Require HTTPS
    cookie_httponly: bool = True  # No JS access


@dataclass
class AuthJwtConfig:
    """JWT auth configuration."""

    access_token_minutes: int = 15
    refresh_token_days: int = 7
    algorithm: str = "HS256"
    # Secret comes from environment: JWT_SECRET


@dataclass
class AuthOAuthProvider:
    """OAuth2 provider configuration."""

    provider: str  # google, github, etc.
    client_id_env: str  # Environment variable name
    client_secret_env: str  # Environment variable name
    scopes: list[str] = field(default_factory=list)


@dataclass
class AuthConfig:
    """Authentication configuration.

    Enable auth by setting enabled=True and choosing a provider.

    Examples in dazzle.toml:

        # Simple session auth (default)
        [auth]
        enabled = true
        provider = "session"

        # JWT auth for APIs
        [auth]
        enabled = true
        provider = "jwt"
        user_entity = "Account"

        # With OAuth2 social login
        [auth]
        enabled = true
        provider = "session"

        [[auth.oauth_providers]]
        provider = "google"
        client_id_env = "GOOGLE_CLIENT_ID"
        client_secret_env = "GOOGLE_CLIENT_SECRET"
        scopes = ["email", "profile"]
    """

    enabled: bool = False
    provider: str = "session"  # "session" | "jwt" | "api_key"
    user_entity: str = "User"  # Name of user entity
    require_email_verification: bool = False
    allow_registration: bool = True

    # Provider-specific config
    session: AuthSessionConfig = field(default_factory=AuthSessionConfig)
    jwt: AuthJwtConfig = field(default_factory=AuthJwtConfig)

    # OAuth2 providers
    oauth_providers: list[AuthOAuthProvider] = field(default_factory=list)

    # Security settings
    password_min_length: int = 8
    max_login_attempts: int = 5
    lockout_duration_minutes: int = 15

    # Audit logging
    audit_enabled: bool = True


@dataclass
class TerraformConfig:
    """Terraform infrastructure configuration."""

    root_module: str = "./infra/terraform"
    cloud_provider: str = "aws"  # "aws", "gcp", "azure"
    environments: list[str] = field(default_factory=lambda: ["dev", "staging", "prod"])
    region: str | None = None


@dataclass
class InfraConfig:
    """Infrastructure configuration from manifest."""

    backends: list[str] = field(default_factory=list)
    docker: DockerConfig = field(default_factory=DockerConfig)
    terraform: TerraformConfig = field(default_factory=TerraformConfig)


# =============================================================================
# Theme Configuration
# =============================================================================


@dataclass
class ThemeConfig:
    """Theme configuration for visual styling.

    Controls the visual appearance of both the app workspace UI and
    public site pages (SiteSpec).

    Available presets:
        - saas-default: Modern SaaS styling with gradient sidebars (default)
        - minimal: Clean, minimal styling with subtle shadows
        - corporate: Professional blue/gray palette for enterprise
        - startup: Bold gradients with vibrant accent colors
        - docs: Documentation-focused, optimized for readability

    Examples in dazzle.toml:

        # Use a preset theme
        [theme]
        preset = "corporate"

        # Override specific tokens
        [theme.colors]
        hero-bg-from = "oklch(0.50 0.18 280)"
        sidebar-from = "oklch(0.30 0.02 200)"

        [theme.spacing]
        section-y = 100
    """

    preset: str = "saas-default"
    colors: dict[str, str] = field(default_factory=dict)
    shadows: dict[str, str] = field(default_factory=dict)
    spacing: dict[str, int] = field(default_factory=dict)
    radii: dict[str, int] = field(default_factory=dict)
    custom: dict[str, str] = field(default_factory=dict)


@dataclass
class StackConfig:
    """Stack configuration - preset combination of backends."""

    name: str
    backends: list[str] = field(default_factory=list)
    description: str | None = None


# =============================================================================
# Dev Configuration (v0.24.0)
# =============================================================================


@dataclass
class DatabaseConfig:
    """Database connection configuration.

    Supports direct URLs and environment variable indirection.

    Examples in dazzle.toml:

        # Direct URL (local native)
        [database]
        url = "postgresql://localhost:5432/myapp"

        # Docker (non-default port)
        [database]
        url = "postgresql://localhost:5433/myapp"

        # Env var indirection (safe to commit)
        [database]
        url = "env:DATABASE_URL"
    """

    url: str = "postgresql://localhost:5432/dazzle"


# =============================================================================
# Dev Configuration (v0.24.0)
# =============================================================================


@dataclass
class DevConfig:
    """Development mode configuration.

    Controls dev-only features like test endpoints.
    These features are automatically disabled when DAZZLE_ENV=production.

    The DAZZLE_ENV environment variable controls the runtime environment:
        - development (default): Test endpoints enabled
        - test: Test endpoints enabled (for E2E tests)
        - production: Disabled for security

    Explicit settings in dazzle.toml override the environment defaults.

    Examples in dazzle.toml:

        # Force-enable test endpoints in production (NOT RECOMMENDED)
        [dev]
        test_endpoints = true

        # Typical production config (usually just use DAZZLE_ENV=production)
        [dev]
        test_endpoints = false
    """

    # None means "use environment default"
    test_endpoints: bool | None = None


@dataclass
class ProjectManifest:
    """
    Project manifest loaded from dazzle.toml.

    Contains project metadata, module paths, and optional infrastructure,
    stack, shell, theme, and authentication configuration.

    Project Types:
        - example: Tutorial/production patterns (default, include in LLM analysis)
        - benchmark: Performance/stress testing (skip unless analyzing performance)
        - test: Test infrastructure projects (skip unless testing)
        - internal: Internal tooling (skip entirely in LLM analysis)
    """

    name: str
    version: str
    project_root: str
    module_paths: list[str]
    project_type: str = "example"  # example | benchmark | test | internal
    infra: InfraConfig | None = None
    stack: StackConfig | None = None
    shell: ShellConfig = field(default_factory=ShellConfig)
    theme: ThemeConfig = field(default_factory=ThemeConfig)
    auth: AuthConfig = field(default_factory=AuthConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    dev: DevConfig = field(default_factory=DevConfig)
    cdn: bool = True  # Serve assets from jsDelivr CDN; set [ui] cdn = false for air-gapped


def load_manifest(path: Path) -> ProjectManifest:
    data = tomllib.loads(path.read_text(encoding="utf-8"))

    project = data.get("project", {})
    modules = data.get("modules", {})
    infra_data = data.get("infra", {})
    stack_data = data.get("stack", {})

    # Parse infra config if present
    infra_config = None
    if infra_data:
        docker_data = infra_data.get("docker", {})
        terraform_data = infra_data.get("terraform", {})

        docker_config = DockerConfig(
            variant=docker_data.get("variant", "compose"),
            image_name=docker_data.get("image_name"),
            base_image=docker_data.get("base_image", "python:3.11-slim"),
            port=docker_data.get("port", 8000),
        )

        terraform_config = TerraformConfig(
            root_module=terraform_data.get("root_module", "./infra/terraform"),
            cloud_provider=terraform_data.get("cloud_provider", "aws"),
            environments=terraform_data.get("environments", ["dev", "staging", "prod"]),
            region=terraform_data.get("region"),
        )

        infra_config = InfraConfig(
            backends=infra_data.get("backends", []),
            docker=docker_config,
            terraform=terraform_config,
        )

    # Parse stack config if present
    stack_config = None
    if stack_data:
        stack_config = StackConfig(
            name=stack_data.get("name", ""),
            backends=stack_data.get("backends", []),
            description=stack_data.get("description"),
        )

    # Parse shell config (with sensible defaults)
    shell_data = data.get("shell", {})
    nav_data = shell_data.get("nav", {})
    header_data = shell_data.get("header", {})
    footer_data = shell_data.get("footer", {})
    pages_data = shell_data.get("pages", [])

    nav_config = ShellNavConfig(
        style=nav_data.get("style", "sidebar"),
        source=nav_data.get("source", "workspaces"),
    )

    header_config = ShellHeaderConfig(
        show_auth=header_data.get("show_auth", True),
        slot=header_data.get("slot"),
    )

    footer_links = [
        ShellFooterLink(label=link.get("label", ""), href=link.get("href", ""))
        for link in footer_data.get("links", [])
    ]

    footer_config = ShellFooterConfig(
        powered_by=footer_data.get("powered_by", True),
        links=footer_links,
        slot=footer_data.get("slot"),
    )

    pages_config = [
        ShellPageConfig(
            src=page.get("src", ""),
            route=page.get("route", ""),
            title=page.get("title"),
            content=page.get("content"),
        )
        for page in pages_data
    ]

    shell_config = ShellConfig(
        layout=shell_data.get("layout", "app-shell"),
        nav=nav_config,
        header=header_config,
        footer=footer_config,
        pages=pages_config,
    )

    # Parse theme config (v0.16.0)
    theme_data = data.get("theme", {})
    theme_config = ThemeConfig(
        preset=theme_data.get("preset", "saas-default"),
        colors=theme_data.get("colors", {}),
        shadows=theme_data.get("shadows", {}),
        spacing=theme_data.get("spacing", {}),
        radii=theme_data.get("radii", {}),
        custom=theme_data.get("custom", {}),
    )

    # Parse auth config
    auth_data = data.get("auth", {})
    session_data = auth_data.get("session", {})
    jwt_data = auth_data.get("jwt", {})
    oauth_providers_data = auth_data.get("oauth_providers", [])

    session_config = AuthSessionConfig(
        duration_hours=session_data.get("duration_hours", 24),
        cookie_name=session_data.get("cookie_name", "dazzle_session"),
        cookie_secure=session_data.get("cookie_secure", True),
        cookie_httponly=session_data.get("cookie_httponly", True),
    )

    jwt_config = AuthJwtConfig(
        access_token_minutes=jwt_data.get("access_token_minutes", 15),
        refresh_token_days=jwt_data.get("refresh_token_days", 7),
        algorithm=jwt_data.get("algorithm", "HS256"),
    )

    oauth_providers = [
        AuthOAuthProvider(
            provider=provider.get("provider", ""),
            client_id_env=provider.get("client_id_env", ""),
            client_secret_env=provider.get("client_secret_env", ""),
            scopes=provider.get("scopes", []),
        )
        for provider in oauth_providers_data
    ]

    auth_config = AuthConfig(
        enabled=auth_data.get("enabled", False),
        provider=auth_data.get("provider", "session"),
        user_entity=auth_data.get("user_entity", "User"),
        require_email_verification=auth_data.get("require_email_verification", False),
        allow_registration=auth_data.get("allow_registration", True),
        session=session_config,
        jwt=jwt_config,
        oauth_providers=oauth_providers,
        password_min_length=auth_data.get("password_min_length", 8),
        max_login_attempts=auth_data.get("max_login_attempts", 5),
        lockout_duration_minutes=auth_data.get("lockout_duration_minutes", 15),
        audit_enabled=auth_data.get("audit_enabled", True),
    )

    # Parse database config
    db_data = data.get("database", {})
    database_config = DatabaseConfig(
        url=db_data.get("url", "postgresql://localhost:5432/dazzle"),
    )

    # Parse dev config (v0.24.0)
    dev_data = data.get("dev", {})
    dev_config = DevConfig(
        test_endpoints=dev_data.get("test_endpoints"),  # None if not set
    )

    # Parse [ui] config
    ui_data = data.get("ui", {})
    cdn_enabled = ui_data.get("cdn", True)

    return ProjectManifest(
        name=project.get("name", "unnamed"),
        version=project.get("version", "0.0.0"),
        project_root=project.get("root", ""),
        module_paths=modules.get("paths", ["./dsl"]),
        project_type=project.get("type", "example"),
        infra=infra_config,
        stack=stack_config,
        shell=shell_config,
        theme=theme_config,
        auth=auth_config,
        database=database_config,
        dev=dev_config,
        cdn=cdn_enabled,
    )


_DEFAULT_DATABASE_URL = "postgresql://localhost:5432/dazzle"


def resolve_database_url(
    manifest: ProjectManifest | None = None,
    *,
    explicit_url: str = "",
) -> str:
    """Resolve the database URL with clear priority.

    Priority:
        1. explicit_url (CLI ``--database-url`` flag)
        2. ``DATABASE_URL`` environment variable
        3. ``dazzle.toml`` ``[database].url`` (supports ``env:VAR_NAME`` indirection)
        4. Default: ``postgresql://localhost:5432/dazzle``

    The ``env:VAR_NAME`` syntax in the manifest lets users commit a safe pointer
    (e.g. ``url = "env:DATABASE_URL"``) that resolves at runtime.

    Heroku-style ``postgres://`` URLs are normalised to ``postgresql://``
    for SQLAlchemy compatibility.
    """
    # 1. Explicit CLI flag
    if explicit_url:
        return _normalise_postgres_scheme(explicit_url)

    # 2. Environment variable
    env_url = os.environ.get("DATABASE_URL", "")
    if env_url:
        return _normalise_postgres_scheme(env_url)

    # 3. Manifest [database].url
    if manifest is not None:
        manifest_url = manifest.database.url
        if manifest_url.startswith("env:"):
            var_name = manifest_url[4:]
            resolved = os.environ.get(var_name, "")
            if resolved:
                return _normalise_postgres_scheme(resolved)
            # env var not set — fall through to default
        elif manifest_url and manifest_url != _DEFAULT_DATABASE_URL:
            return _normalise_postgres_scheme(manifest_url)

    # 4. Default
    return _DEFAULT_DATABASE_URL


def _normalise_postgres_scheme(url: str) -> str:
    """Convert Heroku's ``postgres://`` to ``postgresql://``."""
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://") :]
    return url
