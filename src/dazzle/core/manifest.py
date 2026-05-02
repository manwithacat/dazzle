from __future__ import annotations  # required: forward reference

import os
import tomllib
from dataclasses import dataclass, field
from importlib.metadata import version
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
class URLsConfig:
    """Site and API URL configuration.

    Examples in dazzle.toml:

        [urls]
        site_url = "https://myapp.com"
        api_url = "https://api.myapp.com"
    """

    site_url: str = "http://localhost:3000"
    api_url: str = "http://localhost:8000"


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


@dataclass
class EnvironmentProfile:
    """Per-environment configuration (database connection, Heroku app)."""

    database_url: str = ""
    database_url_env: str = ""
    heroku_app: str = ""


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
class TenantConfig:
    """Multi-tenant configuration.

    isolation = "none" (default): single-schema, no tenant awareness.
    isolation = "schema": each tenant gets a PostgreSQL schema.
    """

    isolation: str = "none"  # "none" | "schema"
    resolver: str = "subdomain"  # "subdomain" | "header" | "session"
    header_name: str = "X-Tenant-ID"  # only used when resolver = "header"
    base_domain: str = ""  # only used when resolver = "subdomain"


@dataclass
class I18nConfig:
    """Internationalisation configuration (#955).

    Cycle 1 — locale-resolution scaffolding only. The ``_()`` Jinja filter
    is identity-passthrough until cycle 2 wires gettext catalogues.

    Attributes:
        default_locale: Locale to fall back to when no Accept-Language
            header / cookie / user pref resolves to a supported locale.
            Defaults to ``"en"``.
        supported_locales: Allow-list. The middleware narrows the
            Accept-Language candidates to this set before picking. An
            empty list means "every locale is supported" — useful when
            a project hasn't decided on a translation matrix yet.
        cookie_name: Name of the cookie that carries an explicit user
            override (set by the locale-switcher UI primitive in cycle 6).
    """

    default_locale: str = "en"
    supported_locales: list[str] = field(default_factory=list)
    cookie_name: str = "dazzle_locale"


@dataclass
class ExtensionsConfig:
    """Registration of project-supplied extensions (closes #786).

    Allows a project's ``dazzle.toml`` to declare FastAPI ``APIRouter``
    objects that the runtime should mount alongside generated routes.
    Each entry is a dotted ``module:attr`` spec imported relative to
    the project root — e.g. ``app.routes.graph:router``.
    """

    routers: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class StorageConfig:
    """One ``[storage.<name>]`` block from ``dazzle.toml`` (#932).

    Storage configs declare a backing store (currently only ``s3``)
    that file fields can bind to via ``field foo: file storage=<name>``.
    The framework's auto-generated upload-ticket / finalize routes
    read this config to build presigned-POST policies and to
    sandbox keys to per-user / per-record prefixes.

    String fields support ``${VAR}`` env-var interpolation. Required
    vars are surfaced via ``dazzle storage env-vars`` and validated
    at app startup.

    Examples in dazzle.toml::

        [storage.cohort_pdfs]
        backend = "s3"
        bucket = "${S3_BUCKET}"
        region = "${AWS_REGION}"
        endpoint_url = "${S3_ENDPOINT_URL}"   # optional — R2/MinIO/LocalStack
        prefix = "production/cohort_assessments/{user_id}/{record_id}/"
        max_bytes = 200_000_000
        content_types = ["application/pdf"]
        ticket_ttl_seconds = 600

    Attributes:
        name: storage identifier (the ``<name>`` in ``[storage.<name>]``).
        backend: storage backend type. v1 supports ``"s3"``.
        bucket: bucket name. May contain ``${VAR}`` references.
        region: AWS region. May contain ``${VAR}`` references.
        endpoint_url: optional S3-compatible endpoint URL. ``None`` =
            real AWS S3. Set to ``${S3_ENDPOINT_URL}`` to support
            MinIO / Cloudflare R2 / LocalStack.
        prefix_template: key prefix with ``{user_id}`` / ``{record_id}``
            substitution. Always ends with ``/``.
        max_bytes: hard limit on uploaded object size (enforced via
            content-length-range condition on the presigned policy).
        content_types: allowlist of acceptable MIME types. Empty list
            means "no content-type restriction".
        ticket_ttl_seconds: how long a minted upload ticket is valid.
    """

    name: str
    backend: str
    bucket: str
    region: str
    prefix_template: str
    max_bytes: int
    content_types: list[str] = field(default_factory=list)
    ticket_ttl_seconds: int = 600
    endpoint_url: str | None = None


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
    urls: URLsConfig = field(default_factory=URLsConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    dev: DevConfig = field(default_factory=DevConfig)
    tenant: TenantConfig = field(default_factory=TenantConfig)
    i18n: I18nConfig = field(default_factory=I18nConfig)  # #955
    framework_version: str | None = None
    cdn: bool = False  # Local-first; opt-in via [ui] cdn = true in dazzle.toml
    # Asset bundling mode. Resolved at request time by `should_bundle_assets()`:
    #   "auto"   = bundle when DAZZLE_ENV=production, individual scripts in dev (default)
    #   "always" = bundle in every environment (perf testing / staging)
    #   "never"  = individual scripts always (advanced live-reload during prod debugging)
    # Set via `[ui] assets = "always"` in dazzle.toml. CLI flags
    # `dazzle serve --bundle` / `--no-bundle` override per-invocation.
    assets: str = "auto"
    favicon: str | None = None  # Override favicon path; set [ui] favicon = "/static/my-icon.svg"
    dark_mode_toggle: bool = True  # #938 — render the dark/light toggle in
    # the app shell (topbar + sidebar footer) and on marketing pages. Set
    # `[ui] dark_mode_toggle = false` for projects whose brand is
    # deliberately light-only (e.g. paper / academic themes) so the toggle
    # is hidden everywhere AND the server forces `data-theme="light"` on
    # first paint regardless of any stale cookie state.
    app_theme: str | None = None  # v0.61.36: app-shell theme preset (overrides
    # the default shadcn-zinc tokens with an alternate :root block). One of
    # the presets shipped in src/dazzle_ui/runtime/static/css/themes/<name>.css
    # — e.g. "linear-dark", "paper", "stripe". None = default theme.
    # Distinct from [theme] which covers site/marketing-page tokens.
    environments: dict[str, EnvironmentProfile] = field(default_factory=dict)
    extensions: ExtensionsConfig = field(default_factory=ExtensionsConfig)
    # v0.61.104 (#932): per-name `[storage.<name>]` blocks. Keyed by the
    # storage name. Empty when no storage blocks are declared.
    storage_defs: dict[str, StorageConfig] = field(default_factory=dict)


_STORAGE_VALID_BACKENDS = {"s3"}


def _parse_storage_configs(data: dict[str, object]) -> dict[str, StorageConfig]:
    """Parse ``[storage.<name>]`` blocks from manifest TOML data (#932).

    Validates required keys + backend allowlist. Raises a clear
    ``ValueError`` if a block is malformed; the caller wraps that in a
    project-load error so authors see one diagnostic per cycle, not a
    Pydantic stack trace.
    """
    raw = data.get("storage") or {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, StorageConfig] = {}
    for name, block in raw.items():
        if not isinstance(block, dict):
            raise ValueError(f"[storage.{name}] must be a TOML table")
        backend = str(block.get("backend") or "")
        if backend not in _STORAGE_VALID_BACKENDS:
            raise ValueError(
                f"[storage.{name}] backend must be one of "
                f"{sorted(_STORAGE_VALID_BACKENDS)!r}, got {backend!r}"
            )
        for required in ("bucket", "region", "prefix"):
            if not block.get(required):
                raise ValueError(f"[storage.{name}] missing required key {required!r}")
        prefix_template = str(block["prefix"])
        if not prefix_template.endswith("/"):
            prefix_template = prefix_template + "/"
        max_bytes = int(block.get("max_bytes", 50 * 1024 * 1024))  # 50 MB default
        ticket_ttl = int(block.get("ticket_ttl_seconds", 600))
        content_types = list(block.get("content_types") or [])
        out[name] = StorageConfig(
            name=name,
            backend=backend,
            bucket=str(block["bucket"]),
            region=str(block["region"]),
            prefix_template=prefix_template,
            max_bytes=max_bytes,
            content_types=content_types,
            ticket_ttl_seconds=ticket_ttl,
            endpoint_url=str(block["endpoint_url"]) if block.get("endpoint_url") else None,
        )
    return out


def check_framework_version(manifest: ProjectManifest) -> None:
    """Raise SystemExit if installed version doesn't satisfy constraint."""
    if not manifest.framework_version:
        return
    from packaging.specifiers import SpecifierSet
    from packaging.version import Version

    installed = Version(version("dazzle-dsl"))
    constraint = manifest.framework_version
    # Handle tilde shorthand: "~0.38" → ">=0.38,<0.39"
    if constraint.startswith("~"):
        base = constraint[1:]
        parts = base.split(".")
        if len(parts) >= 2:
            upper = f"{int(parts[0])}.{int(parts[1]) + 1}"
        else:
            upper = f"{int(parts[0]) + 1}"
        spec = SpecifierSet(f">={base},<{upper}")
    else:
        spec = SpecifierSet(constraint)
    if installed not in spec:
        raise SystemExit(
            f"Framework version mismatch: installed {installed}, "
            f"project requires {constraint}. "
            f"Run: pip install 'dazzle-dsl{constraint}'"
        )


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

    # Parse tenant config
    tenant_data = data.get("tenant", {})
    tenant_config = TenantConfig(
        isolation=tenant_data.get("isolation", "none"),
        resolver=tenant_data.get("resolver", "subdomain"),
        header_name=tenant_data.get("header_name", "X-Tenant-ID"),
        base_domain=tenant_data.get("base_domain", ""),
    )

    # Parse i18n config (#955)
    i18n_data = data.get("i18n", {}) if isinstance(data.get("i18n"), dict) else {}
    raw_supported = i18n_data.get("supported", [])
    if not isinstance(raw_supported, list):
        raw_supported = []
    i18n_config = I18nConfig(
        default_locale=str(i18n_data.get("default", "en")),
        supported_locales=[str(loc) for loc in raw_supported if isinstance(loc, str)],
        cookie_name=str(i18n_data.get("cookie_name", "dazzle_locale")),
    )

    # Parse URLs config
    urls_data = data.get("urls", {})
    urls_config = URLsConfig(
        site_url=urls_data.get("site_url", "http://localhost:3000"),
        api_url=urls_data.get("api_url", "http://localhost:8000"),
    )

    # Parse [ui] config
    ui_data = data.get("ui", {})
    cdn_enabled = ui_data.get("cdn", False)
    favicon_path = ui_data.get("favicon")
    app_theme_name = ui_data.get("theme") or ui_data.get("app_theme")
    dark_mode_toggle_enabled = bool(ui_data.get("dark_mode_toggle", True))
    assets_mode = ui_data.get("assets", "auto")
    if assets_mode not in ("auto", "always", "never"):
        raise ValueError(f"[ui] assets must be 'auto', 'always', or 'never'; got {assets_mode!r}")

    # Parse [extensions] section (#786)
    extensions_data = data.get("extensions", {})
    raw_routers = extensions_data.get("routers", [])
    if not isinstance(raw_routers, list):
        raw_routers = []
    extensions_config = ExtensionsConfig(
        routers=[str(r) for r in raw_routers if isinstance(r, str)],
    )

    # Parse environment profiles
    env_data = data.get("environments", {})
    environments: dict[str, EnvironmentProfile] = {}
    for env_name, env_config in env_data.items():
        if isinstance(env_config, dict):
            environments[env_name] = EnvironmentProfile(
                database_url=env_config.get("database_url", ""),
                database_url_env=env_config.get("database_url_env", ""),
                heroku_app=env_config.get("heroku_app", ""),
            )

    # Parse [storage.<name>] blocks (v0.61.104, #932)
    storage_defs = _parse_storage_configs(data)

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
        urls=urls_config,
        database=database_config,
        dev=dev_config,
        tenant=tenant_config,
        i18n=i18n_config,
        framework_version=project.get("framework_version"),
        cdn=cdn_enabled,
        assets=assets_mode,
        favicon=favicon_path,
        app_theme=app_theme_name,
        dark_mode_toggle=dark_mode_toggle_enabled,
        environments=environments,
        extensions=extensions_config,
        storage_defs=storage_defs,
    )


_DEFAULT_DATABASE_URL = "postgresql://localhost:5432/dazzle"


def resolve_database_url(
    manifest: ProjectManifest | None = None,
    *,
    explicit_url: str = "",
    env_name: str = "",
) -> str:
    """Resolve the database URL with clear priority.

    Priority:
        1. explicit_url (CLI ``--database-url`` flag)
        2. Environment profile (``--env`` / ``DAZZLE_ENV``)
        3. ``DATABASE_URL`` environment variable
        4. ``dazzle.toml`` ``[database].url`` (supports ``env:VAR_NAME`` indirection)
        5. Default: ``postgresql://localhost:5432/dazzle``

    The ``env:VAR_NAME`` syntax in the manifest lets users commit a safe pointer
    (e.g. ``url = "env:DATABASE_URL"``) that resolves at runtime.

    Heroku-style ``postgres://`` URLs are normalised to ``postgresql://``
    for SQLAlchemy compatibility.
    """
    # 1. Explicit CLI flag
    if explicit_url:
        return _normalise_postgres_scheme(explicit_url)

    # 2. Environment profile
    if env_name and manifest is not None:
        if env_name not in manifest.environments:
            available = ", ".join(sorted(manifest.environments.keys())) or "(none)"
            raise SystemExit(
                f"Unknown environment '{env_name}'. "
                f"Available: {available}. "
                f"Check [environments.*] in dazzle.toml."
            )
        profile = manifest.environments[env_name]
        # database_url wins over database_url_env on the same profile
        if profile.database_url:
            return _normalise_postgres_scheme(profile.database_url)
        if profile.database_url_env:
            resolved = os.environ.get(profile.database_url_env, "")
            if resolved:
                return _normalise_postgres_scheme(resolved)
        # Profile set but neither field resolved — fall through

    # 3. Environment variable
    env_url = os.environ.get("DATABASE_URL", "")
    if env_url:
        return _normalise_postgres_scheme(env_url)

    # 4. Manifest [database].url
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

    # 5. Default
    return _DEFAULT_DATABASE_URL


def _normalise_postgres_scheme(url: str) -> str:
    """Convert Heroku's ``postgres://`` to ``postgresql://``."""
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://") :]
    return url


_DEFAULT_SITE_URL = "http://localhost:3000"
_DEFAULT_API_URL = "http://localhost:8000"


def resolve_site_url(manifest: ProjectManifest | None = None) -> str:
    """Resolve the site (frontend) URL.

    Priority:
        1. ``DAZZLE_SITE_URL`` environment variable
        2. ``dazzle.toml`` ``[urls].site_url``
        3. Default: ``http://localhost:3000``
    """
    env_url = os.environ.get("DAZZLE_SITE_URL", "")
    if env_url:
        return env_url.rstrip("/")

    if manifest is not None and manifest.urls.site_url != _DEFAULT_SITE_URL:
        return manifest.urls.site_url.rstrip("/")

    return _DEFAULT_SITE_URL


def resolve_api_url(manifest: ProjectManifest | None = None) -> str:
    """Resolve the API (backend) URL.

    Priority:
        1. ``DAZZLE_API_URL`` environment variable
        2. ``dazzle.toml`` ``[urls].api_url``
        3. Default: ``http://localhost:8000``
    """
    env_url = os.environ.get("DAZZLE_API_URL", "")
    if env_url:
        return env_url.rstrip("/")

    if manifest is not None and manifest.urls.api_url != _DEFAULT_API_URL:
        return manifest.urls.api_url.rstrip("/")

    return _DEFAULT_API_URL
